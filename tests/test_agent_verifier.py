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
from ledgerlight.agent.render import RenderedDossier, event_claim_sentence
from ledgerlight.agent.verifier import (
    check_banned_language,
    check_date_in_span,
    check_entailment,
    check_name_in_span,
    check_number_in_span,
    check_sentence_values_in_claims,
    check_timeline_claim_count,
    find_contradictions,
    verify_claim,
    verify_dossier,
)
from ledgerlight.db.models import Document, DocumentPage, DocumentVersion
from ledgerlight.knowledge.models import Company, Filing

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


def _event_claim(known_at_iso: str) -> Claim:
    return Claim(
        investigation_id=uuid.uuid4(),
        claim_type="event",
        payload={
            "event_type_code": "AUD_RESIGN",
            "tier": "VERIFIED",
            "known_at": known_at_iso,
        },
        evidence=[],
    )


def test_check_sentence_values_in_claims_passes_with_the_correct_ist_date() -> None:
    """Phase 6 Correction 2 §3.2's real IST prose date, checked against
    the exact real sentence `event_claim_sentence` produces -- proves
    the `_flatten_payload_numbers` IST widening does not merely avoid
    false failures, it genuinely recognises the correct date."""
    claim = _event_claim("2019-06-03T20:00:00+00:00")  # 4 June 2019 in IST
    sentence = event_claim_sentence(claim)
    assert "4 June 2019 (IST)" in sentence
    result = check_sentence_values_in_claims(sentence, [claim])
    assert result.passed


def test_check_sentence_values_in_claims_fails_when_the_ist_date_does_not_match_the_claim() -> None:
    """Correction 2 §3's ADDENDUM check: the IST-widening fix in
    `_flatten_payload_numbers` must not have loosened the check so far
    that a WRONG prose date slips through. Claim's real IST date is 4
    June 2019; the rendered sentence is deliberately corrupted to claim
    5 June instead -- this must still fail, exactly as the pre-IST
    raw-ISO-string prose would have."""
    claim = _event_claim("2019-06-03T20:00:00+00:00")  # 4 June 2019 in IST
    correct_sentence = event_claim_sentence(claim)
    wrong_sentence = correct_sentence.replace("4 June 2019", "5 June 2019")
    assert wrong_sentence != correct_sentence
    result = check_sentence_values_in_claims(wrong_sentence, [claim])
    assert not result.passed
    assert "5.0" in result.detail


def test_check_sentence_values_in_claims_fails_on_a_stray_unrelated_number() -> None:
    """A number with no date-prefix structure and no match anywhere in
    the claim's own payload must still fail -- the check's core,
    original purpose (real insurance against a renderer introducing a
    number no real claim actually carries), unaffected by the IST
    widening added for dates."""
    claim = _event_claim("2019-06-03T20:00:00+00:00")
    sentence = event_claim_sentence(claim) + " The penalty was 999 crore."
    result = check_sentence_values_in_claims(sentence, [claim])
    assert not result.passed
    assert "999.0" in result.detail


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
def test_verify_claim_passes_a_timeline_entry_with_a_real_resolving_version(
    db_session: Session,
) -> None:
    """A real bug found by Sec11's real agent-eval run: claims.py's own
    docstring documents timeline_entry as sharing the same empty-
    evidence exemption as risk_signal/limitation, but
    EVIDENCE_EXEMPT_CLAIM_TYPES never included it -- every real
    timeline_entry claim failed as unsupported until this was fixed.
    No evidence SPAN is needed, but a real, resolving version_id with
    a matching known_at is -- never a blanket exemption."""
    known_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    version = _make_document_version(db_session, "A real filing.", known_at)
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="timeline_entry",
        payload={
            "kind": "filing",
            "label": "sebi:order",
            "known_at": known_at.isoformat(),
            "version_id": str(version.id),
        },
        evidence=[],
    )
    db_session.add(claim)
    db_session.flush()

    result = verify_claim(db_session, claim, as_of=dt.date(2020, 2, 1))
    assert result.passed


