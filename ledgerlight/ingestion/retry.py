"""Attempt recording and dead-letter creation shared by every ingestion
and processing op. Dagster's RetryPolicy handles the actual re-execution;
this module is what turns "exhausted retries" into a durable dead_letters
row instead of just a failed run disappearing from view.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.common.timeutil import utc_now
from ledgerlight.db.models import DeadLetter, ProcessingAttempt
from ledgerlight.ingestion.base import classify_exception

T = TypeVar("T")


def record_failed_attempt(
    session: Session,
    *,
    run_id: uuid.UUID | None,
    version_id: uuid.UUID | None,
    stage: str,
    attempt_number: int,
    duration_ms: int,
    exc: Exception,
) -> None:
    session.add(
        ProcessingAttempt(
            run_id=run_id,
            version_id=version_id,
            stage=stage,
            status="failed",
            error_class=classify_exception(exc),
            error_message=str(exc)[:4000],
            duration_ms=duration_ms,
            attempt_number=attempt_number,
        )
    )
    session.commit()


def record_succeeded_attempt(
    session: Session,
    *,
    run_id: uuid.UUID | None,
    version_id: uuid.UUID | None,
    stage: str,
    attempt_number: int,
    duration_ms: int,
) -> None:
    session.add(
        ProcessingAttempt(
            run_id=run_id,
            version_id=version_id,
            stage=stage,
            status="success",
            duration_ms=duration_ms,
            attempt_number=attempt_number,
        )
    )
    session.commit()


def write_dead_letter(
    session: Session,
    *,
    payload_ref: str,
    stage: str,
    attempts: int,
    last_error: str,
    first_failed_at: dt.datetime,
) -> None:
    session.add(
        DeadLetter(
            payload_ref=payload_ref,
            stage=stage,
            last_error=last_error[:4000],
            attempts=attempts,
            first_failed_at=first_failed_at,
        )
    )
    session.commit()


def resolve_dead_letter_if_any(
    session: Session, *, payload_ref: str, stage: str, resolution: str
) -> None:
    """Called automatically on a successful attempt (see
    run_with_attempt_tracking below): if an unresolved dead_letters row
    exists for this exact payload_ref/stage, mark it resolved. Dead
    letters are never deleted -- resolution is recorded, not erased."""
    unresolved = session.scalars(
        select(DeadLetter).where(
            DeadLetter.payload_ref == payload_ref,
            DeadLetter.stage == stage,
            DeadLetter.resolved_at.is_(None),
        )
    ).all()
    for dead_letter in unresolved:
        dead_letter.resolved_at = utc_now()
        dead_letter.resolution = resolution[:4000]
    if unresolved:
        session.commit()


def run_with_attempt_tracking(
    session: Session,
    fn: Callable[[], T],
    *,
    run_id: uuid.UUID | None,
    version_id: uuid.UUID | None,
    stage: str,
    payload_ref: str,
    attempt_number: int,
    max_attempts: int,
) -> T:
    """Run fn() once, recording a processing_attempts row either way. If
    this is the final allowed attempt and it still fails, also writes a
    dead_letters row before re-raising — Dagster's own RetryPolicy is what
    decides whether there even IS a next attempt; this function only
    records what happened and gives up gracefully on the last one."""
    start = time.monotonic()
    try:
        result = fn()
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        record_failed_attempt(
            session,
            run_id=run_id,
            version_id=version_id,
            stage=stage,
            attempt_number=attempt_number,
            duration_ms=duration_ms,
            exc=exc,
        )
        if attempt_number >= max_attempts:
            write_dead_letter(
                session,
                payload_ref=payload_ref,
                stage=stage,
                attempts=attempt_number,
                last_error=str(exc),
                first_failed_at=utc_now(),
            )
        raise
    else:
        duration_ms = int((time.monotonic() - start) * 1000)
        record_succeeded_attempt(
            session,
            run_id=run_id,
            version_id=version_id,
            stage=stage,
            attempt_number=attempt_number,
            duration_ms=duration_ms,
        )
        resolve_dead_letter_if_any(
            session,
            payload_ref=payload_ref,
            stage=stage,
            resolution=f"succeeded on a later attempt (attempt_number={attempt_number})",
        )
        return result
