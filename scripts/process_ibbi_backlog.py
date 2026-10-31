"""Scoped, incrementally-committed text extraction for just the real
IBBI documents the full-universe crawl added that `scripts/process.py`
has not yet extracted -- written because `scripts/process.py` /
`run_process_all` processes every DocumentVersion in ONE session with
no intermediate commits (confirmed by reading `ledgerlight/processing/
batch.py`: no `session.commit()` call inside its loop), so a run
touching the full corpus (2,621 versions, most already-processed
bhavcopy files) risks losing all real progress if it is killed or
crashes before the very end -- which is exactly the real, disclosed
environment-resource risk this project has hit before (see
docs/phase-3/progress.md's low-memory-kill notes). This script commits
after every single document instead, and only touches IBBI's real
backlog, not the whole corpus.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import DocumentVersion  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.processing.document_processor import process_version  # noqa: E402
from ledgerlight.processing.limits import LimitExceededError, ProcessingLimits  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402


def main() -> int:
    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)
    limits = ProcessingLimits()

    pages_created = 0
    pages_already_present = 0
    ocr_pages = 0
    errors: list[str] = []
    skipped: list[str] = []
    processed = 0

    with session_factory() as session:
        version_ids: list[Any] = list(
            session.execute(
                text(
                    "SELECT dv.id FROM document_versions dv "
                    "JOIN documents d ON d.id = dv.document_id "
                    "WHERE d.source_id = 'ibbi' "
                    "AND dv.id NOT IN (SELECT DISTINCT version_id FROM document_pages) "
                    "ORDER BY dv.created_at"
                )
            ).scalars()
        )

    total = len(version_ids)
    print(f"ibbi document_versions to process: {total}")

    for i, version_id in enumerate(version_ids, start=1):
        with session_factory() as session:
            version = session.get(DocumentVersion, version_id)
            if version is None:
                continue
            try:
                body = store.get(version.object_key)
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                errors.append(f"{version_id}: fetch from storage failed: {exc}")
                session.rollback()
                continue

            try:
                outcome = process_version(session, body, version, limits)
            except LimitExceededError as exc:
                errors.append(f"{version_id}: {exc}")
                session.rollback()
                continue
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                errors.append(f"{version_id}: processing failed: {exc}")
                session.rollback()
                continue

            if outcome.skipped_reason:
                skipped.append(f"{version_id}: {outcome.skipped_reason}")
                session.commit()
                continue

            pages_created += outcome.pages_created
            pages_already_present += outcome.pages_already_present
            ocr_pages += outcome.ocr_pages
            processed += 1
            session.commit()

        if i % 10 == 0 or i == total:
            print(f"  {i}/{total} done (pages_created={pages_created}, errors={len(errors)})")

    print(f"documents_processed: {processed}")
    print(f"pages_created: {pages_created}")
    print(f"pages_already_present: {pages_already_present}")
    print(f"ocr_pages: {ocr_pages}")
    print(f"skipped: {len(skipped)}")
    for s in skipped[:20]:
        print(f"  {s}")
    print(f"errors: {len(errors)}")
    for e in errors:
        print(f"  {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
