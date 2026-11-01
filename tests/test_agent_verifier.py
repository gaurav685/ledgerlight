"""Tests for ledgerlight.agent.verifier -- Phase 4 Sec5. Pure unit
tests for the name/date/number/banned-language checks and
find_contradictions; real integration tests (DB + the real local NLI
model) for verify_claim/verify_dossier."""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

import pytest
from sqlalchemy.orm import Session

from ledgerlight.agent.models import Claim, Investigation
from ledgerlight.agent.render import RenderedDossier
from ledgerlight.agent.verifier import (
    check_banned_language,
    check_date_in_span,
    check_entailment,
    check_name_in_span,
    check_number_in_span,
    find_contradictions,
    verify_claim,
    verify_dossier,
)
from ledgerlight.db.models import Document, DocumentPage, DocumentVersion
from ledgerlight.knowledge.models import Company

COMPANY_A = uuid.uuid4()


def _make_investigation(session: Session) -> uuid.UUID:
    company = Company(id=uuid.uuid4(), display_name="Verifier Test Co")
    session.add(company)
    session.flush()
    investigation = Investigation(
        id=uuid.uuid4(),
        company_id=company.id,
        as_of=dt.date(2020, 1, 1),
        requested_by="test",
        budget_config={},
        usage={},
    )
    session.add(investigation)
    session.flush()
    return investigation.id


def _claim(
    claim_type: str,
    payload: dict[str, object],
    evidence: list[dict[str, object]] | None = None,
    claim_id: uuid.UUID | None = None,
) -> Claim:
    claim = Claim(
        id=claim_id or uuid.uuid4(),
        investigation_id=uuid.uuid4(),
        claim_type=claim_type,
        payload=payload,
        evidence=evidence or [],
    )
    return claim


# --- pure checks --------------------------------------------------------------


def test_check_name_in_span_is_case_and_whitespace_insensitive() -> None:
    result = check_name_in_span("The   Statutory   Auditor,  XYZ & Co LLP", "xyz & co llp")
    assert result.passed


def test_check_name_in_span_fails_on_a_real_name_mismatch() -> None:
    result = check_name_in_span("The statutory auditor was ABC LLP.", "XYZ & Co LLP")
    assert not result.passed


def test_check_date_in_span_matches_iso_date() -> None:
    result = check_date_in_span("Effective 2018-04-28, the auditor resigned.", dt.date(2018, 4, 28))
    assert result.passed


def test_check_date_in_span_matches_dd_mm_yyyy() -> None:
    result = check_date_in_span("with effect from 28/04/2018", dt.date(2018, 4, 28))
    assert result.passed


def test_check_date_in_span_does_not_accept_mm_dd_as_an_alternate_reading() -> None:
    """The real adversarial case: '02/03/2020' is DD/MM/YYYY = 2 March
    2020 in this project's real documents. A claim of '3 Feb 2020'
    (the US MM/DD reading) must NOT pass -- that would be exactly the
    DD/MM-vs-MM/DD bug Sec9 requires catching."""
    result = check_date_in_span("dated 02/03/2020", dt.date(2020, 2, 3))
    assert not result.passed


def test_check_date_in_span_matches_month_name_format() -> None:
    result = check_date_in_span(
        "resigned on 28 April 2018 with immediate effect", dt.date(2018, 4, 28)
    )
    assert result.passed


def test_check_date_in_span_fails_on_wrong_date_off_by_one() -> None:
    result = check_date_in_span("dated 2018-04-28", dt.date(2018, 4, 29))
    assert not result.passed


def test_check_number_in_span_matches_crore_to_lakh() -> None:
    result = check_number_in_span("The penalty was Rs. 500 lakh.", 5.0, "crore")
    assert result.passed


def test_check_number_in_span_matches_exact_crore() -> None:
    result = check_number_in_span("The penalty was Rs. 5 crore.", 5.0, "crore")
    assert result.passed


def test_check_number_in_span_distinguishes_percent_from_percentage_points() -> None:
    result = check_number_in_span("Revenue grew by 5%.", 5.0, "percent")
    assert result.passed


def test_check_number_in_span_fails_on_a_real_numeric_mismatch() -> None:
    result = check_number_in_span("The penalty was Rs. 3 crore.", 5.0, "crore")
    assert not result.passed


def test_check_banned_language_fails_on_an_unquoted_banned_term() -> None:
    result = check_banned_language("The company committed fraud against investors.")
    assert not result.passed


def test_check_banned_language_allows_a_short_attributed_quote() -> None:
    result = check_banned_language('The SEBI order states: "the company committed fraud here."')
    assert result.passed


def test_check_banned_language_fails_on_a_long_quote_even_if_attributed() -> None:
    long_quote = " ".join(["word"] * 20) + " fraud"
    result = check_banned_language(f'The order states: "{long_quote}"')
    assert not result.passed


def test_check_banned_language_passes_with_no_banned_terms() -> None:
    result = check_banned_language("The auditor resigned effective the stated date.")
    assert result.passed


def test_find_contradictions_detects_same_event_type_different_known_at() -> None:
    claims = [
        _claim("event", {"event_type_code": "IBBI_CIRP_ADMISSION", "known_at": "2020-01-01"}),
        _claim("event", {"event_type_code": "IBBI_CIRP_ADMISSION", "known_at": "2020-06-01"}),
    ]
    groups = find_contradictions(claims)
    assert len(groups) == 1
    assert len(groups[0].claim_ids) == 2