@pytest.mark.integration
def test_verify_claim_fails_a_timeline_entry_with_a_wrong_known_at(db_session: Session) -> None:
    """The real adversarial case this fix closes: a timeline_entry
    claiming a known_at that does not match its own real
    document_version's known_at must fail, never silently pass just
    because there was no evidence span to check against."""
    known_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    version = _make_document_version(db_session, "A real filing.", known_at)
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="timeline_entry",
        payload={
            "kind": "filing",
            "label": "sebi:order",
            "known_at": "2019-06-15T00:00:00+00:00",  # wrong vs real known_at 2020-01-01
            "version_id": str(version.id),
        },
        evidence=[],
    )
    db_session.add(claim)
    db_session.flush()

    result = verify_claim(db_session, claim, as_of=dt.date(2020, 2, 1))
    assert not result.passed


@pytest.mark.integration
def test_verify_claim_fails_a_timeline_entry_with_a_nonexistent_version(
    db_session: Session,
) -> None:
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="timeline_entry",
        payload={
            "kind": "filing",
            "label": "sebi:order",
            "known_at": "2020-01-01T00:00:00+00:00",
            "version_id": str(uuid.uuid4()),  # never a real document_version
        },
        evidence=[],
    )
    db_session.add(claim)
    db_session.flush()

    result = verify_claim(db_session, claim, as_of=dt.date(2020, 2, 1))
    assert not result.passed


@pytest.mark.integration
def test_verify_claim_skips_date_in_span_for_a_metric_claim(db_session: Session) -> None:
    """A real bug found by Sec11's real agent-eval run: a care_rating
    claim's real evidence span is deliberately just the rating
    symbol's own regex capture group (never a date-bearing sentence),
    so date_in_span could never pass for it -- scoped to event claims
    only. A metric claim whose span has no date must still pass
    overall if its name/number check passes."""
    known_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    version = _make_document_version(db_session, "BBB", known_at)
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="metric",
        payload={
            "name": "care_rating",
            "value": "BBB",
            "unit": "CARE_rating_symbol",
            "known_at": "2020-01-01T00:00:00+00:00",
        },
        evidence=[
            {
                "document_version_id": str(version.id),
                "page_number": 1,
                "char_start": 0,
                "char_end": 3,
            }
        ],
    )
    db_session.add(claim)
    db_session.flush()

    result = verify_claim(db_session, claim, as_of=dt.date(2020, 2, 1))
    assert result.passed
    assert not any(c.check_name == "date_in_span" for c in result.checks)


@pytest.mark.integration
def test_verify_claim_fails_a_metric_claim_with_a_wrong_known_at(db_session: Session) -> None:
    """The real adversarial case Phase 5's own preflight requires:
    scoping date_in_span away from metric claims must not create a
    blind spot for a wrong date. known_at_matches_evidence (the check
    that now covers rating dates) must still fail a care_rating claim
    whose claimed known_at does not equal its real evidence
    document's own known_at, even though the span text and rating
    symbol are both otherwise correct."""
    known_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    version = _make_document_version(db_session, "BBB", known_at)
    investigation_id = _make_investigation(db_session)
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="metric",
        payload={
            "name": "care_rating",
            "value": "BBB",
            "unit": "CARE_rating_symbol",
            "known_at": "2019-06-15T00:00:00+00:00",  # wrong vs real known_at 2020-01-01
        },
        evidence=[
            {
                "document_version_id": str(version.id),
                "page_number": 1,
                "char_start": 0,
                "char_end": 3,
            }
        ],
    )
    db_session.add(claim)
    db_session.flush()

    result = verify_claim(db_session, claim, as_of=dt.date(2020, 2, 1))
    assert not result.passed
    assert any(c.check_name == "known_at_matches_evidence" and not c.passed for c in result.checks)


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


# --- Phase 6 Correction 1 Sec2.4/Sec2.5: independent timeline-count check ----
#
# The real "0 real filings known as of" bug (see
# docs/phase-6/phase-6-correction-1.md Sec2) reached FINALISE because
# nothing independently re-derived the dossier's own claimed filing
# count. `check_timeline_claim_count` closes that gap: these tests
# pin it directly, including the synthetic "GATHER dropped a result"
# case the brief calls for -- a real filing exists (confirmed via a
# real `filings`/`document_versions` row), but no claim was ever made
# for it, which must fail closed rather than silently under-report.


