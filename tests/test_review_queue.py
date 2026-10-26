"""Tests for review-queue list/resolve/dismiss."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from ledgerlight.knowledge.models import ReviewQueueItem
from ledgerlight.knowledge.review_queue import dismiss_item, list_open_items, resolve_item

pytestmark = pytest.mark.integration


def _make_item(
    session: Session, item_type: str = "event_field", priority: int = 3
) -> ReviewQueueItem:
    item = ReviewQueueItem(
        item_type=item_type,
        reference_id=uuid.uuid4(),
        reason_code="test_reason",
        priority=priority,
    )
    session.add(item)
    session.flush()
    return item


def test_list_open_items_excludes_resolved(db_session: Session) -> None:
    open_item = _make_item(db_session)
    resolved_item = _make_item(db_session)
    resolve_item(db_session, resolved_item.id, "fixed", "reviewer1")

    items = list_open_items(db_session)
    ids = {i.id for i in items}
    assert open_item.id in ids
    assert resolved_item.id not in ids


def test_list_open_items_filters_by_item_type(db_session: Session) -> None:
    _make_item(db_session, item_type="event_field")
    _make_item(db_session, item_type="entity_link")

    items = list_open_items(db_session, item_type="entity_link")
    assert all(i.item_type == "entity_link" for i in items)


def test_list_open_items_orders_by_priority(db_session: Session) -> None:
    low_priority = _make_item(db_session, priority=5)
    high_priority = _make_item(db_session, priority=1)

    items = [i for i in list_open_items(db_session) if i.id in {low_priority.id, high_priority.id}]
    assert items[0].id == high_priority.id


def test_resolve_sets_status_and_timestamp(db_session: Session) -> None:
    item = _make_item(db_session)
    resolved = resolve_item(db_session, item.id, "confirmed correct", "reviewer1")
    assert resolved.status == "resolved"
    assert resolved.resolution == "confirmed correct"
    assert resolved.resolved_at is not None


def test_dismiss_sets_status_dismissed(db_session: Session) -> None:
    item = _make_item(db_session)
    dismissed = dismiss_item(db_session, item.id, "not actually relevant", "reviewer1")
    assert dismissed.status == "dismissed"


def test_resolve_blank_reviewer_rejected(db_session: Session) -> None:
    item = _make_item(db_session)
    with pytest.raises(ValueError, match="non-empty human identifier"):
        resolve_item(db_session, item.id, "x", "  ")


def test_resolve_unknown_item_raises(db_session: Session) -> None:
    with pytest.raises(ValueError, match="no such review_queue item"):
        resolve_item(db_session, uuid.uuid4(), "x", "reviewer1")
