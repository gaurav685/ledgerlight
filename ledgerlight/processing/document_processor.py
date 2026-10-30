"""Top-level per-version document processing: MIME-sniff, dispatch to the
right extractor, run inside a timeout-bounded subprocess, and persist
DocumentPage rows (or quarantine price_bars rows for bhavcopy).

Determinism: re-processing the same version with the same
EXTRACTOR_VERSION must produce byte-identical raw_text — guaranteed here
because every extractor is a pure function of the input bytes (no
wall-clock, no random IDs, no filesystem paths baked into the output).
Bumping an extractor's version produces new DocumentPage rows; the
unique constraint on (version_id, page_number, extractor_version) means
old rows for the previous extractor_version are never touched, let alone
deleted — see ledgerlight/db/models.py.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.db.models import DocumentPage, DocumentVersion
from ledgerlight.processing import html as html_mod
from ledgerlight.processing import pdf as pdf_mod
from ledgerlight.processing.limits import LimitExceededError, ProcessingLimits
from ledgerlight.processing.mime_sniff import find_pdf_offset, is_html, is_pdf, sniff_mime
from ledgerlight.processing.ocr import OCR_ENGINE_NAME, OcrUnavailableError, run_ocr
from ledgerlight.processing.runner import run_with_timeout


@dataclass
class PageResult:
    page_number: int
    raw_text: str
    extraction_method: str
    ocr_engine: str | None = None
    ocr_engine_version: str | None = None
    ocr_mean_confidence: float | None = None


@dataclass
class ProcessingOutcome:
    pages_created: int = 0
    pages_already_present: int = 0
    ocr_pages: int = 0
    mime_type: str = ""
    skipped_reason: str | None = None


def _process_pdf_worker(body: bytes, limits: ProcessingLimits) -> list[PageResult]:
    """Module-level (picklable) function run inside a subprocess via
    run_with_timeout — the entire per-document budget (extraction + any
    OCR) is bounded by one timeout."""
    pages = pdf_mod.extract_pdf_pages(body, limits)
    results: list[PageResult] = []
    for page in pages:
        if not page.needs_ocr:
            results.append(
                PageResult(
                    page_number=page.page_number,
                    raw_text=page.raw_text,
                    extraction_method="text_layer",
                )
            )
            continue

        try:
            image = pdf_mod.render_page_to_rgb_array(body, page.page_number)
            ocr_text, confidence = run_ocr(image)
        except OcrUnavailableError:
            # OCR engine not installed in this environment — keep whatever
            # native text layer there was rather than failing the page.
            results.append(
                PageResult(
                    page_number=page.page_number,
                    raw_text=page.raw_text,
                    extraction_method="text_layer",
                )
            )
            continue

        from ledgerlight.processing.ocr import _engine_version

        results.append(
            PageResult(
                page_number=page.page_number,
                raw_text=ocr_text or page.raw_text,
                extraction_method="ocr",
                ocr_engine=OCR_ENGINE_NAME,
                ocr_engine_version=_engine_version(),
                ocr_mean_confidence=confidence,
            )
        )
    return results


def _process_html_worker(body: bytes) -> list[PageResult]:
    text = html_mod.extract_html_text(body)
    return [PageResult(page_number=1, raw_text=text, extraction_method="html")]


def process_version(
    session: Session,
    body: bytes,
    version: DocumentVersion,
    limits: ProcessingLimits,
) -> ProcessingOutcome:
    outcome = ProcessingOutcome()

    if len(body) > limits.max_file_size_bytes:
        raise LimitExceededError(f"version {version.id}: {len(body)} bytes > max_file_size_bytes")

    mime = sniff_mime(body)
    outcome.mime_type = mime

    if is_pdf(mime):
        # A real PDF signature may sit a few bytes into the body (see
        # mime_sniff.find_pdf_offset's docstring for the real case this
        # handles) -- slice it off so the PDF extractor sees a clean PDF,
        # not a wrapper-stub-plus-PDF blob.
        pdf_offset = find_pdf_offset(body) or 0
        pdf_body = body[pdf_offset:]
        extractor_version = pdf_mod.EXTRACTOR_VERSION
        page_results = run_with_timeout(
            _process_pdf_worker, (pdf_body, limits), limits.per_document_timeout_seconds
        )
    elif is_html(mime):
        extractor_version = html_mod.EXTRACTOR_VERSION
        page_results = run_with_timeout(
            _process_html_worker, (body,), limits.per_document_timeout_seconds
        )
    else:
        outcome.skipped_reason = f"no page-text extractor for mime type {mime!r}"
        return outcome

    for pr in page_results:
        existing = session.scalar(
            select(DocumentPage).where(
                DocumentPage.version_id == version.id,
                DocumentPage.page_number == pr.page_number,
                DocumentPage.extractor_version == extractor_version,
            )
        )
        if existing is not None:
            outcome.pages_already_present += 1
            continue

        # Postgres text columns reject NUL bytes outright -- a hard DB
        # constraint, not a style choice. The real cause for a PDF is
        # handled above (find_pdf_offset); this is a defensive floor so
        # one unexpected NUL from any other source never crashes a whole
        # batch run. Stripped before hashing so text_sha256 matches what
        # is actually stored.
        raw_text = pr.raw_text.replace("\x00", "")
        text_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        session.add(
            DocumentPage(
                version_id=version.id,
                page_number=pr.page_number,
                raw_text=raw_text,
                text_sha256=text_sha256,
                char_count=len(raw_text),
                extraction_method=pr.extraction_method,
                ocr_engine=pr.ocr_engine,
                ocr_engine_version=pr.ocr_engine_version,
                ocr_mean_confidence=pr.ocr_mean_confidence,
                extractor_version=extractor_version,
            )
        )
        outcome.pages_created += 1
        if pr.extraction_method == "ocr":
            outcome.ocr_pages += 1

    session.commit()
    return outcome
