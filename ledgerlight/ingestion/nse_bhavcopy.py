"""Live NSE bhavcopy ingestion job: daily/incremental and ad-hoc backfill
ranges, both built on the same PoliteFetcher + upsert pipeline Phase
0/Correction 1 proved out. A 404 for a given date is NOT an error — it
means no trading day (weekend already filtered by business_days(), but
exchange holidays still 404) — see ledgerlight.ingestion.base for how
that's classified in processing_attempts without being treated as a
pipeline failure.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from ledgerlight.acquisition.fetcher import HTTPStatusError, PoliteFetcher
from ledgerlight.ingestion.base import require_enabled_source
from ledgerlight.ingestion.nse_bhavcopy_urls import bhavcopy_url_for_date, business_days
from ledgerlight.ingestion.run_tracking import finish_run, start_run
from ledgerlight.ingestion.upsert import upsert_document_version
from ledgerlight.storage.s3_store import ObjectStore

SOURCE_ID = "nse_archives"


@dataclass
class BhavcopyJobStats:
    attempted: int = 0
    fetched_new: int = 0
    unchanged: int = 0
    not_found: int = 0
    errors: list[str] = field(default_factory=list)


def run_bhavcopy_range(
    session: Session,
    store: ObjectStore,
    fetcher: PoliteFetcher,
    start: dt.date,
    end: dt.date,
) -> BhavcopyJobStats:
    require_enabled_source(session, SOURCE_ID)
    stats = BhavcopyJobStats()
    run = start_run(session, source_id=SOURCE_ID, stage="ingest")

    for date in business_days(start, end):
        url = bhavcopy_url_for_date(date)
        stats.attempted += 1
        try:
            entry = fetcher.fetch(
                source_id=SOURCE_ID,
                source_url="https://archives.nseindia.com/",
                retrieval_url=url,
                document_type="equity_bhavcopy",
                publication_time=date.isoformat(),
                coverage_note=f"NSE equity bhavcopy for {date.isoformat()} (live ingestion job)",
                licence_status="public_no_explicit_licence",
                redistribution_allowed="unclear",
            )
        except HTTPStatusError as exc:
            if exc.status_code == 404:
                stats.not_found += 1
                continue
            stats.errors.append(f"{date}: HTTP {exc.status_code}")
            continue
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            stats.errors.append(f"{date}: {exc.__class__.__name__}: {exc}")
            continue

        if entry is None:
            stats.errors.append(
                f"{date}: robots.txt disallowed (unexpected for an AVAILABLE source)"
            )
            continue

        body = Path(entry.local_path).read_bytes()
        _version, _doc_new, version_new = upsert_document_version(session, store, entry, body)
        if version_new:
            stats.fetched_new += 1
        else:
            stats.unchanged += 1

    finish_run(
        session,
        run,
        status="success" if not stats.errors else "partial_failure",
        fetched=stats.attempted,
        new=stats.fetched_new,
        unchanged=stats.unchanged,
        failed=len(stats.errors),
    )
    return stats
