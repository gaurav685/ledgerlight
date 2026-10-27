"""Builds a deterministic, fixed-size review sample that combines
already-reviewed label_items with newly-selected pending ones, to grow
gold coverage toward a per-class minimum without re-touching any
decision a human has already made.

Selection algorithm (seeded, reproducible given the same seed and the
same database state):

1. Count already-reviewed items per resolved event class
   (`corrected_event_type_code` if set, else `proposed_event_type_code`),
   excluding `rejected` items -- a rejection means the original proposal
   was wrong, so it contributes no evidence toward that class's coverage
   (it still appears in the sample and in the display table, just not
   toward the minimum).
2. For each class (in a fixed order, for determinism), compute
   `need = max(0, target_per_class - already_reviewed_count)`.
3. Pull `need` NEW items for that class from the eligible pool -- pending
   items in the `test` split first, falling back to `validation` only
   when `test` is exhausted for that class. `dev` is never used for new
   items: it is the training split, not an evaluation split, so adding
   more reviewed `dev` items would not grow gold evaluation coverage.
4. Once every class's minimum is satisfied (or its test+validation pool
   is exhausted -- some classes have 0 items in test+validation at all),
   any remaining budget (up to `target_total - 38`) is filled by
   round-robining over the same fixed class order, same test-then-
   validation preference, one item per class per round, until the
   budget or the pool is exhausted. In this corpus that overflow lands
   almost entirely on `none` (the only class with a large remaining
   pool), which is disclosed, not hidden.

Within a (class, split) bucket, candidates are sorted by id (so the
input order to the RNG never depends on incidental query-result
ordering) and then shuffled with `random.Random(seed)` before being
consumed from the front -- this is what makes "deterministic" mean
"reproducible," not "alphabetical" or "arbitrary."
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.models import LabelItem

SAMPLE_SEED = 42
TARGET_TOTAL = 80
TARGET_PER_CLASS_MIN = 4

EVENT_CLASSES = [
    "AUD_RESIGN",
    "PLEDGE_UP",
    "KMP_EXIT",
    "ID_EXIT",
    "RATING_ACT",
    "RESULT_DELAY",
    "AUDIT_QUAL",
    "FORENSIC",
    "RPT_GROWTH",
    "none",
]

# New items are only ever pulled from evaluation splits -- `dev` is the
# training split and reviewing more of it doesn't grow gold *evaluation*
# coverage. Order matters: test is preferred, validation is the fallback.
NEW_ITEM_SPLIT_PRIORITY: tuple[str, ...] = ("test", "validation")

SampleItemStatus = Literal["already_reviewed", "new_pending"]


@dataclass(frozen=True)
class SampleItem:
    label_item_id: uuid.UUID
    split: str
    status: SampleItemStatus
    event_class: str
    counts_toward_minimum: bool


@dataclass
class ClassComposition:
    event_class: str
    already_reviewed: int
    newly_added: int
    new_test: int
    new_validation: int

    @property
    def total(self) -> int:
        return self.already_reviewed + self.newly_added


@dataclass
class SampleBuildResult:
    seed: int
    target_total: int
    target_per_class: int
    items: list[SampleItem] = field(default_factory=list)
    composition: list[ClassComposition] = field(default_factory=list)
    reviewed_total: int = 0
    reviewed_in_test_split: int = 0
    new_total: int = 0
    under_minimum_classes: list[str] = field(default_factory=list)


def _resolved_class(proposed: str, corrected: str | None, review_status: str) -> str:
    if review_status == "rejected":
        return proposed
    return corrected or proposed


def build_label_sample(
    session: Session,
    *,
    seed: int = SAMPLE_SEED,
    target_total: int = TARGET_TOTAL,
    target_per_class: int = TARGET_PER_CLASS_MIN,
    only_label_item_ids: set[uuid.UUID] | None = None,
) -> SampleBuildResult:
    """`only_label_item_ids`, when given, scopes both the already-reviewed
    and the pending-pool queries to that id set -- used by tests so they
    never see (or get counted against) the real corpus's own label_items,
    the same isolation pattern as `labeling.propose_labels`'s
    `only_chunk_ids`."""
    result = SampleBuildResult(
        seed=seed, target_total=target_total, target_per_class=target_per_class
    )

    # 1. Already-reviewed items (any decision, including 'skipped' and
    # 'rejected') -- included as-is, decisions untouched.
    reviewed_stmt = select(LabelItem).where(LabelItem.review_status != "pending")
    if only_label_item_ids is not None:
        reviewed_stmt = reviewed_stmt.where(LabelItem.id.in_(only_label_item_ids))
    reviewed_rows = session.scalars(reviewed_stmt.order_by(LabelItem.id)).all()

    reviewed_items: list[SampleItem] = []
    already_reviewed_counts: dict[str, int] = {}
    for row in reviewed_rows:
        cls = _resolved_class(
            row.proposed_event_type_code, row.corrected_event_type_code, row.review_status
        )
        counts = row.review_status != "rejected"
        reviewed_items.append(
            SampleItem(
                label_item_id=row.id,
                split=row.split or "unknown",
                status="already_reviewed",
                event_class=cls,
                counts_toward_minimum=counts,
            )
        )
        if counts:
            already_reviewed_counts[cls] = already_reviewed_counts.get(cls, 0) + 1

    result.reviewed_total = len(reviewed_items)
    result.reviewed_in_test_split = sum(1 for i in reviewed_items if i.split == "test")
    already_reviewed_ids = {i.label_item_id for i in reviewed_items}

    # 2. Eligible new-item pool: pending, test/validation only, never dev.
    pending_stmt = select(LabelItem.id, LabelItem.split, LabelItem.proposed_event_type_code).where(
        LabelItem.review_status == "pending",
        LabelItem.split.in_(NEW_ITEM_SPLIT_PRIORITY),
    )
    if only_label_item_ids is not None:
        pending_stmt = pending_stmt.where(LabelItem.id.in_(only_label_item_ids))
    pending_rows = session.execute(pending_stmt.order_by(LabelItem.id)).all()

    pool: dict[str, dict[str, list[uuid.UUID]]] = {
        cls: {split: [] for split in NEW_ITEM_SPLIT_PRIORITY} for cls in EVENT_CLASSES
    }
    for item_id, split, proposed_cls in pending_rows:
        if split is None or proposed_cls not in pool or item_id in already_reviewed_ids:
            continue
        pool[proposed_cls][split].append(item_id)

    rng = random.Random(seed)
    for cls in EVENT_CLASSES:
        for split in NEW_ITEM_SPLIT_PRIORITY:
            rng.shuffle(pool[cls][split])

    new_budget = max(0, target_total - result.reviewed_total)
    selected: list[SampleItem] = []
    new_by_class_split: dict[str, dict[str, int]] = {
        cls: {split: 0 for split in NEW_ITEM_SPLIT_PRIORITY} for cls in EVENT_CLASSES
    }

    def _take(cls: str, split: str, n: int) -> int:
        bucket = pool[cls][split]
        take = min(n, len(bucket))
        for _ in range(take):
            item_id = bucket.pop(0)
            selected.append(
                SampleItem(
                    label_item_id=item_id,
                    split=split,
                    status="new_pending",
                    event_class=cls,
                    counts_toward_minimum=True,
                )
            )
            new_by_class_split[cls][split] += 1
        return take

    # Step A: fill each class's minimum, test-first then validation.
    for cls in EVENT_CLASSES:
        need = max(0, target_per_class - already_reviewed_counts.get(cls, 0))
        for split in NEW_ITEM_SPLIT_PRIORITY:
            if need <= 0 or len(selected) >= new_budget:
                break
            taken = _take(cls, split, min(need, new_budget - len(selected)))
            need -= taken
        if need > 0:
            result.under_minimum_classes.append(cls)

    # Step B: round-robin the remaining budget over the same class
    # order and split priority, one item at a time, until the budget or
    # every class's pool is exhausted.
    progressed = True
    while len(selected) < new_budget and progressed:
        progressed = False
        for cls in EVENT_CLASSES:
            if len(selected) >= new_budget:
                break
            for split in NEW_ITEM_SPLIT_PRIORITY:
                if len(selected) >= new_budget:
                    break
                if _take(cls, split, 1):
                    progressed = True

    result.new_total = len(selected)
    result.items = reviewed_items + selected

    # Composition table: already_reviewed counts include rejected items
    # (bucketed under their original proposed class) since they are
    # genuinely part of the 38/80 -- only the *minimum-driving* counts
    # above exclude them.
    display_already_reviewed: dict[str, int] = {}
    for item in reviewed_items:
        display_already_reviewed[item.event_class] = (
            display_already_reviewed.get(item.event_class, 0) + 1
        )

    for cls in EVENT_CLASSES:
        result.composition.append(
            ClassComposition(
                event_class=cls,
                already_reviewed=display_already_reviewed.get(cls, 0),
                newly_added=new_by_class_split[cls]["test"] + new_by_class_split[cls]["validation"],
                new_test=new_by_class_split[cls]["test"],
                new_validation=new_by_class_split[cls]["validation"],
            )
        )

    return result
