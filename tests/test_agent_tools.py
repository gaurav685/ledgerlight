"""Tests for ledgerlight.agent.tools -- Phase 4 Sec3's 7 read-only
tools. Real integration tests against the real local DB (rolled back
per test, via the db_session fixture), building small, controlled
real fixtures so each tool's point-in-time filter is directly
checkable rather than depending on real production data that can
shift over time."""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.agent.tools import (
    ToolEnvelope,
    get_entity_history,
    get_events,
    get_evidence,
    get_outcomes_context,
    get_risk_score,
    get_timeline,
)
from ledgerlight.db.models import Document, DocumentPage, DocumentVersion
from ledgerlight.knowledge.models import Company, Event, EventField, EventType, Filing

pytestmark = pytest.mark.integration


def _make_company(session: Session, name: str) -> uuid.UUID:
    company = Company(id=uuid.uuid4(), display_name=name)
    session.add(company)
    session.flush()
    return company.id


def _make_document_version(
    session: Session, page_text: str, known_at: dt.datetime, source_id: str = "sebi"
) -> DocumentVersion:
    document = Document(
        source_id=source_id,
        source_key=f"test://agent-tools/{uuid.uuid4()}",
        document_type="announcement",
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


def _make_filing(session: Session, version_id: uuid.UUID, company_id: uuid.UUID) -> None:
    session.add(
        Filing(
            version_id=version_id,
            company_id=company_id,
            link_method="manual",
            confidence=1.0,
        )
    )
    session.flush()


def _make_event(
    session: Session,
    company_id: uuid.UUID,
    event_type_code: str,
    known_at: dt.datetime,
    status: str,
    evidence_version_id: uuid.UUID,
) -> uuid.UUID:
    event_type = session.scalar(select(EventType).where(EventType.code == event_type_code))
    assert event_type is not None, f"real event type {event_type_code!r} must already exist"
    event = Event(
        event_type_id=event_type.id,
        company_id=company_id,
        known_at=known_at,
        severity="medium",
        status=status,
        detector_name="test",
        detector_version="1",
        confidence=0.9,
    )
    session.add(event)
    session.flush()
    session.add(
        EventField(
            event_id=event.id,
            field_name="test_field",
            value_json="test",
            evidence_version_id=evidence_version_id,
            evidence_page=1,
            evidence_char_start=0,
            evidence_char_end=5,
            extractor_name="test",
            extractor_version="1",
            confidence=0.9,
            validation_status="validated",
        )
    )
    session.flush()
    return event.id


def test_tool_envelope_is_frozen_and_marked_untrusted(db_session: Session) -> None:
    company_id = _make_company(db_session, "Envelope Test Co")
    result = get_timeline(db_session, company_id, dt.date(2020, 1, 1))
    assert isinstance(result, ToolEnvelope)
    assert result.untrusted is True
    with pytest.raises(ValidationError):
        result.untrusted = False  # type: ignore[assignment]


def test_get_evidence_resolves_the_real_exact_span(db_session: Session) -> None:
    known_at = dt.datetime(2020, 1, 15, tzinfo=dt.UTC)
    version = _make_document_version(db_session, "Hello world, this is real text.", known_at)
    result = get_evidence(db_session, version.id, 1, 6, 11, as_of=dt.date(2020, 1, 20))
    assert result.data is not None
    assert result.data.text == "world"


def test_get_evidence_returns_none_when_not_yet_known_as_of(db_session: Session) -> None:
    known_at = dt.datetime(2020, 6, 1, tzinfo=dt.UTC)
    version = _make_document_version(db_session, "Future knowledge span.", known_at)
    result = get_evidence(db_session, version.id, 1, 0, 6, as_of=dt.date(2020, 1, 1))
    assert result.data is None


def test_get_evidence_returns_none_for_out_of_range_offsets(db_session: Session) -> None:
    known_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    version = _make_document_version(db_session, "Short.", known_at)
    result = get_evidence(db_session, version.id, 1, 0, 9999, as_of=dt.date(2020, 1, 10))
    assert result.data is None


def test_get_evidence_returns_none_for_a_nonexistent_page(db_session: Session) -> None:
    result = get_evidence(db_session, uuid.uuid4(), 1, 0, 5, as_of=dt.date(2020, 1, 1))
    assert result.data is None


def test_get_events_excludes_events_known_after_as_of(db_session: Session) -> None:
    company_id = _make_company(db_session, "Events PIT Co")
    version = _make_document_version(
        db_session, "AUD_RESIGN evidence text.", dt.datetime(2019, 1, 1, tzinfo=dt.UTC)
    )
    known_at = dt.datetime(2020, 6, 15, tzinfo=dt.UTC)
    _make_event(db_session, company_id, "AUD_RESIGN", known_at, "candidate", version.id)

    before = get_events(db_session, company_id, as_of=dt.date(2020, 1, 1))
    after = get_events(db_session, company_id, as_of=dt.date(2020, 12, 31))
    assert len(before.data) == 0
    assert len(after.data) == 1


def test_get_events_normalizes_tier_from_status(db_session: Session) -> None:
    company_id = _make_company(db_session, "Tier Co")
    version = _make_document_version(db_session, "evidence", dt.datetime(2020, 1, 1, tzinfo=dt.UTC))
    known_at = dt.datetime(2020, 1, 2, tzinfo=dt.UTC)
    _make_event(db_session, company_id, "AUD_RESIGN", known_at, "verified", version.id)

    result = get_events(db_session, company_id, as_of=dt.date(2020, 1, 10))
    assert len(result.data) == 1
    assert result.data[0].tier == "VERIFIED"
    assert len(result.data[0].evidence) == 1


def test_get_events_excludes_rejected_and_needs_review(db_session: Session) -> None:
    company_id = _make_company(db_session, "Rejected Co")
    version = _make_document_version(db_session, "evidence", dt.datetime(2020, 1, 1, tzinfo=dt.UTC))
    known_at = dt.datetime(2020, 1, 2, tzinfo=dt.UTC)
    _make_event(db_session, company_id, "AUD_RESIGN", known_at, "rejected", version.id)
    _make_event(db_session, company_id, "AUD_RESIGN", known_at, "needs_review", version.id)

    result = get_events(db_session, company_id, as_of=dt.date(2020, 1, 10))
    assert result.data == []


def test_get_events_filters_by_event_type_code(db_session: Session) -> None:
    company_id = _make_company(db_session, "Filter Co")
    version = _make_document_version(db_session, "evidence", dt.datetime(2020, 1, 1, tzinfo=dt.UTC))
    known_at = dt.datetime(2020, 1, 2, tzinfo=dt.UTC)
    _make_event(db_session, company_id, "AUD_RESIGN", known_at, "candidate", version.id)

    matching = get_events(
        db_session, company_id, as_of=dt.date(2020, 1, 10), event_type_code="AUD_RESIGN"
    )
    non_matching = get_events(
        db_session, company_id, as_of=dt.date(2020, 1, 10), event_type_code="KMP_EXIT"
    )
    assert len(matching.data) == 1
    assert non_matching.data == []


def test_get_timeline_includes_events_and_filings_sorted(db_session: Session) -> None:
    company_id = _make_company(db_session, "Timeline Co")
    early_version = _make_document_version(
        db_session, "early filing", dt.datetime(2019, 1, 1, tzinfo=dt.UTC)
    )
    _make_filing(db_session, early_version.id, company_id)
    late_version = _make_document_version(
        db_session, "late filing", dt.datetime(2020, 6, 1, tzinfo=dt.UTC)
    )
    _make_filing(db_session, late_version.id, company_id)

    result = get_timeline(db_session, company_id, as_of=dt.date(2021, 1, 1))
    known_ats = [entry.known_at for entry in result.data]
    assert known_ats == sorted(known_ats)
    assert len(result.data) >= 2


def test_get_timeline_excludes_filings_known_after_as_of(db_session: Session) -> None:
    company_id = _make_company(db_session, "Timeline PIT Co")
    version = _make_document_version(
        db_session, "future filing", dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    )
    _make_filing(db_session, version.id, company_id)

    result = get_timeline(db_session, company_id, as_of=dt.date(2020, 1, 1))
    assert result.data == []


def test_get_entity_history_identifiers_respect_valid_from(db_session: Session) -> None:
    company_id = _make_company(db_session, "Identifier Co")
    result = get_entity_history(db_session, company_id, as_of=dt.date(2020, 1, 1))
    assert result.data.identifiers == []
    assert "no real name-change history" in result.data.limitation


def test_get_risk_score_not_found_still_returns_real_model_limitations(db_session: Session) -> None:
    company_id = _make_company(db_session, "No Score Co")
    result = get_risk_score(db_session, company_id, as_of=dt.date(2020, 1, 1))
    assert result.data.found is False
    assert len(result.data.model_limitations) > 0


def test_get_outcomes_context_empty_for_a_fresh_company(db_session: Session) -> None:
    company_id = _make_company(db_session, "Fresh Outcomes Co")
    result = get_outcomes_context(db_session, company_id, as_of=dt.date(2020, 1, 1))
    assert result.data.ibbi_events == []
    assert result.data.sebi_events == []
    assert result.data.rating_history == []
