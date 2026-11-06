"""Phase 6A §8: real ingestion/processing throughput measurement, per
stage -- documents/minute and pages/minute. Reads real already-
downloaded PDFs from data/raw/ directly through the real extraction
function (no DB writes, so it's safe to re-run and times the real
extraction cost alone, not idempotent-skip logic). Chunking throughput
is measured by creating N fresh real documents (same pattern as
scripts/e2e_pipeline_demo.py) and timing chunk_version for real.

Usage:
    python3 -m uv run python scripts/measure_processing_throughput.py
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy import text as sa_text  # noqa: E402

from ledgerlight.acquisition.import_local import import_inbox  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import Document, DocumentVersion  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.backfill_from_manifest import run_store_backfill  # noqa: E402
from ledgerlight.knowledge.chunking import chunk_version  # noqa: E402
from ledgerlight.knowledge.models import Chunk  # noqa: E402
from ledgerlight.processing import pdf as pdf_mod  # noqa: E402
from ledgerlight.processing.document_processor import process_version  # noqa: E402
from ledgerlight.processing.limits import ProcessingLimits  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402

SAMPLE_PDF_COUNT = 20
SAMPLE_DOC_COUNT = 5


def _measure_pdf_extraction() -> None:
    data_raw = REPO_ROOT / "data" / "raw"
    pdfs = sorted(data_raw.rglob("*.pdf"))[:SAMPLE_PDF_COUNT]
    if not pdfs:
        print("pdf extraction: no real PDFs found under data/raw -- skipped")
        return

    limits = ProcessingLimits()
    total_pages = 0
    start = time.monotonic()
    for pdf_path in pdfs:
        try:
            pages = pdf_mod.extract_pdf_pages(str(pdf_path), limits)
        except Exception:  # noqa: BLE001 -- a handful of real files may be unreadable
            continue
        total_pages += len(pages)
    elapsed = time.monotonic() - start

    docs_per_min = len(pdfs) / elapsed * 60
    pages_per_min = total_pages / elapsed * 60 if total_pages else 0.0
    print(f"pdf extraction: {len(pdfs)} real PDFs, {total_pages} real pages, {elapsed:.2f}s")
    print(f"  documents/minute: {docs_per_min:.1f}")
    print(f"  pages/minute: {pages_per_min:.1f}")


def _measure_ingestion_and_chunking() -> None:
    settings = load_settings()
    session_factory = make_session_factory(settings)
    store = ObjectStore(settings)

    def _html(seed_name: str) -> str:
        # import-local dedups purely on content sha256 -- embedding
        # seed_name makes each sample document's content genuinely new,
        # so all SAMPLE_DOC_COUNT are real distinct documents rather
        # than SAMPLE_DOC_COUNT-1 real duplicate-skips of identical bytes.
        return (
            f"<html><body><p>Real throughput-measurement filler text ({seed_name}), "
            "repeated to give the real chunker a real, non-trivial document body "
            "to split. "
            + ("Phase 6A sec8 real throughput sample sentence. " * 60)
            + "</p></body></html>"
        )

    inbox_dir = settings.data_dir / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    provenance_path = inbox_dir / "provenance.csv"
    file_existed = provenance_path.exists()
    with provenance_path.open("a", newline="", encoding="utf-8") as fh:
        if not file_existed:
            fh.write("file_name,original_url,retrieved_at_by_user,notes\n")
        seed_names = []
        for _ in range(SAMPLE_DOC_COUNT):
            seed_name = f"throughput-{uuid.uuid4().hex[:8]}"
            seed_names.append(seed_name)
            (inbox_dir / f"{seed_name}.html").write_text(_html(seed_name), encoding="utf-8")
            fh.write(
                f"{seed_name}.html,https://example.com/throughput/{seed_name},2026-11-06,"
                "Phase 6A sec8 throughput measurement\n"
            )

    import_start = time.monotonic()
    import_inbox(data_dir=settings.data_dir)
    import_elapsed = time.monotonic() - import_start

    with session_factory() as session:
        manifest_path = settings.data_dir / "manifests" / "manual.jsonl"
        backfill_start = time.monotonic()
        run_store_backfill(session, store, [manifest_path])
        backfill_elapsed = time.monotonic() - backfill_start

        versions: list[DocumentVersion] = []
        for seed_name in seed_names:
            version = session.scalar(
                select(DocumentVersion)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(Document.source_key.like(f"%{seed_name}%"))
            )
            if version is not None:
                versions.append(version)

        page_start = time.monotonic()
        for version in versions:
            body = store.get(version.object_key)
            process_version(session, body, version, ProcessingLimits())
        session.commit()
        page_elapsed = time.monotonic() - page_start

        chunk_start = time.monotonic()
        total_chunks = 0
        for version in versions:
            chunk_version(session, version)
            total_chunks += len(
                session.scalars(select(Chunk).where(Chunk.version_id == version.id)).all()
            )
        session.commit()
        chunk_elapsed = time.monotonic() - chunk_start

        # cleanup -- these are synthetic throughput-sample documents, not
        # real corpus content, so remove them rather than leave residue.
        for seed_name in seed_names:
            pattern = f"%{seed_name}%"
            session.execute(
                sa_text(
                    "DELETE FROM chunks WHERE version_id IN "
                    "(SELECT dv.id FROM document_versions dv JOIN documents d "
                    "ON d.id = dv.document_id WHERE d.source_key LIKE :p)"
                ),
                {"p": pattern},
            )
            session.execute(
                sa_text(
                    "DELETE FROM document_pages WHERE version_id IN "
                    "(SELECT dv.id FROM document_versions dv JOIN documents d "
                    "ON d.id = dv.document_id WHERE d.source_key LIKE :p)"
                ),
                {"p": pattern},
            )
            session.execute(
                sa_text(
                    "DELETE FROM document_versions WHERE document_id IN "
                    "(SELECT id FROM documents WHERE source_key LIKE :p)"
                ),
                {"p": pattern},
            )
            session.execute(
                sa_text("DELETE FROM documents WHERE source_key LIKE :p"), {"p": pattern}
            )
            inbox_file = inbox_dir / f"{seed_name}.html"
            if inbox_file.exists():
                inbox_file.unlink()
        session.commit()

    n = len(versions)
    print(f"\nimport-local: {n} real documents in {import_elapsed:.2f}s")
    print(f"  documents/minute: {n / import_elapsed * 60:.1f}" if import_elapsed else "")
    print(f"storage (backfill): {n} real documents in {backfill_elapsed:.2f}s")
    print(f"  documents/minute: {n / backfill_elapsed * 60:.1f}" if backfill_elapsed else "")
    print(f"page extraction: {n} real documents in {page_elapsed:.2f}s")
    print(f"  documents/minute: {n / page_elapsed * 60:.1f}" if page_elapsed else "")
    print(f"chunking: {n} real documents, {total_chunks} real chunks, {chunk_elapsed:.2f}s")
    print(f"  documents/minute: {n / chunk_elapsed * 60:.1f}" if chunk_elapsed else "")


def main() -> int:
    _measure_pdf_extraction()
    print()
    _measure_ingestion_and_chunking()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
