"""Generic "fetch a fixed list of known items" ingestion job — the shape
shared by SEBI, IBBI, CARE and every company-IR source: a short,
individually-verified list of URLs (ledgerlight.ingestion.known_seed_items
.SEED_ITEMS), re-fetched on each run. Re-running is what makes this
"incremental" for these sources: unchanged content is a no-op (via
upsert_document_version's hash check), changed content becomes a new
version, exactly like the live NSE bhavcopy job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ledgerlight.acquisition.fetcher import (
    FileTooLargeError,
    HTTPStatusError,
    LoginRedirectError,
    PoliteFetcher,
    RobotsDisallowed,
)
from ledgerlight.ingestion.base import require_enabled_source
from ledgerlight.ingestion.known_seed_items import SEED_ITEMS
from ledgerlight.ingestion.run_tracking import finish_run, start_run
from ledgerlight.ingestion.upsert import upsert_document_version
from ledgerlight.storage.s3_store import ObjectStore


@dataclass
class KnownItemsJobStats:
    source_id: str
    attempted: int = 0
    fetched_new: int = 0
    unchanged: int = 0
    blocked: int = 0
    errors: list[str] = field(default_factory=list)


def items_for_source(source_id: str) -> list[dict[str, Any]]:
    return [item for item in SEED_ITEMS if item["source_id"] == source_id]


def run_known_items_job(
    session: Session, store: ObjectStore, fetcher: PoliteFetcher, source_id: str
) -> KnownItemsJobStats:
    require_enabled_source(session, source_id)
    stats = KnownItemsJobStats(source_id=source_id)
    items = items_for_source(source_id)
    run = start_run(session, source_id=source_id, stage="ingest")

    for item in items:
        stats.attempted += 1
        try:
            entry = fetcher.fetch(**item)
        except RobotsDisallowed:
            stats.blocked += 1
            continue
        except (HTTPStatusError, LoginRedirectError, FileTooLargeError) as exc:
            stats.errors.append(f"{item['retrieval_url']}: {exc.__class__.__name__}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            stats.errors.append(f"{item['retrieval_url']}: {exc.__class__.__name__}: {exc}")
            continue

        if entry is None:
            stats.blocked += 1
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
