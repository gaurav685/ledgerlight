"""Observability CLI: per-source ingestion health -- last run, backlog,
dead-letter count, and failure-class breakdown. Reads only what's already
persisted (ingestion_runs, processing_attempts, dead_letters, documents) --
no new network calls."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import func, select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import (  # noqa: E402
    DeadLetter,
    Document,
    DocumentVersion,
    IngestionRun,
    ProcessingAttempt,
    Source,
)
from ledgerlight.db.session import make_session_factory  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        sources = session.scalars(select(Source).order_by(Source.id)).all()

        print(
            f"{'source_id':<20} {'enabled':<8} {'last_run_status':<18} "
            f"{'last_run_at':<26} {'doc_count':<10} {'last_run_failed':<15}"
        )
        for source in sources:
            last_run = session.scalar(
                select(IngestionRun)
                .where(IngestionRun.source_id == source.id)
                .order_by(IngestionRun.started_at.desc())
                .limit(1)
            )
            doc_count = session.scalar(
                select(func.count()).select_from(Document).where(Document.source_id == source.id)
            )

            status = last_run.status if last_run else "never_run"
            last_run_at = str(last_run.started_at) if last_run else "-"
            last_run_failed = last_run.failed if last_run else "-"
            print(
                f"{source.id:<20} {str(source.enabled):<8} {status:<18} "
                f"{last_run_at:<26} {doc_count or 0:<10} {last_run_failed!s:<15}"
            )

        print()
        print("-- overall dead letters by stage (resolved / unresolved) --")
        dead_letter_rows = session.execute(
            select(
                DeadLetter.stage,
                func.count().filter(DeadLetter.resolved_at.is_(None)),
                func.count().filter(DeadLetter.resolved_at.is_not(None)),
            ).group_by(DeadLetter.stage)
        ).all()
        if not dead_letter_rows:
            print("  (none)")
        for stage, unresolved, resolved in dead_letter_rows:
            print(f"  {stage}: unresolved={unresolved} resolved={resolved}")

        print()
        print("-- failure classes (processing_attempts, status=failed) --")
        failure_class_rows = session.execute(
            select(ProcessingAttempt.error_class, func.count())
            .where(ProcessingAttempt.status == "failed")
            .group_by(ProcessingAttempt.error_class)
        ).all()
        if not failure_class_rows:
            print("  (none)")
        for error_class, count in failure_class_rows:
            print(f"  {error_class}: {count}")

        print()
        total_versions = session.scalar(select(func.count()).select_from(DocumentVersion))
        print(f"total document_versions: {total_versions}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
