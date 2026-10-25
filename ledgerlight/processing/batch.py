"""Drive document processing / price loading across every DocumentVersion
on record — the engine behind `scripts/process.py` and `scripts/reprocess.py`.

Dispatch rule: bhavcopy zips (source_id == nse_bhavcopy.SOURCE_ID) go to
price_loader; everything else goes to document_processor.process_version,
which already no-ops cleanly on a MIME type it has no extractor for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentVersion
from ledgerlight.ingestion.nse_bhavcopy import SOURCE_ID as BHAVCOPY_SOURCE_ID
from ledgerlight.ingestion.run_tracking import finish_run, start_run
from ledgerlight.processing.document_processor import ProcessingOutcome, process_version
from ledgerlight.processing.limits import LimitExceededError, ProcessingLimits
from ledgerlight.processing.price_loader import (
    PriceLoadResult,
    extract_csv_text_from_zip_bytes,
    load_price_bars,
)
from ledgerlight.storage.s3_store import ObjectStore


@dataclass
class ProcessAllStats:
    versions_seen: int = 0
    documents_processed: int = 0
    price_files_processed: int = 0
    pages_created: int = 0
    pages_already_present: int = 0
    ocr_pages: int = 0
    price_rows_upserted: int = 0
    price_rows_unchanged: int = 0
    price_rows_quarantined: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_process_all(
    session: Session, store: ObjectStore, limits: ProcessingLimits
) -> ProcessAllStats:
    stats = ProcessAllStats()
    run = start_run(session, source_id=None, stage="process")

    rows = session.execute(
        select(DocumentVersion, Document.source_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .order_by(DocumentVersion.created_at)
    ).all()

    for version, source_id in rows:
        stats.versions_seen += 1
        try:
            body = store.get(version.object_key)
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            stats.errors.append(f"{version.id}: fetch from storage failed: {exc}")
            continue

        if source_id == BHAVCOPY_SOURCE_ID:
            try:
                csv_text = extract_csv_text_from_zip_bytes(body)
                price_result: PriceLoadResult = load_price_bars(
                    session, source_id, version, csv_text
                )
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                stats.errors.append(f"{version.id}: price load failed: {exc}")
                continue
            stats.price_files_processed += 1
            stats.price_rows_upserted += price_result.rows_upserted
            stats.price_rows_unchanged += price_result.rows_unchanged
            stats.price_rows_quarantined += len(price_result.quarantined)
            continue

        try:
            outcome: ProcessingOutcome = process_version(session, body, version, limits)
        except LimitExceededError as exc:
            stats.errors.append(f"{version.id}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            stats.errors.append(f"{version.id}: processing failed: {exc}")
            continue

        if outcome.skipped_reason:
            stats.skipped.append(f"{version.id}: {outcome.skipped_reason}")
            continue

        stats.documents_processed += 1
        stats.pages_created += outcome.pages_created
        stats.pages_already_present += outcome.pages_already_present
        stats.ocr_pages += outcome.ocr_pages

    finish_run(
        session,
        run,
        status="success" if not stats.errors else "partial_failure",
        fetched=stats.versions_seen,
        new=stats.pages_created,
        unchanged=stats.pages_already_present,
        failed=len(stats.errors),
        ocr_pages=stats.ocr_pages,
        rows_parsed=stats.price_rows_upserted + stats.price_rows_unchanged,
        rows_quarantined=stats.price_rows_quarantined,
    )
    return stats
