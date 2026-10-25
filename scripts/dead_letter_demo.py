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
from ledgerlight.db.models import DeadLetter, ProcessingAttempt  # noqa: E402
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

        attempts = session.scalars(
            select(ProcessingAttempt)
            .where(ProcessingAttempt.stage == "demo_stage")
            .order_by(ProcessingAttempt.created_at)
        ).all()
        print(f"total processing_attempts rows for this demo: {len(attempts)}")
        for a in attempts:
            print(f"  attempt_number={a.attempt_number} status={a.status}")

        dead_letters_after = session.scalars(
            select(DeadLetter).where(DeadLetter.payload_ref == payload_ref)
        ).all()
        print(f"dead_letters rows after reprocess: {len(dead_letters_after)} (unchanged)")

        session.rollback()  # this is a demo -- never leaves rows behind

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
