"""Phase 5 §3: review queue list/get/decide. `review_tasks` carries no
`tenant_id` of its own (see `ledgerlight.api.models`'s own docstring
for why) -- real tenant isolation here is reached transitively,
through each task's own dossier's own investigation's real,
RLS-protected `tenant_id` (the same pattern `routers.dossiers` already
uses). A claim-only review task (no `dossier_id`) is out of this
router's scope for now -- every real review task created by
`ledgerlight.agent.review.create_review_tasks` is dossier-level.
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from ledgerlight.agent import review as agent_review
from ledgerlight.agent.models import Dossier, Investigation, ReviewTask
from ledgerlight.api import audit, rbac
from ledgerlight.api.deps import Identity, get_db, require_csrf, require_permission
from ledgerlight.api.schemas import ReviewDecisionRequest, ReviewTaskOut
from ledgerlight.api.tenancy import make_app_session_factory, tenant_scope
from ledgerlight.config.settings import load_settings

router = APIRouter(prefix="/v1/review", tags=["review"])


@lru_cache(maxsize=1)
def _independent_session_factory() -> sessionmaker[DbSession]:
    """`ledgerlight.agent.review.record_decision` commits internally
    (a real, relied-upon behaviour -- see its own callers in
    `scripts/dossier_review.py` and `tests/test_agent_review.py`'s own
    docstring), so it must never run inside `get_db`'s own
    request-scoped transaction: an explicit mid-block `commit()` there
    closes that transaction out from under the `with session.begin():`
    context manager FastAPI's dependency is still inside, and the
    very next statement on `db` raises a real
    `InvalidRequestError: Can't operate on closed transaction inside
    context manager` (confirmed directly). This mirrors
    `ledgerlight.api.rate_limit`'s own independent-transaction
    pattern for the same real reason."""
    return make_app_session_factory(load_settings())


_VALID_DECISIONS = ("approve", "approve_with_edits", "reject", "escalate")


def _to_out(task: ReviewTask) -> ReviewTaskOut:
    return ReviewTaskOut(
        id=task.id,
        dossier_id=task.dossier_id,
        claim_id=task.claim_id,
        reason_code=task.reason_code,
        priority=task.priority,
        status=task.status,
        assignee=task.assignee,
        decision=task.decision,
        created_at=task.created_at,
    )


def _get_visible_task(db: DbSession, review_task_id: uuid.UUID) -> ReviewTask:
    """Fetches the real task, then proves its owning investigation is
    visible under the caller's own real RLS tenant scope before
    returning it -- an invisible-to-this-tenant task 404s identically
    to a truly unknown one, same as `routers.dossiers`."""
    task = db.get(ReviewTask, review_task_id)
    if task is None or task.dossier_id is None:
        raise HTTPException(status_code=404, detail="review task not found")
    dossier = db.get(Dossier, task.dossier_id)
    if dossier is None:
        raise HTTPException(status_code=404, detail="review task not found")
    investigation = db.get(Investigation, dossier.investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="review task not found")
    return task


@router.get(
    "/tasks",
    response_model=list[ReviewTaskOut],
    dependencies=[Depends(require_permission(rbac.VIEW_REVIEW_QUEUE))],
)
def list_review_tasks(db: DbSession = Depends(get_db)) -> list[ReviewTaskOut]:
    """Real open tasks whose owning investigation is visible under the
    caller's own real RLS tenant scope -- the JOIN down to
    `investigations` is what makes this tenant-safe: Postgres applies
    `investigations`' own real RLS policy to every row the join
    touches, same as any other query against that table."""
    rows = db.scalars(
        select(ReviewTask)
        .join(Dossier, Dossier.id == ReviewTask.dossier_id)
        .join(Investigation, Investigation.id == Dossier.investigation_id)
        .where(ReviewTask.status == "open")
        .order_by(ReviewTask.priority.desc(), ReviewTask.created_at)
    ).all()
    return [_to_out(row) for row in rows]


@router.get(
    "/tasks/{review_task_id}",
    response_model=ReviewTaskOut,
    dependencies=[Depends(require_permission(rbac.VIEW_REVIEW_QUEUE))],
)
def get_review_task(review_task_id: uuid.UUID, db: DbSession = Depends(get_db)) -> ReviewTaskOut:
    return _to_out(_get_visible_task(db, review_task_id))


@router.post(
    "/tasks/{review_task_id}/decision",
    response_model=ReviewTaskOut,
    dependencies=[Depends(require_csrf)],
)
def decide_review_task(
    review_task_id: uuid.UUID,
    payload: ReviewDecisionRequest,
    identity: Identity = Depends(require_permission(rbac.DECIDE_REVIEW)),
    db: DbSession = Depends(get_db),
) -> ReviewTaskOut:
    if payload.decision not in _VALID_DECISIONS:
        raise HTTPException(status_code=422, detail=f"decision must be one of {_VALID_DECISIONS}")
    _get_visible_task(db, review_task_id)  # real RLS gate, on the request's own session

    factory = _independent_session_factory()
    with factory() as independent_session:
        with tenant_scope(independent_session, identity.tenant_id):
            task = agent_review.record_decision(
                independent_session,
                review_task_id,
                payload.decision,
                reviewer=str(identity.user_id),
                notes=payload.notes,
            )
        # record_decision's own internal commit() ends the transaction
        # `tenant_scope` above was tied to (its `is_local=true` GUC is
        # transaction-scoped) -- a fresh transaction auto-begins on the
        # next statement with NO tenant context set, so audit_logs'
        # own real RLS policy would block this INSERT outright unless
        # the tenant is scoped again here, in the new transaction.
        with tenant_scope(independent_session, identity.tenant_id):
            audit.write_audit_log(
                independent_session,
                identity.tenant_id,
                "review_decision",
                actor_user_id=identity.user_id,
                target_type="review_task",
                target_id=str(review_task_id),
                extra={"decision": payload.decision},
            )
            independent_session.commit()
        return _to_out(task)