def _make_company_and_investigation(
    session: Session, as_of: dt.date
) -> tuple[uuid.UUID, uuid.UUID]:
    company = Company(id=uuid.uuid4(), display_name="Timeline Count Test Co")
    session.add(company)
    session.flush()
    investigation = Investigation(
        id=uuid.uuid4(),
        company_id=company.id,
        as_of=as_of,
        requested_by="test",
        budget_config={},
        usage={},
    )
    session.add(investigation)
    session.flush()
    return company.id, investigation.id


def _make_real_filing(
    session: Session, company_id: uuid.UUID, known_at: dt.datetime
) -> DocumentVersion:
    version = _make_document_version(session, "A real filing document.", known_at)
    session.add(
        Filing(company_id=company_id, version_id=version.id, link_method="manual", confidence=1.0)
    )
    session.flush()
    return version


def _timeline_claim(investigation_id: uuid.UUID, version: DocumentVersion) -> Claim:
    claim = Claim(
        investigation_id=investigation_id,
        claim_type="timeline_entry",
        payload={
            "kind": "filing",
            "label": "test:filing",
            "known_at": version.known_at.isoformat(),
            "version_id": str(version.id),
        },
        evidence=[],
    )
    return claim


@pytest.mark.integration
def test_check_timeline_claim_count_matches_when_every_real_filing_has_a_claim(
    db_session: Session,
) -> None:
    as_of = dt.date(2020, 6, 1)
    company_id, investigation_id = _make_company_and_investigation(db_session, as_of)
    versions = [
        _make_real_filing(db_session, company_id, dt.datetime(2020, 1, d, tzinfo=dt.UTC))
        for d in (1, 2, 3)
    ]
    claims = [_timeline_claim(investigation_id, v) for v in versions]
    db_session.add_all(claims)
    db_session.flush()

    claim_results = [verify_claim(db_session, c, as_of) for c in claims]
    mismatch = check_timeline_claim_count(db_session, claims, claim_results, as_of)
    assert mismatch is None


@pytest.mark.integration
def test_check_timeline_claim_count_catches_a_gather_dropped_filing(db_session: Session) -> None:
    """The real synthetic regression the brief asks for: three real
    filings exist (real `filings`/`document_versions` rows), but
    GATHER only ever produced claims for two of them -- the third was
    silently dropped. This must fail closed, never pass as if only
    two real filings existed."""
    as_of = dt.date(2020, 6, 1)
    company_id, investigation_id = _make_company_and_investigation(db_session, as_of)
    versions = [
        _make_real_filing(db_session, company_id, dt.datetime(2020, 1, d, tzinfo=dt.UTC))
        for d in (1, 2, 3)
    ]
    # version[2] (the 3rd real filing) is deliberately dropped here
    dropped_claims = [_timeline_claim(investigation_id, v) for v in versions[:2]]
    db_session.add_all(dropped_claims)
    db_session.flush()

    claim_results = [verify_claim(db_session, c, as_of) for c in dropped_claims]
    mismatch = check_timeline_claim_count(db_session, dropped_claims, claim_results, as_of)
    assert mismatch is not None
    assert "2" in mismatch and "3" in mismatch


@pytest.mark.integration
def test_verify_dossier_fails_closed_when_a_real_filing_claim_is_dropped(
    db_session: Session,
) -> None:
    """Full-pipeline wiring: the same dropped-claim scenario must also
    make `verify_dossier(...).passed` False, via the new
    `count_mismatches` field -- not just the standalone check."""
    as_of = dt.date(2020, 6, 1)
    company_id, investigation_id = _make_company_and_investigation(db_session, as_of)
    versions = [
        _make_real_filing(db_session, company_id, dt.datetime(2020, 1, d, tzinfo=dt.UTC))
        for d in (1, 2, 3)
    ]
    dropped_claims = [_timeline_claim(investigation_id, v) for v in versions[:2]]
    db_session.add_all(dropped_claims)
    db_session.flush()

    rendered = RenderedDossier(
        sections={
            "chronology": [
                f"A real test:filing filing was known as of {v.known_at.isoformat()}."
                for v in versions[:2]
            ]
        },
        claim_id_map={f"chronology:{i}": [str(c.id)] for i, c in enumerate(dropped_claims)},
    )
    result = verify_dossier(db_session, dropped_claims, rendered, as_of)
    assert not result.passed
    assert result.count_mismatches
