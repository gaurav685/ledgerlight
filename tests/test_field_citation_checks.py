"""Tests for ledgerlight.knowledge.field_citation_checks -- Phase 6
Correction 1 Sec4. Pure unit tests for the schema-type check; real DB
integration tests for the span-bounds and order-document-identity
checks (they need a real DocumentPage), built against the three real
field-citation findings this module exists to catch: THERMAX's own
detector-level fix lives in tests/test_extraction_adversarial.py; the
RELCAPITAL and BCG document-identity findings are regression-pinned
here."""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

import pytest
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentPage, DocumentVersion
from ledgerlight.knowledge.field_citation_checks import (
    seed_name_for_retrieval_url,
    verify_field_type_matches_schema,
    verify_order_document_names_company,
    verify_span_within_document,
)

# --- pure: verify_field_type_matches_schema -----------------------------------


def test_field_type_check_validates_a_real_iso_date() -> None:
    assert verify_field_type_matches_schema("AUD_RESIGN", "resignation_date", "2018-04-28") == (
        "validated"
    )


def test_field_type_check_fails_a_non_date_string_for_a_date_field() -> None:
    assert verify_field_type_matches_schema("AUD_RESIGN", "resignation_date", "soon") == "failed"


def test_field_type_check_validates_a_real_string_field() -> None:
    assert verify_field_type_matches_schema("AUD_RESIGN", "audit_firm", "KPMG") == "validated"


def test_field_type_check_fails_a_non_string_value_for_a_string_field() -> None:
    assert verify_field_type_matches_schema("AUD_RESIGN", "audit_firm", 123) == "failed"


def test_field_type_check_is_unverifiable_for_an_event_type_with_no_schema() -> None:
    """A real, disclosed gap: the 3 outcome-taxonomy event types have
    no declared field schema at all."""
    assert (
        verify_field_type_matches_schema("SEBI_ORDER_AGAINST_COMPANY", "order_document", None)
        == "unverifiable"
    )


def test_field_type_check_fails_a_field_name_not_in_the_schema() -> None:
    assert verify_field_type_matches_schema("AUD_RESIGN", "not_a_real_field", "x") == "failed"


def test_field_type_check_is_unverifiable_for_a_null_value() -> None:
    assert verify_field_type_matches_schema("AUD_RESIGN", "resignation_date", None) == (
        "unverifiable"
    )


# --- integration: verify_span_within_document ---------------------------------


def _make_document_version(session: Session, page_text: str) -> DocumentVersion:
    document = Document(
        source_id="sebi", source_key=f"test://citation/{uuid.uuid4()}", document_type="order"
    )
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key=f"raw/test/{uuid.uuid4()}.pdf",
        bytes=len(page_text),
        mime_type="application/pdf",
        retrieval_method="automated_fetch",
        retrieval_url="https://example.com/test.pdf",
        retrieved_at=dt.datetime.now(dt.UTC),
        known_at=dt.datetime.now(dt.UTC),
        known_at_basis="retrieved_at",
        tool_version="test/1",
    )
    session.add(version)
    session.flush()
    session.add(
        DocumentPage(
            version_id=version.id,
            page_number=1,
            raw_text=page_text,
            text_sha256=hashlib.sha256(page_text.encode("utf-8")).hexdigest(),
            char_count=len(page_text),
            extraction_method="text_layer",
            extractor_version="test/1",
        )
    )
    session.flush()
    return version


@pytest.mark.integration
def test_span_within_document_validates_a_real_in_bounds_span(db_session: Session) -> None:
    version = _make_document_version(db_session, "Resigned effective 2020-01-01.")
    assert verify_span_within_document(db_session, version.id, 1, 0, 8) == "validated"


@pytest.mark.integration
def test_span_within_document_fails_an_out_of_bounds_span(db_session: Session) -> None:
    version = _make_document_version(db_session, "Short text.")
    assert verify_span_within_document(db_session, version.id, 1, 0, 9999) == "failed"


