"""Deterministic sampling for the human review pack: draw test-split
items first, then top up from validation (and anything else) if the
test split alone doesn't reach the target count. Every selected item
is tagged with which split it actually came from, so a reviewer (or
this phase's own evaluation report) can tell a real test-split item
from a validation top-up -- never silently blended.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

_SPLIT_PRIORITY = {"test": 0, "validation": 1, "dev": 2}


@dataclass(frozen=True)
class SampledItem(Generic[T]):
    item: T
    split: str
    is_topup: bool


def sample_test_split_first(items: list[tuple[T, str, str]], limit: int) -> list[SampledItem[T]]:
    """`items` is a list of (item, split, tiebreak_key) triples, where
    split is one of "test", "validation", "dev", or any other string
    (treated as lowest priority). Orders by split priority then by
    `tiebreak_key` ascending -- a stable, deterministic string, e.g. a
    real id -- and takes the first `limit`. Every selected item not in
    the real test split is tagged `is_topup=True`, so a top-up is never
    silently blended with a genuine test-split item.
    """
    ordered = sorted(items, key=lambda t: (_SPLIT_PRIORITY.get(t[1], 99), t[2]))
    selected = ordered[:limit]
    return [
        SampledItem(item=item, split=split, is_topup=(split != "test"))
        for item, split, _ in selected
    ]
