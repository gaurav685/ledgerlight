"""Tests for ledgerlight.processing.document_processor -- specifically
the real bug found 2026-10-30 (an IBBI order URL): a tiny HTML/JS
"Loading..." stub concatenated directly in front of a complete, valid
PDF in the same response body. Before the fix, the HTML extractor ran
on the whole blob and leaked raw PDF binary (incl. NUL bytes, which
Postgres rejects outright) into DocumentPage.raw_text instead of real
page text. See tests/test_mime_sniff.py for the pure sniffing-logic
tests; this file verifies process_version end-to-end recovers the real
PDF content.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pymupdf
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentPage, DocumentVersion
from ledgerlight.processing.document_processor import process_version
from ledgerlight.processing.limits import ProcessingLimits

pytestmark = pytest.mark.integration


def _real_one_page_pdf_bytes(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def _make_version(session: Session, object_key: str) -> DocumentVersion:
    document = Document(source_id="ibbi", source_key=f"https://example.test/{object_key}")
    session.add(document)
    session.flush()
    now = dt.datetime.now(dt.UTC)
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key=object_key,
        bytes=0,
        retrieval_method="automated_fetch",
        retrieval_url=f"https://example.test/{object_key}",
        retrieved_at=now,
        known_at=now,
        known_at_basis="retrieved_at",
        tool_version="test",
    )
    session.add(version)
    session.flush()
    return version


def test_html_stub_plus_embedded_pdf_recovers_real_text(db_session: Session) -> None:
    real_text = "In the matter of Test Seed Company Ltd. Order dated 2026-10-30."
    pdf_bytes = _real_one_page_pdf_bytes(real_text)
    stub = (
        b'<html><head><script src="jquery.js"></script></head>'
        b'<div id="loading">Loading...</div>\n'
    )
    body = stub + pdf_bytes

    version = _make_version(db_session, f"test/{uuid.uuid4().hex}.pdf")
    outcome = process_version(db_session, body, version, ProcessingLimits())

    assert outcome.mime_type == "application/pdf"
    assert outcome.pages_created == 1

    page = db_session.scalar(select(DocumentPage).where(DocumentPage.version_id == version.id))
    assert page is not None
    assert "\x00" not in page.raw_text
    assert "Test Seed Company" in page.raw_text
    assert page.extraction_method == "text_layer"
