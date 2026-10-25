"""Proves the attempt-tracking / dead-letter mechanism end-to-end against
real tables: every attempt (success or failure) gets a processing_attempts
row; a dead_letters row is written only once the final allowed attempt
fails; a subsequent successful reprocess attempt records its own success
row without touching the dead letter (dead letters are an audit trail,
never deleted or "cleared")."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.common.timeutil import utc_now
from ledgerlight.db.models import DeadLetter, ProcessingAttempt
from ledgerlight.ingestion.retry import run_with_attempt_tracking

pytestmark = pytest.mark.integration


class _DeliberateFailure(Exception):
    pass


def test_dead_letter_written_only_on_final_attempt(db_session: Session) -> None:
    payload_ref = "test://dead-letter-demo/does-not-exist"
    max_attempts = 3

    for attempt_number in range(1, max_attempts + 1):
        with pytest.raises(_DeliberateFailure):
            run_with_attempt_tracking(
                db_session,
                lambda: (_ for _ in ()).throw(_DeliberateFailure("simulated transient failure")),
                run_id=None,
                version_id=None,
                stage="test_stage",
                payload_ref=payload_ref,
                attempt_number=attempt_number,
                max_attempts=max_attempts,
            )

    attempts = db_session.scalars(
        select(ProcessingAttempt).where(ProcessingAttempt.stage == "test_stage")
    ).all()
    assert len(attempts) == max_attempts
    assert all(a.status == "failed" for a in attempts)
    assert all(a.error_class == "validation" for a in attempts)

    dead_letters = db_session.scalars(
        select(DeadLetter).where(DeadLetter.payload_ref == payload_ref)
    ).all()
    assert len(dead_letters) == 1
    assert dead_letters[0].attempts == max_attempts


def test_reprocess_after_fix_succeeds_without_touching_dead_letter(db_session: Session) -> None:
    payload_ref = "test://dead-letter-demo/fixed-on-retry"

    with pytest.raises(_DeliberateFailure):
        run_with_attempt_tracking(
            db_session,
            lambda: (_ for _ in ()).throw(_DeliberateFailure("simulated transient failure")),
            run_id=None,
            version_id=None,
            stage="test_stage_fixed",
            payload_ref=payload_ref,
            attempt_number=1,
            max_attempts=1,
        )

    dead_letters_before = db_session.scalars(
        select(DeadLetter).where(DeadLetter.payload_ref == payload_ref)
    ).all()
    assert len(dead_letters_before) == 1
    first_failed_at = dead_letters_before[0].first_failed_at

    # "Fix" applied; reprocess as a fresh attempt sequence.
    result = run_with_attempt_tracking(
        db_session,
        lambda: "ok",
        run_id=None,
        version_id=None,
        stage="test_stage_fixed",
        payload_ref=payload_ref,
        attempt_number=1,
        max_attempts=3,
    )
    assert result == "ok"

    dead_letters_after = db_session.scalars(
        select(DeadLetter).where(DeadLetter.payload_ref == payload_ref)
    ).all()
    assert len(dead_letters_after) == 1  # untouched — dead letters are never deleted
    assert dead_letters_after[0].first_failed_at == first_failed_at

    attempts = db_session.scalars(
        select(ProcessingAttempt).where(ProcessingAttempt.stage == "test_stage_fixed")
    ).all()
    assert [a.status for a in sorted(attempts, key=lambda a: a.attempt_number)] == [
        "failed",
        "success",
    ]


def test_utc_now_is_timezone_aware() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.tzinfo == dt.UTC
