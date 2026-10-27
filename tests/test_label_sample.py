"""Tests for the deterministic 80-item review sample builder
(ledgerlight.knowledge.label_sample). All fixtures are scoped via
only_label_item_ids so these tests never see (or get counted against)
the real corpus's own label_items -- same isolation pattern as
test_labeling.py's only_chunk_ids."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentVersion
from ledgerlight.knowledge.label_sample import build_label_sample
from ledgerlight.knowledge.models import LabelItem

pytestmark = pytest.mark.integration


def _make_version(session: Session) -> DocumentVersion:
    document = Document(
        source_id="sebi", source_key=f"test://sample/{uuid.uuid4()}", document_type="x"
    )
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key=f"raw/test/{uuid.uuid4()}.pdf",
        bytes=10,
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
    return version


def _make_item(
    session: Session,
    version: DocumentVersion,
    *,
    proposed: str,
    split: str | None,
    review_status: str = "pending",
    corrected: str | None = None,
    reviewer: str | None = None,
) -> LabelItem:
    item = LabelItem(
        version_id=version.id,
        page_number=1,
        proposed_event_type_code=proposed,
        proposer_name="keyword-rule-baseline",
        proposer_version="1",
        split=split,
        review_status=review_status,
        corrected_event_type_code=corrected,
        reviewer=reviewer,
        reviewed_at=dt.datetime.now(dt.UTC) if reviewer else None,
        label_source="human_reviewed" if reviewer else "ai_assisted_unreviewed",
    )
    session.add(item)
    session.flush()
    return item


def test_sampling_is_deterministic_given_same_seed(db_session: Session) -> None:
    version = _make_version(db_session)
    ids = set()
    for _ in range(10):
        item = _make_item(db_session, version, proposed="RPT_GROWTH", split="validation")
        ids.add(item.id)

    first = build_label_sample(
        db_session, seed=7, target_total=5, target_per_class=4, only_label_item_ids=ids
    )
    second = build_label_sample(
        db_session, seed=7, target_total=5, target_per_class=4, only_label_item_ids=ids
    )

    first_ids = [i.label_item_id for i in first.items]
    second_ids = [i.label_item_id for i in second.items]
    assert first_ids == second_ids
    assert len(first_ids) == 5


def test_sampling_with_different_seed_can_pick_different_items(db_session: Session) -> None:
    version = _make_version(db_session)
    ids = set()
    for _ in range(10):
        item = _make_item(db_session, version, proposed="RPT_GROWTH", split="validation")
        ids.add(item.id)

    seed7 = build_label_sample(
        db_session, seed=7, target_total=5, target_per_class=4, only_label_item_ids=ids
    )
    seed99 = build_label_sample(
        db_session, seed=99, target_total=5, target_per_class=4, only_label_item_ids=ids
    )

    assert {i.label_item_id for i in seed7.items} != {i.label_item_id for i in seed99.items} or len(
        ids
    ) <= 5


def test_already_reviewed_items_included_unchanged(db_session: Session) -> None:
    version = _make_version(db_session)
    reviewed = _make_item(
        db_session,
        version,
        proposed="AUD_RESIGN",
        split="dev",
        review_status="accepted",
        reviewer="Someone",
    )
    pending_ids = {reviewed.id}
    for _ in range(3):
        item = _make_item(db_session, version, proposed="AUD_RESIGN", split="validation")
        pending_ids.add(item.id)

    result = build_label_sample(
        db_session, seed=1, target_total=4, target_per_class=4, only_label_item_ids=pending_ids
    )

    already = [i for i in result.items if i.status == "already_reviewed"]
    assert len(already) == 1
    assert already[0].label_item_id == reviewed.id
    assert already[0].split == "dev"
    assert already[0].event_class == "AUD_RESIGN"
    # Untouched: the review_status/reviewer this test set are still exactly what we set.
    db_session.refresh(reviewed)
    assert reviewed.review_status == "accepted"
    assert reviewed.reviewer == "Someone"


def test_per_class_minimum_counts_already_reviewed_items(db_session: Session) -> None:
    version = _make_version(db_session)
    ids = set()
    # 4 already-reviewed AUD_RESIGN items -- minimum (4) already met.
    for _ in range(4):
        item = _make_item(
            db_session,
            version,
            proposed="AUD_RESIGN",
            split="dev",
            review_status="accepted",
            reviewer="X",
        )
        ids.add(item.id)
    # Plenty of pending AUD_RESIGN items available, which should NOT be touched.
    for _ in range(5):
        item = _make_item(db_session, version, proposed="AUD_RESIGN", split="validation")
        ids.add(item.id)

    result = build_label_sample(
        db_session, seed=1, target_total=4, target_per_class=4, only_label_item_ids=ids
    )

    new_aud_resign = [
        i for i in result.items if i.status == "new_pending" and i.event_class == "AUD_RESIGN"
    ]
    assert len(new_aud_resign) == 0
    assert "AUD_RESIGN" not in result.under_minimum_classes


def test_test_split_preferred_before_validation_fallback(db_session: Session) -> None:
    version = _make_version(db_session)
    ids = set()
    test_ids = set()
    for _ in range(2):
        item = _make_item(db_session, version, proposed="ID_EXIT", split="test")
        ids.add(item.id)
        test_ids.add(item.id)
    val_ids = set()
    for _ in range(5):
        item = _make_item(db_session, version, proposed="ID_EXIT", split="validation")
        ids.add(item.id)
        val_ids.add(item.id)

    result = build_label_sample(
        db_session, seed=3, target_total=4, target_per_class=4, only_label_item_ids=ids
    )

    new_items = [i for i in result.items if i.status == "new_pending"]
    assert len(new_items) == 4
    chosen_test = [i for i in new_items if i.split == "test"]
    chosen_val = [i for i in new_items if i.split == "validation"]
    # Both 2 test items are exhausted before any validation item is needed.
    assert len(chosen_test) == 2
    assert len(chosen_val) == 2
    assert {i.label_item_id for i in chosen_test} == test_ids
    assert {i.label_item_id for i in chosen_val} <= val_ids


def test_dev_split_never_used_for_new_items(db_session: Session) -> None:
    version = _make_version(db_session)
    ids = set()
    for _ in range(6):
        item = _make_item(db_session, version, proposed="FORENSIC", split="dev")
        ids.add(item.id)

    result = build_label_sample(
        db_session, seed=1, target_total=4, target_per_class=4, only_label_item_ids=ids
    )

    new_items = [i for i in result.items if i.status == "new_pending"]
    assert len(new_items) == 0
    assert "FORENSIC" in result.under_minimum_classes
