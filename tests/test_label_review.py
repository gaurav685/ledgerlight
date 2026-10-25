"""Tests for the label-review core logic. apply_review_decision is what
the interactive CLI (scripts/label_review.py) calls on an actual human's
input -- this module itself never decides anything; it only records."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentVersion
from ledgerlight.knowledge.label_review import apply_review_decision, gold_label_counts
from ledgerlight.knowledge.models import LabelItem

pytestmark = pytest.mark.integration


def _make_label_item(db_session: Session, proposed_code: str = "AUD_RESIGN") -> LabelItem:
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
    item = LabelItem(
        version_id=version.id,
        page_number=1,
        proposed_event_type_code=proposed_code,
        proposer_name="test-proposer",
        proposer_version="1",
    )
    db_session.add(item)
    db_session.flush()
    return item


def test_accept_sets_human_reviewed_and_accepted(db_session: Session) -> None:
    item = _make_label_item(db_session)
    result = apply_review_decision(db_session, item.id, "accept", "jane reviewer")

    assert result.review_status == "accepted"
    assert result.label_source == "human_reviewed"
    db_session.refresh(item)
    assert item.reviewer == "jane reviewer"
    assert item.reviewed_at is not None


def test_correct_records_corrected_code(db_session: Session) -> None:
    item = _make_label_item(db_session, proposed_code="AUD_RESIGN")
    apply_review_decision(
        db_session, item.id, "correct", "jane reviewer", corrected_event_type_code="KMP_EXIT"
    )
    db_session.refresh(item)
    assert item.review_status == "corrected"
    assert item.corrected_event_type_code == "KMP_EXIT"
    assert item.label_source == "human_reviewed"


def test_reject_sets_rejected_but_still_human_reviewed(db_session: Session) -> None:
    item = _make_label_item(db_session)
    apply_review_decision(db_session, item.id, "reject", "jane reviewer")
    db_session.refresh(item)
    assert item.review_status == "rejected"
    assert item.label_source == "human_reviewed"


def test_blank_reviewer_is_rejected(db_session: Session) -> None:
    item = _make_label_item(db_session)
    with pytest.raises(ValueError, match="non-empty human identifier"):
        apply_review_decision(db_session, item.id, "accept", "   ")


def test_correct_without_corrected_code_is_rejected(db_session: Session) -> None:
    item = _make_label_item(db_session)
    with pytest.raises(ValueError, match="requires corrected_event_type_code"):
        apply_review_decision(db_session, item.id, "correct", "jane reviewer")


def test_unknown_label_item_id_is_rejected(db_session: Session) -> None:
    with pytest.raises(ValueError, match="no such label_item"):
        apply_review_decision(db_session, uuid.uuid4(), "accept", "jane reviewer")


def test_gold_label_counts_excludes_rejected_and_uses_corrected_code(db_session: Session) -> None:
    accepted = _make_label_item(db_session, proposed_code="AUD_RESIGN")
    corrected = _make_label_item(db_session, proposed_code="AUD_RESIGN")
    rejected = _make_label_item(db_session, proposed_code="AUD_RESIGN")
    unreviewed = _make_label_item(db_session, proposed_code="AUD_RESIGN")

    apply_review_decision(db_session, accepted.id, "accept", "r")
    apply_review_decision(
        db_session, corrected.id, "correct", "r", corrected_event_type_code="ID_EXIT"
    )
    apply_review_decision(db_session, rejected.id, "reject", "r")
    _ = unreviewed

    counts = gold_label_counts(db_session)
    assert counts.get("AUD_RESIGN") == 1
    assert counts.get("ID_EXIT") == 1
