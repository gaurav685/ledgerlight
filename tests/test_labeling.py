"""Tests for the silver label proposer.

Real bug found while running this against the real corpus: sampling
'none' examples by `enumerate()` position was non-idempotent, because
the chunks query had no ORDER BY, so a second run could return chunks in
a different order and sample a different subset as 'none' -- creating
duplicate-looking but distinct proposals every run. Fixed by sampling
deterministically from chunk.id instead of query-result position.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from ledgerlight.knowledge.labeling import propose_event_type, propose_labels
from ledgerlight.knowledge.models import Chunk

pytestmark = pytest.mark.integration


def test_propose_event_type_matches_real_aud_resign_pattern() -> None:
    # The exact real-world pattern that broke a stricter proximity regex
    # during development (see labeling.py's module comment): the subject
    # and verb are separated by a firm name across a line break.
    text = (
        "UPDATE ON RESIGNATION FROM THE AUDIT ENGAGEMENT\n"
        "BY THE STATUTORY AUDITOR - PRICE WATERHOUSE & CO\n"
        "CHARTERED ACCOUNTANTS LLP (PWC)\n\n"
        "This is to hereby inform that Price Waterhouse & Co "
        "Chartered Accountants LLP (PWC) has resigned."
    )
    assert propose_event_type(text) == "AUD_RESIGN"


def test_propose_event_type_none_for_unrelated_text() -> None:
    assert propose_event_type("The company held its annual general meeting on time.") is None


def test_propose_event_type_rpt_growth() -> None:
    text = "Related party transactions increased significantly during the quarter."
    assert propose_event_type(text) == "RPT_GROWTH"


def test_propose_labels_is_idempotent(db_session: Session) -> None:
    import datetime as dt

    from ledgerlight.db.models import Document, DocumentVersion

    document = Document(source_id="sebi", source_key=f"test://{uuid.uuid4()}", document_type="x")
    db_session.add(document)
    db_session.flush()
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key="raw/test/test.pdf",
        bytes=100,
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

    chunk_ids = set()
    for i in range(20):
        chunk = Chunk(
            version_id=version.id,
            page_number=1,
            char_start=i * 10,
            char_end=i * 10 + 9,
            text="nothing relevant here at all",
            chunker_version="test-1",
            known_at=version.known_at,
        )
        db_session.add(chunk)
        db_session.flush()
        chunk_ids.add(chunk.id)

    # Scoped to only this test's own chunks -- never touches the real
    # corpus's chunks or label_items.
    first = propose_labels(db_session, none_sample_rate=3, only_chunk_ids=chunk_ids)
    second = propose_labels(db_session, none_sample_rate=3, only_chunk_ids=chunk_ids)

    assert first.chunks_seen == 20
    assert first.proposals_created > 0
    assert second.proposals_created == 0
    assert second.already_proposed == first.proposals_created
