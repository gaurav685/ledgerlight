"""Force reprocessing of one DocumentVersion -- used after a fix (e.g. a
previously dead-lettered item) or to demonstrate that bumping an
extractor_version creates new DocumentPage rows while leaving old ones
untouched (see ledgerlight.processing.document_processor's determinism
guarantee).

Usage: python scripts/reprocess.py VERSION_ID
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import Document, DocumentVersion  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.nse_bhavcopy import SOURCE_ID as BHAVCOPY_SOURCE_ID  # noqa: E402
from ledgerlight.processing.document_processor import process_version  # noqa: E402
from ledgerlight.processing.limits import ProcessingLimits  # noqa: E402
from ledgerlight.processing.price_loader import (  # noqa: E402
    extract_csv_text_from_zip_bytes,
    load_price_bars,
)
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/reprocess.py VERSION_ID")
        return 2
    version_id = uuid.UUID(sys.argv[1])

    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        row = session.execute(
            select(DocumentVersion, Document.source_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(DocumentVersion.id == version_id)
        ).first()
        if row is None:
            print(f"no such DocumentVersion: {version_id}")
            return 1
        version, source_id = row

        body = store.get(version.object_key)

        if source_id == BHAVCOPY_SOURCE_ID:
            csv_text = extract_csv_text_from_zip_bytes(body)
            result = load_price_bars(session, source_id, version, csv_text)
            print(f"rows_parsed: {result.rows_parsed}")
            print(f"rows_upserted: {result.rows_upserted}")
            print(f"rows_unchanged: {result.rows_unchanged}")
            print(f"quarantined: {len(result.quarantined)}")
        else:
            outcome = process_version(session, body, version, ProcessingLimits())
            print(f"mime_type: {outcome.mime_type}")
            print(f"pages_created: {outcome.pages_created}")
            print(f"pages_already_present: {outcome.pages_already_present}")
            print(f"ocr_pages: {outcome.ocr_pages}")
            if outcome.skipped_reason:
                print(f"skipped_reason: {outcome.skipped_reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