@pytest.mark.integration
def test_span_within_document_is_unverifiable_for_a_zero_width_span(db_session: Session) -> None:
    """Real for every SEBI_ORDER_AGAINST_COMPANY order_document field
    -- "the whole document is the evidence", by design, not a defect."""
    version = _make_document_version(db_session, "Some real text.")
    assert verify_span_within_document(db_session, version.id, 1, 0, 0) == "unverifiable"


@pytest.mark.integration
def test_span_within_document_fails_a_nonexistent_page(db_session: Session) -> None:
    version = _make_document_version(db_session, "Some real text.")
    assert verify_span_within_document(db_session, version.id, 2, 0, 5) == "failed"


# --- integration: verify_order_document_names_company --------------------------


@pytest.mark.integration
def test_order_document_identity_validates_when_the_seed_name_is_present(
    db_session: Session,
) -> None:
    version = _make_document_version(
        db_session, "BEFORE THE SECURITIES AND EXCHANGE BOARD OF INDIA re GENSOL ENGINEERING."
    )
    assert (
        verify_order_document_names_company(db_session, version.id, "Gensol Engineering")
        == "validated"
    )


@pytest.mark.integration
def test_order_document_identity_fails_the_real_bcg_case(db_session: Session) -> None:
    """The real BCG finding: a Telangana High Court writ petition
    about an unrelated SEBI tribunal quorum matter -- "Brightcom"
    never appears in it at all."""
    version = _make_document_version(
        db_session,
        "HON'BLE MRS JUSTICE SUREPALLI NANDA WRIT PETITION No.450 of 2024 "
        "ORDER: Heard Mr. P. Vikram, learned Senior Counsel appearing for "
        "petitioners regarding SEBI tribunal quorum.",
    )
    assert (
        verify_order_document_names_company(db_session, version.id, "Brightcom Group") == "failed"
    )


@pytest.mark.integration
def test_order_document_identity_tolerates_a_real_pdf_whitespace_extraction_artifact(
    db_session: Session,
) -> None:
    """Real NCLT order text extracts with no spaces between words at
    all (confirmed: "INTHEMATTEROFM/S.BGRENERGYSYSTEMSLIMITED") -- a
    real, correct citation must not fail just because of that."""
    version = _make_document_version(
        db_session, "INTHEMATTEROFM/S.BGRENERGYSYSTEMSLIMITEDBETWEEN:RDCCONCRETE"
    )
    assert (
        verify_order_document_names_company(db_session, version.id, "BGR Energy Systems Limited")
        == "validated"
    )


@pytest.mark.integration
def test_order_document_identity_is_unverifiable_with_no_pages(db_session: Session) -> None:
    document = Document(
        source_id="sebi", source_key=f"test://citation/{uuid.uuid4()}", document_type="order"
    )
    db_session.add(document)
    db_session.flush()
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key=f"raw/test/{uuid.uuid4()}.pdf",
        bytes=0,
        mime_type="application/pdf",
        retrieval_method="automated_fetch",
        retrieval_url="https://example.com/test.pdf",
        retrieved_at=dt.datetime.now(dt.UTC),
        known_at=dt.datetime.now(dt.UTC),
        known_at_basis="retrieved_at",
        tool_version="test/1",
    )
    db_session.add(version)
    db_session.flush()
    assert verify_order_document_names_company(db_session, version.id, "Anything") == (
        "unverifiable"
    )


# --- seed_name_for_retrieval_url: against the real, frozen manifest -----------


def test_seed_name_resolves_the_real_bcg_manifest_entry() -> None:
    url = "https://www.sebi.gov.in/sebi_data/attachdocs/may-2024/1715669416537.pdf"
    assert seed_name_for_retrieval_url(url) == "Brightcom Group"


def test_seed_name_resolves_the_real_relcapital_manifest_entry() -> None:
    url = "https://www.sebi.gov.in/sebi_data/attachdocs/1288609225207.pdf"
    assert seed_name_for_retrieval_url(url) == "Reliance Capital"


def test_seed_name_is_none_for_an_unknown_url() -> None:
    assert seed_name_for_retrieval_url("https://example.com/not-a-real-document.pdf") is None
