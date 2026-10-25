"""Re-run the Phase 0 seed-dataset acquisition reproducibly.

Every SEED_ITEMS entry was individually verified reachable (HTTP 200,
correct content-type) with the project's identifying User-Agent before
being added here — see docs/data/seed-universe.md and
docs/data/source-inventory.md for the robots.txt / terms-of-use findings
behind each source_id. The generated bhavcopy series
(_nse_archive_bhavcopy_items) was spot-checked on a sample of dates, not
exhaustively verified one-by-one — a missing trading day (weekend/holiday
mismatch) or an unavailable date raises HTTPStatusError, which main() below
catches and reports as a normal skip, never a fatal error.

This is Phase 0 scope only: a small, legitimately-sourced seed, not the
Phase 1 ingestion pipeline.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.acquisition.fetcher import (  # noqa: E402
    FileTooLargeError,
    HTTPStatusError,
    LoginRedirectError,
    PoliteFetcher,
    RobotsDisallowed,
)
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.ingestion.known_seed_items import SEED_ITEMS  # noqa: E402
from ledgerlight.ingestion.nse_bhavcopy_urls import bhavcopy_url_for_date  # noqa: E402


def _nse_archive_bhavcopy_items() -> list[dict[str, Any]]:
    """Twice-monthly NSE equity bhavcopy snapshots, Jan 2017 - Sep 2025.

    archives.nseindia.com (distinct from the blocked nsearchives.nseindia.com
    and www.nseindia.com — see docs/data/source-inventory.md §B1) serves both
    the legacy per-date CSV format (through 2024-07-05) and the newer UDiFF
    format (from 2024-07-08). This covers the union of all seed-company event
    windows and doubles as the survivorship-bias check (DHFL/Jet Airways/
    Reliance Capital/Future Retail all have snapshots after their respective
    suspension/CIRP dates).
    """
    items: list[dict[str, Any]] = []
    month_days = (5, 20)

    year, month = 2017, 1
    while (year, month) <= (2025, 9):
        for day in month_days:
            try:
                date = dt.date(year, month, day)
            except ValueError:
                continue
            while date.weekday() >= 5:  # Sat/Sun -> following Monday
                date += dt.timedelta(days=1)

            retrieval_url = bhavcopy_url_for_date(date)

            items.append(
                {
                    "source_id": "nse_archives",
                    "source_url": "https://archives.nseindia.com/",
                    "retrieval_url": retrieval_url,
                    "document_type": "equity_bhavcopy",
                    "publication_time": date.isoformat(),
                    "coverage_note": (
                        f"NSE equity bhavcopy for {date.isoformat()} (twice-monthly seed sample)"
                    ),
                    "licence_status": "public_no_explicit_licence",
                    "redistribution_allowed": "unclear",
                    "terms_url": None,
                }
            )
        month += 1
        if month > 12:
            month = 1
            year += 1
    return items


def main() -> int:
    settings = load_settings()
    manifest_path = settings.data_dir / "manifests" / "seed.jsonl"

    all_items = SEED_ITEMS + _nse_archive_bhavcopy_items()
    results = {"fetched": 0, "skipped_duplicate": 0, "blocked": 0, "not_found": 0, "errors": 0}

    with PoliteFetcher(
        contact_email=settings.contact_email,
        data_dir=settings.data_dir,
        manifest_path=manifest_path,
        rate_limit_seconds=settings.fetch_rate_limit_seconds,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_retries=settings.fetch_max_retries,
        max_file_size_bytes=settings.fetch_max_file_size_bytes,
    ) as fetcher:
        for item in all_items:
            label = f"{item['source_id']}: {item['retrieval_url']}"
            try:
                entry = fetcher.fetch(**item)
                if entry is None:
                    print(f"SKIP (robots): {label}")
                    results["blocked"] += 1
                    continue
                if entry.skipped_duplicate_of:
                    print(f"DUPLICATE (already have content): {label}")
                    results["skipped_duplicate"] += 1
                else:
                    print(f"OK ({entry.bytes} bytes, sha256={entry.sha256[:12]}...): {label}")
                    results["fetched"] += 1
            except RobotsDisallowed:
                print(f"BLOCKED (robots.txt disallow): {label}")
                results["blocked"] += 1
            except LoginRedirectError as exc:
                print(f"BLOCKED (redirected to login-like URL {exc}): {label}")
                results["blocked"] += 1
            except FileTooLargeError as exc:
                print(f"BLOCKED (size guard: {exc}): {label}")
                results["blocked"] += 1
            except HTTPStatusError as exc:
                print(f"NOT FOUND (HTTP {exc.status_code}, likely non-trading day): {label}")
                results["not_found"] += 1
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR ({exc.__class__.__name__}: {exc}): {label}")
                results["errors"] += 1

    print("---")
    print(f"Total items attempted: {len(all_items)}")
    print(f"Summary: {results}")
    return 0 if results["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
