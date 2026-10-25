"""Process every DocumentVersion on record: extract PDF/HTML page text (with
OCR fallback where needed) and load bhavcopy CSVs into price_bars. Safe to
re-run — every extractor/loader is idempotent (see
ledgerlight.processing.document_processor and .price_loader)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.processing.batch import run_process_all  # noqa: E402
from ledgerlight.processing.limits import ProcessingLimits  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402


def main() -> int:
    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)
    limits = ProcessingLimits()

    started = time.monotonic()
    with session_factory() as session:
        stats = run_process_all(session, store, limits)
    elapsed = time.monotonic() - started

    print(f"versions_seen: {stats.versions_seen}")
    print(f"documents_processed (pdf/html): {stats.documents_processed}")
    print(f"  pages_created: {stats.pages_created}")
    print(f"  pages_already_present: {stats.pages_already_present}")
    print(f"  ocr_pages: {stats.ocr_pages}")
    print(f"price_files_processed (bhavcopy): {stats.price_files_processed}")
    print(f"  price_rows_upserted: {stats.price_rows_upserted}")
    print(f"  price_rows_unchanged: {stats.price_rows_unchanged}")
    print(f"  price_rows_quarantined: {stats.price_rows_quarantined}")
    print(f"skipped (no extractor for mime type): {len(stats.skipped)}")
    for s in stats.skipped[:20]:
        print(f"  {s}")
    if len(stats.skipped) > 20:
        print(f"  ... and {len(stats.skipped) - 20} more")
    print(f"errors: {len(stats.errors)}")
    for e in stats.errors:
        print(f"  {e}")
    print(f"elapsed_seconds: {elapsed:.2f}")

    return 1 if stats.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
