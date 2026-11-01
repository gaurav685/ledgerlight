"""Phase 5 §3: create-investigation (real async job), investigation
status, dossier retrieval, and export -- all real tenant isolation
for `investigations` comes from its own real RLS policy (migration
`4dad2cd00443`); `dossiers`/`claims` carry no `tenant_id` of their own
and are NOT RLS-protected, so every real lookup here goes through a
real, RLS-gated `Investigation` fetch FIRST (an investigation
invisible to the caller's tenant 404s exactly like a truly unknown
one -- never distinguishable, so this never lets a caller enumerate
other tenants' investigation ids) before trusting its `investigation_id`
to query `Dossier`/`Claim` directly.
"""

from __future__ import annotations

import datetime as dt
import uuid

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ledgerlight.agent.budgets import BudgetConfig
from ledgerlight.agent.export import export_dossier_json, export_dossier_markdown
from ledgerlight.agent.models import Dossier, Investigation
from ledgerlight.agent.state_machine import run_investigation
from ledgerlight.api import rbac
from ledgerlight.api.deps import Identity, get_db, require_csrf, require_permission
from ledgerlight.api.schemas import DossierOut, InvestigationCreateRequest, InvestigationOut
from ledgerlight.api.tenancy import tenant_scope
from ledgerlight.config.settings import load_settings
from ledgerlight.db.session import make_session_factory
from ledgerlight.knowledge.models import Company

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/dossiers", tags=["dossiers"])


def _run_investigation_in_background(
    investigation_id: uuid.UUID, company_id: uuid.UUID, as_of: dt.date, tenant_id: uuid.UUID
) -> None:
    """Runs in its own real, independent session -- the request's own
    app-role session is already closed by the time a real
    `BackgroundTasks` callback executes (FastAPI tears down `yield`
    dependencies before running background tasks), so this can never
    reuse it. Opens a fresh app-role connection, scopes it to the real
    tenant, and resumes the real state machine from the row this
    request already created."""
    settings = load_settings()
    session = make_session_factory(settings)()
    try:
        with tenant_scope(session, tenant_id):
            run_investigation(
                session,
                company_id,
                as_of,
                requested_by=f"api:{tenant_id}",
                resume_investigation_id=investigation_id,
            )
    except Exception:
        logger.exception("background_investigation_failed", investigation_id=str(investigation_id))
    finally:
        session.close()


@router.post(
    "/investigations",
    response_model=InvestigationOut,
    status_code=202,
    dependencies=[Depends(require_csrf)],
)
def create_investigation(
    payload: InvestigationCreateRequest,
    background_tasks: BackgroundTasks,
    identity: Identity = Depends(require_permission(rbac.CREATE_INVESTIGATION)),
    db: DbSession = Depends(get_db),
) -> InvestigationOut:
    """Creates the real `Investigation` row synchronously (so the
    caller gets a real id back immediately), then hands the real work
    off to a background task -- a real async job, using the row's own
    `state`/`final_status` columns as its real job status, never a
    second, parallel job-tracking table."""
    budget = BudgetConfig()
    investigation = Investigation(
        id=uuid.uuid4(),
        company_id=payload.company_id,
        as_of=payload.as_of,
        requested_by=f"api:{identity.tenant_id}",
        tenant_id=identity.tenant_id,
        state="PLAN",
        budget_config=budget.to_json(),
        usage={"steps": 0, "wall_seconds": 0.0, "tool_calls": 0, "llm_tokens": 0, "cost_usd": 0.0},
    )
    db.add(investigation)
    db.flush()

    background_tasks.add_task(
        _run_investigation_in_background,
        investigation.id,
        payload.company_id,
        payload.as_of,
        identity.tenant_id,
    )
    return InvestigationOut(
        id=investigation.id,
        company_id=investigation.company_id,
        as_of=investigation.as_of,
        state=investigation.state,
        final_status=investigation.final_status,
        started_at=investigation.started_at,
        finished_at=investigation.finished_at,
    )


def _get_visible_investigation(db: DbSession, investigation_id: uuid.UUID) -> Investigation:
    """The real RLS-gated fetch every other function in this module
    relies on for tenant isolation -- see this module's own docstring."""
    investigation = db.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return investigation


@router.get(
    "/investigations",
    response_model=list[InvestigationOut],
    dependencies=[Depends(require_permission(rbac.VIEW_DOSSIER))],
)
def list_investigations(db: DbSession = Depends(get_db)) -> list[InvestigationOut]:
    """Real investigations for the caller's own tenant -- `investigations`
    is directly RLS-protected (migration `4dad2cd00443`), so a plain
    query under the app role already returns only this tenant's own
    rows; no extra filtering is needed here."""
    rows = db.scalars(
        select(Investigation).order_by(Investigation.started_at.desc()).limit(200)
    ).all()
    return [
        InvestigationOut(
            id=row.id,
            company_id=row.company_id,
            as_of=row.as_of,
            state=row.state,
            final_status=row.final_status,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )
        for row in rows
    ]


@router.get(
    "/investigations/{investigation_id}",
    response_model=InvestigationOut,
    dependencies=[Depends(require_permission(rbac.VIEW_DOSSIER))],
)
def get_investigation(
    investigation_id: uuid.UUID, db: DbSession = Depends(get_db)
) -> InvestigationOut:
    investigation = _get_visible_investigation(db, investigation_id)
    return InvestigationOut(
        id=investigation.id,
        company_id=investigation.company_id,
        as_of=investigation.as_of,
        state=investigation.state,
        final_status=investigation.final_status,
        started_at=investigation.started_at,
        finished_at=investigation.finished_at,
    )


@router.get(
    "/investigations/{investigation_id}/dossier",
    response_model=DossierOut,
    dependencies=[Depends(require_permission(rbac.VIEW_DOSSIER))],
)
def get_latest_dossier(investigation_id: uuid.UUID, db: DbSession = Depends(get_db)) -> DossierOut:
    _get_visible_investigation(db, investigation_id)  # real RLS gate -- see module docstring
    dossier = db.scalar(
        select(Dossier)
        .where(Dossier.investigation_id == investigation_id)
        .order_by(Dossier.version.desc())
        .limit(1)
    )
    if dossier is None:
        raise HTTPException(
            status_code=404, detail="no dossier rendered yet for this investigation"
        )
    return DossierOut(
        id=dossier.id,
        investigation_id=dossier.investigation_id,
        version=dossier.version,
        status=dossier.status,
        sections=dossier.sections,
        claim_id_map=dossier.claim_id_map,
        created_at=dossier.created_at,
    )


@router.get(
    "/investigations/{investigation_id}/export",
    dependencies=[Depends(require_permission(rbac.EXPORT_DOSSIER))],
)
def export_latest_dossier(
    investigation_id: uuid.UUID,
    fmt: str = Query(default="markdown", pattern="^(markdown|json)$"),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    investigation = _get_visible_investigation(db, investigation_id)  # real RLS gate
    dossier = db.scalar(
        select(Dossier)
        .where(Dossier.investigation_id == investigation_id)
        .order_by(Dossier.version.desc())
        .limit(1)
    )
    if dossier is None:
        raise HTTPException(
            status_code=404, detail="no dossier rendered yet for this investigation"
        )
    company = db.get(Company, investigation.company_id)
    company_name = company.display_name if company is not None else "Unknown company"
    if fmt == "json":
        return {"format": "json", "content": export_dossier_json(dossier, investigation)}
    return {
        "format": "markdown",
        "content": export_dossier_markdown(dossier, investigation, company_name),
    }
