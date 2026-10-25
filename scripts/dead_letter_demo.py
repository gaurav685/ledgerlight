"""CLI demonstration of the retry/dead-letter/reprocess mechanism end to
end, for the Phase 1 verification sequence's raw output (the same logic is
pinned as a real test in tests/test_retry_dead_letter.py):

1. A stage fails 3 times in a row (max_attempts=3) -- each attempt gets
   its own processing_attempts row; the 3rd failure also writes a
   dead_letters row.
2. The underlying issue is "fixed" and the same payload_ref is retried --
   it succeeds, recording a new processing_attempts row. The dead_letters
   row from step 1 is left untouched (dead letters are an audit trail,
   never deleted)."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import DeadLetter  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.retry import run_with_attempt_tracking  # noqa: E402


class _SimulatedTransientFailure(Exception):
    pass


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)
    payload_ref = f"demo://dead-letter-demo/{uuid.uuid4()}"
    max_attempts = 3

    with session_factory() as session:
        from ledgerlight.common.timeutil import utc_now

        demo_started_at = utc_now()
        print(f"payload_ref: {payload_ref}")
        print(f"-- simulating {max_attempts} failing attempts --")
        for attempt_number in range(1, max_attempts + 1):
            try:
                run_with_attempt_tracking(
                    session,
                    lambda: (_ for _ in ()).throw(
                        _SimulatedTransientFailure("demo: upstream still broken")
                    ),
                    run_id=None,
                    version_id=None,
                    stage="demo_stage",
                    payload_ref=payload_ref,
                    attempt_number=attempt_number,
                    max_attempts=max_attempts,
                )
            except _SimulatedTransientFailure as exc:
                print(f"  attempt {attempt_number}: failed ({exc})")

        dead_letter = session.scalar(
            select(DeadLetter).where(DeadLetter.payload_ref == payload_ref)
        )
        print(f"dead_letter written: {dead_letter is not None}")
        if dead_letter:
            print(f"  attempts={dead_letter.attempts} last_error={dead_letter.last_error!r}")
            print(f"  resolved_at={dead_letter.resolved_at} (should be None here)")

        print("-- 'fixing' the issue and reprocessing --")
        result = run_with_attempt_tracking(
            session,
            lambda: "fixed",
            run_id=None,
            version_id=None,
            stage="demo_stage",
            payload_ref=payload_ref,
            attempt_number=1,
            max_attempts=3,
        )
        print(f"reprocess result: {result!r}")

        # NOTE: ProcessingAttempt has no payload_ref column (only
        # DeadLetter does) -- it's tied to a run_id/version_id, neither
        # of which this synthetic demo has. Filtering by created_at
        # window on *this* payload_ref's dead_letter instead of by
        # stage avoids picking up every past run of this same script.
        from ledgerlight.db.models import ProcessingAttempt as _PA

        attempts = session.scalars(
            select(_PA)
            .where(_PA.stage == "demo_stage", _PA.created_at >= demo_started_at)
            .order_by(_PA.created_at)
        ).all()
        print(f"processing_attempts rows from this run: {len(attempts)}")
        for a in attempts:
            print(f"  attempt_number={a.attempt_number} status={a.status}")

        dead_letters_after = session.scalars(
            select(DeadLetter).where(DeadLetter.payload_ref == payload_ref)
        ).all()
        print(f"dead_letters rows after reprocess: {len(dead_letters_after)} (never deleted)")
        for dl in dead_letters_after:
            print(f"  resolved_at={dl.resolved_at}  resolution={dl.resolution!r}")

        # run_with_attempt_tracking commits internally on every attempt --
        # session.rollback() here would NOT undo any of it (see ADR 0004
        # §6 / scripts/dead_letter_real_pipeline_demo.py). Delete the rows
        # this run actually created, explicitly.
        for a in attempts:
            session.delete(a)
        for dl in dead_letters_after:
            session.delete(dl)
        session.commit()
        print("(this run's demo rows explicitly deleted -- not left in the database)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
