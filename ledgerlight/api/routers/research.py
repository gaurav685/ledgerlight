"""Enhancement 1 §3: read-only `/v1/research/event-study` endpoints.
Real, global reference data (like companies/events/scores) -- not
RLS-protected, not tenant-owned -- so `get_db` directly, same as
`ledgerlight.api.routers.companies`. Never writes anything; a real
run is only ever produced by `scripts/event_study.py run` or the
Dagster `event_study_job`, both human-triggered.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api import rbac
from ledgerlight.api.deps import get_db, require_permission
from ledgerlight.api.schemas import EventStudyCompanyEventOut, EventStudyRunSummaryOut
from ledgerlight.research.event_study import PRIMARY_WINDOW
from ledgerlight.research.models import EventStudyEventResult, EventStudyRun
from ledgerlight.research.report import REPORT_DIR

router = APIRouter(prefix="/v1/research", tags=["research"])

_SAFE_EVENT_TYPE = re.compile(r"^[a-z_]+$")
_REPO_ROOT = Path(__file__).resolve().parents[3]

_VIEW = Depends(require_permission(rbac.VIEW_COMPANY_DATA))

NO_RUN_YET_DETAIL = (
    "No real event_study_runs row exists yet -- run `scripts/event_study.py run` "
    "(or the Dagster event_study_job) first."
)


def _latest_run(db: DbSession) -> EventStudyRun:
    run = db.scalars(select(EventStudyRun).order_by(EventStudyRun.created_at.desc())).first()
    if run is None:
        raise HTTPException(status_code=404, detail=NO_RUN_YET_DETAIL)
    return run


@router.get("/event-study", response_model=EventStudyRunSummaryOut, dependencies=[_VIEW])
def get_event_study_summary(db: DbSession = Depends(get_db)) -> EventStudyRunSummaryOut:
    """The latest real run's own summary -- real spec hash, real event
    counts per filter stage, and the real full metrics table (CAR,
    t/BMP/rank, Holm-adjusted p, per event type and window)."""
    run = _latest_run(db)
    return EventStudyRunSummaryOut(
        run_id=run.id,
        spec_version=run.spec_version,
        spec_sha256=run.spec_sha256,
        git_sha=run.git_sha,
        created_at=run.created_at,
        event_counts=dict(run.event_counts_json),
        metrics=dict(run.metrics_json),
    )


@router.get(
    "/event-study/companies/{company_id}",
    response_model=list[EventStudyCompanyEventOut],
    dependencies=[_VIEW],
)
def get_company_event_study_events(
    company_id: uuid.UUID, db: DbSession = Depends(get_db)
) -> list[EventStudyCompanyEventOut]:
    """This real company's own events from the latest real run, each
    with its real primary-window CAR next to the real type-wide
    average -- the company-page "Market reaction" panel's own data
    source. An empty list is a real, honest answer (no real event-
    study events for this company in the latest run), never a 404."""
    run = _latest_run(db)
    company_results = list(
        db.scalars(
            select(EventStudyEventResult).where(
                EventStudyEventResult.run_id == run.id,
                EventStudyEventResult.company_id == company_id,
            )
        ).all()
    )

    out: list[EventStudyCompanyEventOut] = []
    for r in company_results:
        type_metrics = run.metrics_json.get(r.event_type_code, {})
        type_average = None
        if isinstance(type_metrics, dict):
            primary_window_metrics = type_metrics.get(PRIMARY_WINDOW, {})
            if isinstance(primary_window_metrics, dict):
                mean_car = primary_window_metrics.get("mean_car")
                if isinstance(mean_car, int | float):
                    type_average = float(mean_car)
        out.append(
            EventStudyCompanyEventOut(
                event_type_code=r.event_type_code,
                severity_band=r.severity_band,
                event_date=r.event_date,
                is_primary=r.is_primary,
                possible_corporate_action=r.possible_corporate_action,
                car_primary_window=r.car_by_window.get(PRIMARY_WINDOW),
                type_average_car_primary_window=type_average,
            )
        )
    return out


@router.get("/event-study/caar/{event_type}.png", dependencies=[_VIEW])
def get_event_study_caar_plot(event_type: str) -> FileResponse:
    """The real CAAR plot PNG `ledgerlight.research.report.generate_report`
    already wrote to disk -- served directly, never regenerated per
    request. `event_type` is checked against a strict `[a-z_]+`
    allowlist before touching the filesystem (real path-traversal
    hardening, not just a documented assumption)."""
    if not _SAFE_EVENT_TYPE.match(event_type):
        raise HTTPException(status_code=404, detail="not found")
    png_path = _REPO_ROOT / REPORT_DIR / f"caar_{event_type}.png"
    if not png_path.is_file():
        raise HTTPException(status_code=404, detail="no real CAAR plot for this event type yet")
    return FileResponse(png_path, media_type="image/png")
