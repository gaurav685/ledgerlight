"""Full dead-letter cycle through the REAL document-processing pipeline
(not the abstract retry.py demo in scripts/dead_letter_demo.py): ingest a
synthetic corrupted PDF, watch it fail and dead-letter across 3 attempts
(matching Dagster's RetryPolicy(max_retries=2) = 3 total attempts), fix
it, reprocess, and confirm resolved_at gets set. Everything inserted is
explicitly deleted at the end -- this is a demo, not real corpus data.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.common.timeutil import utc_now  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import Document, DocumentVersion  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.db.temporal import compute_known_at  # noqa: E402
from ledgerlight.ingestion.retry import run_with_attempt_tracking  # noqa: E402
from ledgerlight.processing.document_processor import process_version  # noqa: E402
from ledgerlight.processing.limits import ProcessingLimits  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402

# A corrupted PDF: a real %PDF magic header (so mime-sniffing correctly
# identifies it as a PDF) followed by garbage -- PyMuPDF.open() raises on
# this, a realistic "bad file" failure mode, not a fabricated exception.
CORRUPTED_PDF = b"%PDF-1.4\n" + b"\x00\xff\xee\xdd garbage not a real pdf structure" * 50

# A minimal but genuinely valid single-page PDF (hand-built, no external
# tool) -- what "fixing the input" looks like.
VALID_PDF = (
    b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>"
)


def main() -> int:
    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)
    limits = ProcessingLimits()
    max_attempts = 3

    with session_factory() as session:
        source_key = f"synthetic://dead-letter-real-pipeline-demo/{uuid.uuid4()}"
        document = Document(
            source_id="sebi",
            source_key=source_key,
            document_type="synthetic_demo",
        )
        session.add(document)
        session.flush()

        corrupted_key, _ = store.put_content_addressed(CORRUPTED_PDF, _sha(CORRUPTED_PDF), ".pdf")
        now = utc_now()
        known_at, basis = compute_known_at(
            source_id="sebi", published_at=None, snapshot_at=None, retrieved_at=now
        )
        version = DocumentVersion(
            document_id=document.id,
            sha256=_sha(CORRUPTED_PDF),
            content_sha256=_sha(CORRUPTED_PDF),
            object_key=corrupted_key,
            bytes=len(CORRUPTED_PDF),
            mime_type="application/pdf",
            retrieval_method="automated_fetch",
            retrieval_url=source_key,
            http_status=200,
            retrieved_at=now,
            known_at=known_at,
            known_at_basis=basis,
            tool_version="dead-letter-demo/1",
        )
        session.add(version)
        session.commit()
        payload_ref = str(version.id)
        print(f"ingested synthetic corrupted PDF as version {payload_ref}")

        print(f"\n-- attempting to process it {max_attempts} times (expect failure each time) --")
        for attempt_number in range(1, max_attempts + 1):
            try:
                run_with_attempt_tracking(
                    session,
                    lambda: process_version(session, CORRUPTED_PDF, version, limits),
                    run_id=None,
                    version_id=version.id,
                    stage="process",
                    payload_ref=payload_ref,
                    attempt_number=attempt_number,
                    max_attempts=max_attempts,
                )
            except Exception as exc:  # noqa: BLE001 - expected, printed not swallowed
                print(f"  attempt {attempt_number}: failed ({exc.__class__.__name__}: {exc})")

        from ledgerlight.db.models import DeadLetter, ProcessingAttempt

        print("\n-- dead_letters row (BEFORE fix) --")
        before = session.scalars(
            select(DeadLetter).where(DeadLetter.payload_ref == payload_ref)
        ).all()
        for dl in before:
            print(
                f"  id={dl.id} attempts={dl.attempts} resolved_at={dl.resolved_at} "
                f"resolution={dl.resolution!r}"
            )
        print(f"  ({len(before)} row(s))")

        print("\n-- ingest-report would show this under 'overall dead letters by stage' --")
        print("  stage=process count>=1 (see scripts/ingest_report.py)")

        print("\n-- fixing the input: re-uploading a valid PDF for the same version --")
        valid_key, _ = store.put_content_addressed(VALID_PDF, _sha(VALID_PDF), ".pdf")
        version.object_key = valid_key
        version.sha256 = _sha(VALID_PDF)
        version.content_sha256 = _sha(VALID_PDF)
        version.bytes = len(VALID_PDF)
        session.commit()

        print("-- reprocessing with the fixed input --")
        result = run_with_attempt_tracking(
            session,
            lambda: process_version(session, VALID_PDF, version, limits),
            run_id=None,
            version_id=version.id,
            stage="process",
            payload_ref=payload_ref,
            attempt_number=1,
            max_attempts=3,
        )
        print(f"  reprocess outcome: pages_created={result.pages_created} mime={result.mime_type}")

        print("\n-- dead_letters row (AFTER fix + successful reprocess) --")
        after = session.scalars(
            select(DeadLetter).where(DeadLetter.payload_ref == payload_ref)
        ).all()
        for dl in after:
            print(
                f"  id={dl.id} attempts={dl.attempts} resolved_at={dl.resolved_at} "
                f"resolution={dl.resolution!r}"
            )
        print(f"  ({len(after)} row(s) -- same row, not deleted, resolved_at now set)")

        attempts = session.scalars(
            select(ProcessingAttempt)
            .where(ProcessingAttempt.version_id == version.id)
            .order_by(ProcessingAttempt.created_at)
        ).all()
        print(f"\nprocessing_attempts for this version: {len(attempts)}")
        for a in attempts:
            print(
                f"  attempt_number={a.attempt_number} status={a.status} error_class={a.error_class}"
            )

        # Every step above commits internally (record_failed_attempt,
        # write_dead_letter, process_version's own page-insert commit,
        # resolve_dead_letter_if_any) -- a session.rollback() here would
        # NOT undo any of it (exactly the commit-semantics lesson from
        # ADR 0004 §6). Clean up explicitly, in FK order, instead.
        from ledgerlight.db.models import DocumentPage

        session.query(DocumentPage).filter(DocumentPage.version_id == version.id).delete()
        session.query(ProcessingAttempt).filter(ProcessingAttempt.version_id == version.id).delete()
        session.query(DeadLetter).filter(DeadLetter.payload_ref == payload_ref).delete()
        session.delete(version)
        session.delete(document)
        session.commit()
        print("\n(all demo rows explicitly deleted -- not left in the database)")

    return 0


def _sha(body: bytes) -> str:
    import hashlib

    return hashlib.sha256(body).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
