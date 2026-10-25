"""Core logic for the label-review CLI (scripts/label_review.py). Only
this module's apply_review_decision -- driven by an actual human typing
into the interactive CLI -- may set label_source='human_reviewed', which
is what makes a label GOLD. No automated process may call this on behalf
of a human; see docs/knowledge/taxonomy.md and the Phase 2 report §13.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.models import LabelItem

ReviewDecision = Literal["accept", "correct", "reject"]


@dataclass
class ReviewResult:
    label_item_id: uuid.UUID
    decision: ReviewDecision
    review_status: str
    label_source: str


def apply_review_decision(
    session: Session,
    label_item_id: uuid.UUID,
    decision: ReviewDecision,
    reviewer: str,
    *,
    corrected_event_type_code: str | None = None,
) -> ReviewResult:
    if not reviewer or not reviewer.strip():
        raise ValueError("reviewer must be a non-empty human identifier -- never blank/automated")
    if decision == "correct" and not corrected_event_type_code:
        raise ValueError("decision='correct' requires corrected_event_type_code")

    item = session.get(LabelItem, label_item_id)
    if item is None:
        raise ValueError(f"no such label_item: {label_item_id}")

    status_by_decision: dict[ReviewDecision, str] = {
        "accept": "accepted",
        "correct": "corrected",
        "reject": "rejected",
    }
    item.review_status = status_by_decision[decision]
    item.label_source = "human_reviewed"
    item.reviewer = reviewer
    item.reviewed_at = dt.datetime.now(dt.UTC)
    if decision == "correct":
        item.corrected_event_type_code = corrected_event_type_code

    session.commit()
    return ReviewResult(
        label_item_id=item.id,
        decision=decision,
        review_status=item.review_status,
        label_source=item.label_source,
    )


def pending_label_items(session: Session, limit: int | None = None) -> list[LabelItem]:
    stmt = (
        select(LabelItem).where(LabelItem.review_status == "pending").order_by(LabelItem.created_at)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


def gold_label_counts(session: Session) -> dict[str, int]:
    """Counts of GOLD (human_reviewed) labels by final event_type code --
    'corrected' items count under their corrected code, not the original
    proposal."""
    items = session.scalars(
        select(LabelItem).where(LabelItem.label_source == "human_reviewed")
    ).all()
    counts: dict[str, int] = {}
    for item in items:
        if item.review_status == "rejected":
            continue
        code = item.corrected_event_type_code or item.proposed_event_type_code
        counts[code] = counts.get(code, 0) + 1
    return counts
