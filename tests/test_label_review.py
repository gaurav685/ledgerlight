"""Tests for the label-review core logic. apply_review_decision is what
the interactive CLI (scripts/label_review.py) calls on an actual human's
input -- this module itself never decides anything; it only records."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentVersion
from ledgerlight.knowledge.label_review import (
    apply_review_decision,
    gold_label_counts,
    pending_label_items,
)
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

    ids = {accepted.id, corrected.id, rejected.id, unreviewed.id}
    counts = gold_label_counts(db_session, only_label_item_ids=ids)
    assert counts.get("AUD_RESIGN") == 1
    assert counts.get("ID_EXIT") == 1


def test_skip_persists_as_skipped_without_promoting_to_gold(db_session: Session) -> None:
    item = _make_label_item(db_session)
    result = apply_review_decision(
        db_session, item.id, "skip", "jane reviewer", note="unsure, revisit"
    )

    assert result.review_status == "skipped"
    # Skip is a deliberate non-decision: never promotes to GOLD, unlike
    # accept/correct/reject which all set human_reviewed.
    assert result.label_source == "ai_assisted_unreviewed"
    db_session.refresh(item)
    assert item.review_status == "skipped"
    assert item.reviewer == "jane reviewer"
    assert item.reviewed_at is not None
    assert item.review_note == "unsure, revisit"


def test_skip_without_note_is_allowed(db_session: Session) -> None:
    item = _make_label_item(db_session)
    apply_review_decision(db_session, item.id, "skip", "jane reviewer")
    db_session.refresh(item)
    assert item.review_status == "skipped"
    assert item.review_note is None


def test_skipped_item_is_distinguishable_from_unseen_pending(db_session: Session) -> None:
    skipped = _make_label_item(db_session)
    untouched = _make_label_item(db_session)
    apply_review_decision(db_session, skipped.id, "skip", "jane reviewer")

    ids = {skipped.id, untouched.id}
    pending = pending_label_items(db_session, only_ids=ids)
    pending_ids = {p.id for p in pending}

    assert skipped.id not in pending_ids
    assert untouched.id in pending_ids


def test_resume_excludes_already_decided_items_from_a_second_pending_query(
    db_session: Session,
) -> None:
    item_a = _make_label_item(db_session)
    item_b = _make_label_item(db_session)
    ids = {item_a.id, item_b.id}

    first_pass = pending_label_items(db_session, only_ids=ids)
    assert {i.id for i in first_pass} == ids

    apply_review_decision(db_session, item_a.id, "accept", "jane reviewer")

    second_pass = pending_label_items(db_session, only_ids=ids)
    assert {i.id for i in second_pass} == {item_b.id}
