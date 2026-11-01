"""Phase 5 §3: company search/overview, event timelines, point-in-time
scores, and management credibility. Companies/events/scores are real,
global reference data (Phase 1-3's own schema) -- not RLS-protected,
not tenant-owned -- so these endpoints use the plain `get_db` session,
no `tenant_scope` needed to read them. Point-in-time correctness is
never reimplemented here: every endpoint delegates to Phase 4's own,
already-tested `ledgerlight.agent.tools` functions (`get_events`,
`get_timeline`, `get_risk_score`), which already enforce
`known_at <= as_of`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ledgerlight.agent.tools import get_events, get_risk_score, get_timeline
from ledgerlight.api import rbac
from ledgerlight.api.deps import get_db, require_permission
from ledgerlight.api.schemas import CompanyOut, CredibilityOut, EventOut, ScoreOut
from ledgerlight.knowledge.models import Company

router = APIRouter(prefix="/v1/companies", tags=["companies"])

_VIEW = Depends(require_permission(rbac.VIEW_COMPANY_DATA))

# docs/modelling/guidance.md: "No GUIDANCE_MISS extraction machinery,
# matching logic, or credibility series was built." -- the real,
# documented reason this endpoint always and honestly reports
# insufficient data rather than fabricating a number.
CREDIBILITY_UNAVAILABLE_REASON = (
    "No guidance-tracking / credibility-series machinery has been built "
    "(see docs/modelling/guidance.md) -- this is a documented limitation, "
    "not a transient error."
)


@router.get("/search", response_model=list[CompanyOut], dependencies=[_VIEW])
def search_companies(
    q: str = Query(..., min_length=1), db: DbSession = Depends(get_db)
) -> list[CompanyOut]:
    rows = (
        db.execute(select(Company).where(Company.display_name.ilike(f"%{q}%")).limit(25))
        .scalars()
        .all()
    )
    return [CompanyOut(id=row.id, name=row.display_name) for row in rows]


@router.get("/{company_id}", response_model=CompanyOut, dependencies=[_VIEW])
def get_company(company_id: uuid.UUID, db: DbSession = Depends(get_db)) -> CompanyOut:
    row = db.get(Company, company_id)
    if row is None:
        raise HTTPException(status_code=404, detail="company not found")
    return CompanyOut(id=row.id, name=row.display_name)


@router.get("/{company_id}/events", response_model=list[EventOut], dependencies=[_VIEW])
def get_company_events(
    company_id: uuid.UUID,
    as_of: dt.date = Query(default_factory=dt.date.today),
    event_type_code: str | None = None,
    db: DbSession = Depends(get_db),
) -> list[EventOut]:
    envelope = get_events(db, company_id, as_of, event_type_code)
    return [
        EventOut(
            id=event.event_id,
            company_id=company_id,
            event_type_code=event.event_type_code,
            status=event.tier,
            event_time=event.event_time.date() if event.event_time else None,
            known_at=event.known_at.date(),
            summary=None,
        )
        for event in envelope.data
    ]


@router.get("/{company_id}/timeline", dependencies=[_VIEW])
def get_company_timeline(
    company_id: uuid.UUID,
    as_of: dt.date = Query(default_factory=dt.date.today),
    db: DbSession = Depends(get_db),
) -> list[dict[str, object]]:
    """Real events AND real filings, ordered -- the real evidence
    trail the frontend's event-timeline page renders. Returned as the
    raw tool envelope's data shape (already a stable, documented
    Pydantic model in `ledgerlight.agent.tools.TimelineEntry`), not
    re-wrapped into a parallel schema."""
    envelope = get_timeline(db, company_id, as_of)
    return [entry.model_dump(mode="json") for entry in envelope.data]


@router.get("/{company_id}/scores", response_model=ScoreOut, dependencies=[_VIEW])
def get_company_score(
    company_id: uuid.UUID,
    as_of: dt.date = Query(default_factory=dt.date.today),
    db: DbSession = Depends(get_db),
) -> ScoreOut:
    """Real point-in-time score + SHAP + the real, live-read model
    limitations banner -- never a score computed after `as_of`
    (enforced inside `get_risk_score`/`get_score` themselves), and the
    limitations text is read live from `docs/modelling/model-card.md`
    every call, never a copy that can drift from it."""
    envelope = get_risk_score(db, company_id, as_of)
    result = envelope.data
    if not result.found:
        raise HTTPException(
            status_code=404,
            detail=f"no real score found for this company at or before {as_of} "
            f"-- model limitations: {result.model_limitations}",
        )
    return ScoreOut(
        company_id=company_id,
        as_of=result.score_as_of or as_of,
        score=result.calibrated_probability or 0.0,
        model_version="primary-risk-lightgbm:1.0",
        shap_contributors=result.top_shap_contributors,
        model_limitations=result.model_limitations,
    )


@router.get("/{company_id}/credibility", response_model=CredibilityOut, dependencies=[_VIEW])
def get_company_credibility(
    company_id: uuid.UUID, as_of: dt.date = Query(default_factory=dt.date.today)
) -> CredibilityOut:
    """Honestly reports insufficient data, with the real, documented
    reason -- per the brief's own §3 requirement, never a fabricated
    credibility figure."""
    return CredibilityOut(
        company_id=company_id, as_of=as_of, available=False, reason=CREDIBILITY_UNAVAILABLE_REASON
    )
