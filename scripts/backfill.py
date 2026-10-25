"""Ad-hoc historical backfill of NSE equity bhavcopy over an explicit date
range — the one-time historical load referenced in
ledgerlight/orchestration/definitions.py's bhavcopy_daily docstring. Not a
Dagster run (looping per-partition run overhead would dominate); it calls
the same run_bhavcopy_range() the daily partition itself uses.

Usage: python scripts/backfill.py START_DATE END_DATE
       (dates as YYYY-MM-DD)
"""

from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.acquisition.fetcher import PoliteFetcher  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.nse_bhavcopy import run_bhavcopy_range  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python scripts/backfill.py START_DATE END_DATE (YYYY-MM-DD)")
        return 2
    start = dt.date.fromisoformat(sys.argv[1])
    end = dt.date.fromisoformat(sys.argv[2])

    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)

    started = time.monotonic()
    with (
        session_factory() as session,
        PoliteFetcher(
            contact_email=settings.contact_email,
            data_dir=settings.data_dir,
            manifest_path=settings.data_dir / "manifests" / "live_ingestion.jsonl",
            rate_limit_seconds=settings.fetch_rate_limit_seconds,
            timeout_seconds=settings.fetch_timeout_seconds,
            max_retries=settings.fetch_max_retries,
            max_file_size_bytes=settings.fetch_max_file_size_bytes,
        ) as fetcher,
    ):
        stats = run_bhavcopy_range(session, store, fetcher, start, end)
    elapsed = time.monotonic() - started

    print(f"range: {start} .. {end}")
    print(f"business_days_attempted: {stats.attempted}")
    print(f"fetched_new: {stats.fetched_new}")
    print(f"unchanged: {stats.unchanged}")
    print(f"not_found (holiday/no-trading-day): {stats.not_found}")
    print(f"errors: {len(stats.errors)}")
    for e in stats.errors:
        print(f"  {e}")
    print(f"elapsed_seconds: {elapsed:.2f}")
    if stats.attempted:
        print(f"throughput: {stats.attempted / elapsed:.3f} requests/sec")

    return 1 if stats.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