def test_find_contradictions_is_empty_when_known_ats_agree() -> None:
    claims = [
        _claim("event", {"event_type_code": "IBBI_CIRP_ADMISSION", "known_at": "2020-01-01"}),
        _claim("event", {"event_type_code": "IBBI_CIRP_ADMISSION", "known_at": "2020-01-01"}),
    ]
    assert find_contradictions(claims) == []


# --- real NLI entailment (slow: loads the real local model) ------------------


@pytest.mark.network
def test_check_entailment_passes_for_a_real_entailed_sentence() -> None:
    result = check_entailment(
        "The statutory auditor resigned on 28 April 2018.", "The auditor resigned."
    )
    assert result.passed


@pytest.mark.network
def test_check_entailment_fails_for_an_unrelated_sentence() -> None:
    result = check_entailment(
        "The company reported record profits this year.", "The auditor resigned."
    )
    assert not result.passed


# --- integration: verify_claim / verify_dossier -------------------------------


def _make_document_version(
    session: Session, page_text: str, known_at: dt.datetime
) -> DocumentVersion:
    document = Document(
        source_id="sebi", source_key=f"test://verifier/{uuid.uuid4()}", document_type="order"
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
        retrieved_at=known_at,
        known_at=known_at,
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
def test_verify_claim_passes_with_a_real_resolving_citation(db_session: Session) -> None:
    known_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    version = _make_document_version(db_session, "Resigned effective 2020-01-01.", known_at)
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="event",
        payload={"event_type_code": "AUD_RESIGN", "known_at": "2020-01-01T00:00:00+00:00"},
        evidence=[
            {
                "document_version_id": str(version.id),
                "page_number": 1,
                "char_start": 0,
                "char_end": 30,
            }
        ],
    )
    db_session.add(claim)
    db_session.flush()

    result = verify_claim(db_session, claim, as_of=dt.date(2020, 2, 1))
    assert result.passed


@pytest.mark.integration
def test_verify_claim_fails_with_a_missing_citation(db_session: Session) -> None:
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="event",
        payload={"event_type_code": "AUD_RESIGN", "known_at": "2020-01-01T00:00:00+00:00"},
        evidence=[
            {
                "document_version_id": str(uuid.uuid4()),
                "page_number": 1,
                "char_start": 0,
                "char_end": 5,
            }
        ],
    )
    db_session.add(claim)
    db_session.flush()

    result = verify_claim(db_session, claim, as_of=dt.date(2020, 2, 1))
    assert not result.passed


@pytest.mark.integration
def test_verify_claim_fails_with_offsets_out_of_range(db_session: Session) -> None:
    known_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    version = _make_document_version(db_session, "Short.", known_at)
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="event",
        payload={"event_type_code": "AUD_RESIGN", "known_at": "2020-01-01T00:00:00+00:00"},
        evidence=[
            {
                "document_version_id": str(version.id),
                "page_number": 1,
                "char_start": 0,
                "char_end": 9999,
            }
        ],
    )
    db_session.add(claim)
    db_session.flush()

    result = verify_claim(db_session, claim, as_of=dt.date(2020, 2, 1))
    assert not result.passed


@pytest.mark.integration
def test_verify_claim_fails_with_a_future_known_evidence_span(db_session: Session) -> None:
    """A real adversarial case: the evidence's own known_at is AFTER
    the investigation's as_of -- a future-known span relative to
    as_of, which must fail, never silently pass."""
    known_at = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    version = _make_document_version(db_session, "Resigned effective 2025-01-01.", known_at)
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="event",
        payload={"event_type_code": "AUD_RESIGN", "known_at": "2025-01-01T00:00:00+00:00"},
        evidence=[
            {
                "document_version_id": str(version.id),
                "page_number": 1,
                "char_start": 0,
                "char_end": 30,
            }
        ],
    )
    db_session.add(claim)
    db_session.flush()

    # get_evidence's own as_of filter means this resolves to None entirely
    # (not merely a failed point_in_time check) -- either way, the claim
    # must fail, which is exactly what this test pins.
    result = verify_claim(db_session, claim, as_of=dt.date(2020, 1, 1))
    assert not result.passed


@pytest.mark.integration
def test_verify_dossier_flags_a_sentence_with_no_claim_id(db_session: Session) -> None:
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="limitation",
        payload={"text": "A real limitation."},
        evidence=[],
    )
    db_session.add(claim)
    db_session.flush()

    rendered = RenderedDossier(
        sections={"limitations": ["A real limitation.", "An orphan sentence."]},
        claim_id_map={"limitations:0": [str(claim.id)]},
    )
    result = verify_dossier(db_session, [claim], rendered, as_of=dt.date(2020, 1, 1))
    assert not result.passed
    assert any("limitations:1" in f for f in result.sentence_mapping_failures)


@pytest.mark.integration
def test_verify_dossier_flags_banned_language(db_session: Session) -> None:
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="limitation",
        payload={"text": "The company committed fraud."},
        evidence=[],
    )
    db_session.add(claim)
    db_session.flush()

    rendered = RenderedDossier(
        sections={"limitations": ["The company committed fraud."]},
        claim_id_map={"limitations:0": [str(claim.id)]},
    )
    result = verify_dossier(db_session, [claim], rendered, as_of=dt.date(2020, 1, 1))
    assert not result.passed
    assert result.banned_language_failures
