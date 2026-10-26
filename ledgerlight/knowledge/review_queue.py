"""Review-queue operations: list open items, resolve one. Used by
scripts/review_queue.py (list and resolve) and by any pipeline stage
that queues a conflict/low-confidence decision for a human."""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.models import ReviewQueueItem


def list_open_items(
    session: Session, item_type: str | None = None, limit: int | None = None
) -> list[ReviewQueueItem]:
    stmt = select(ReviewQueueItem).where(ReviewQueueItem.status == "open")
    if item_type is not None:
        stmt = stmt.where(ReviewQueueItem.item_type == item_type)
    stmt = stmt.order_by(ReviewQueueItem.priority, ReviewQueueItem.created_at)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


def summarize_queue(session: Session) -> dict[str, dict[str, int]]:
    """Counts of open/in_review/resolved/dismissed items, grouped by
    item_type."""
    rows = session.execute(select(ReviewQueueItem.item_type, ReviewQueueItem.status)).all()
    summary: dict[str, dict[str, int]] = {}
    for item_type, status in rows:
        summary.setdefault(item_type, {}).setdefault(status, 0)
        summary[item_type][status] += 1
    return summary


def resolve_item(
    session: Session, item_id: UUID, resolution: str, reviewer: str
) -> ReviewQueueItem:
    if not reviewer or not reviewer.strip():
        raise ValueError("reviewer must be a non-empty human identifier")
    item = session.get(ReviewQueueItem, item_id)
    if item is None:
        raise ValueError(f"no such review_queue item: {item_id}")
    item.status = "resolved"
    item.resolution = resolution
    item.resolved_at = dt.datetime.now(dt.UTC)
    session.commit()
    return item


def dismiss_item(session: Session, item_id: UUID, reason: str, reviewer: str) -> ReviewQueueItem:
    if not reviewer or not reviewer.strip():
        raise ValueError("reviewer must be a non-empty human identifier")
    item = session.get(ReviewQueueItem, item_id)
    if item is None:
        raise ValueError(f"no such review_queue item: {item_id}")
    item.status = "dismissed"
    item.resolution = reason
    item.resolved_at = dt.datetime.now(dt.UTC)
    session.commit()
    return item
