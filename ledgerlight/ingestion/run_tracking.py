"""Persisted per-run metrics (ingestion_runs) -- what `ingest-report` reads.
Every ingestion job wraps its work in start_run()/finish_run() so a run's
counts survive even after the Dagster run itself scrolls out of view.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ledgerlight.common.timeutil import utc_now
from ledgerlight.db.models import IngestionRun


def start_run(session: Session, *, source_id: str | None, stage: str) -> IngestionRun:
    run = IngestionRun(source_id=source_id, stage=stage, status="running", started_at=utc_now())
    session.add(run)
    session.commit()
    return run


def finish_run(
    session: Session,
    run: IngestionRun,
    *,
    status: str,
    fetched: int = 0,
    new: int = 0,
    unchanged: int = 0,
    failed: int = 0,
    ocr_pages: int = 0,
    rows_parsed: int = 0,
    rows_quarantined: int = 0,
) -> None:
    run.status = status
    run.finished_at = utc_now()
    run.fetched = fetched
    run.new = new
    run.unchanged = unchanged
    run.failed = failed
    run.ocr_pages = ocr_pages
    run.rows_parsed = rows_parsed
    run.rows_quarantined = rows_quarantined
    session.commit()
