"""Tests for ledgerlight.agent.render -- Phase 4 Sec4 DRAFT /
Sec6 offline template renderer. Integration tests against the real DB
(claims need a real investigation_id FK and a real persisted id)."""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

import pytest
from sqlalchemy.orm import Session

from ledgerlight.agent.claims import standing_limitation_claims
from ledgerlight.agent.models import Claim, Investigation
from ledgerlight.agent.render import event_claim_sentence, render_offline
from ledgerlight.db.models import Document, DocumentPage, DocumentVersion
from ledgerlight.knowledge.models import Company

pytestmark = pytest.mark.integration


def _make_investigation(session: Session, company_id: uuid.UUID) -> uuid.UUID:
    investigation = Investigation(
        id=uuid.uuid4(),
        company_id=company_id,
        as_of=dt.date(2020, 1, 1),
        requested_by="test",
        budget_config={},
        usage={},
    )
    session.add(investigation)
    session.flush()
    return investigation.id


def _persist_claim(
    session: Session,
    investigation_id: uuid.UUID,
    claim_type: str,
    payload: dict[str, object],
    evidence: list[dict[str, object]],
) -> Claim:
    claim = Claim(
        investigation_id=investigation_id,
        claim_type=claim_type,
        payload=payload,
        evidence=evidence,
    )
    session.add(claim)
    session.flush()
    return claim


def test_render_offline_maps_every_sentence_to_a_real_claim_id(db_session: Session) -> None:
    company = Company(id=uuid.uuid4(), display_name="Render Test Co")
    db_session.add(company)
    db_session.flush()
    investigation_id = _make_investigation(db_session, company.id)

    claims: list[Claim] = []
    for draft in standing_limitation_claims():
        claims.append(
            _persist_claim(db_session, investigation_id, draft.claim_type, draft.payload, [])
        )
    claims.append(
        _persist_claim(
            db_session,
            investigation_id,
            "risk_signal",
            {"found": False, "model_limitations": "real limitations"},
            [],
        )
    )

    rendered = render_offline(db_session, claims, "Render Test Co", "2020-01-01", company.id)

    for section, sentences in rendered.sections.items():
        for idx in range(len(sentences)):
            key = f"{section}:{idx}"
            assert key in rendered.claim_id_map
            assert len(rendered.claim_id_map[key]) >= 1, f"sentence {key} has no claim id"


def test_render_offline_includes_a_real_source_citation(db_session: Session) -> None:
    company = Company(id=uuid.uuid4(), display_name="Source Test Co")
    db_session.add(company)
    db_session.flush()
    investigation_id = _make_investigation(db_session, company.id)

    document = Document(
        source_id="sebi", source_key=f"test://render/{uuid.uuid4()}", document_type="order"
    )
    db_session.add(document)
    db_session.flush()
    page_text = "This is the real first page text used for a rendered excerpt example."
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key=f"raw/test/{uuid.uuid4()}.pdf",
        bytes=len(page_text),
        mime_type="application/pdf",
        retrieval_method="automated_fetch",
        retrieval_url="https://example.com/test.pdf",
        retrieved_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
        known_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
        known_at_basis="retrieved_at",
        tool_version="test/1",
    )
    db_session.add(version)
    db_session.flush()
    db_session.add(
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
    db_session.flush()

    claim = _persist_claim(
        db_session,
        investigation_id,
        "event",
        {"event_type_code": "AUD_RESIGN", "tier": "CANDIDATE", "known_at": "2020-01-01"},
        [
            {
                "document_version_id": str(version.id),
                "page_number": 1,
                "char_start": 0,
                "char_end": 10,
            }
        ],
    )

    rendered = render_offline(db_session, [claim], "Source Test Co", "2020-01-01", company.id)
    assert "sources" in rendered.sections
    assert len(rendered.sections["sources"]) == 1
    assert "sebi" in rendered.sections["sources"][0]


def test_render_offline_resolves_company_name_via_real_filing_link(db_session: Session) -> None:
    """Phase 6 Correction 2 §3.1: the Sources-section title must come
    from the real `filings` link (`Filing.company_id` ->
    `Company.display_name`), not from `Document.company_name_raw`
    (almost always NULL) and not merely from whatever `company_name`
    string the caller happened to pass in. Deliberately passes a
    WRONG `company_name` to `render_offline` to isolate that the real
    filing link, not the fallback, is what resolves the name here."""
    from ledgerlight.knowledge.models import Filing

    company = Company(id=uuid.uuid4(), display_name="Real Filing Co")
    db_session.add(company)
    db_session.flush()
    investigation_id = _make_investigation(db_session, company.id)

    document = Document(
        source_id="care", source_key=f"test://render/{uuid.uuid4()}", document_type="rating"
    )
    db_session.add(document)
    db_session.flush()
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key=f"raw/test/{uuid.uuid4()}.pdf",
        bytes=1,
        mime_type="application/pdf",
        retrieval_method="automated_fetch",
        retrieval_url="https://example.com/test.pdf",
        retrieved_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
        known_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
        known_at_basis="retrieved_at",
        tool_version="test/1",
    )
    db_session.add(version)
    db_session.flush()
    db_session.add(
        Filing(
            version_id=version.id,
            company_id=company.id,
            link_method="manual",
            confidence=1.0,
        )
    )
    db_session.flush()

    claim = _persist_claim(
        db_session,
        investigation_id,
        "event",
        {"event_type_code": "AUD_RESIGN", "tier": "CANDIDATE", "known_at": "2020-01-01"},
        [
            {
                "document_version_id": str(version.id),
                "page_number": 1,
                "char_start": 0,
                "char_end": 10,
            }
        ],
    )

    rendered = render_offline(db_session, [claim], "WRONG passed-in name", "2020-01-01", company.id)
    assert "Real Filing Co" in rendered.sections["sources"][0]
    assert "WRONG passed-in name" not in rendered.sections["sources"][0]
    assert "Unknown company" not in rendered.sections["sources"][0]


def test_event_claim_sentence_renders_known_at_as_an_ist_calendar_date() -> None:
    """Phase 6 Correction 2 §3.2: prose must show the real Asia/Kolkata
    calendar date, never the raw UTC ISO string -- while the claim's
    own payload (the structured/exported form) stays untouched."""
    claim = Claim(
        investigation_id=uuid.uuid4(),
        claim_type="event",
        payload={
            "event_type_code": "AUD_RESIGN",
            "tier": "VERIFIED",
            "known_at": "2019-06-03T20:00:00+00:00",
        },
        evidence=[],
    )
    sentence = event_claim_sentence(claim)
    assert "4 June 2019 (IST)" in sentence
    assert claim.payload["known_at"] == "2019-06-03T20:00:00+00:00"


def test_render_offline_is_deterministic(db_session: Session) -> None:
    company = Company(id=uuid.uuid4(), display_name="Determinism Co")
    db_session.add(company)
    db_session.flush()
    investigation_id = _make_investigation(db_session, company.id)
    claims = [
        _persist_claim(db_session, investigation_id, draft.claim_type, draft.payload, [])
        for draft in standing_limitation_claims()
    ]

    first = render_offline(db_session, claims, "Determinism Co", "2020-01-01", company.id)
    second = render_offline(db_session, claims, "Determinism Co", "2020-01-01", company.id)
    assert first.sections == second.sections
    assert first.claim_id_map == second.claim_id_map
