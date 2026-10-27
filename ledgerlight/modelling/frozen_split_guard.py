"""Guards the Phase 2 frozen evaluation data (data/manifests/
frozen-test-split-phase2.json, data/manifests/gold-labels-phase2.json)
against being touched by Phase 3 training, tuning, or threshold-selection
code. Every such code path must call `assert_no_frozen_test_ids` on
whatever item/chunk ids it is about to fit or select on.

This is a hard boundary, not a convention: the brief that created this
module is explicit that no training, tuning, or threshold-selection
code may ever read a frozen test item, and that classifier selection
must use GOLD VALIDATION only -- never test.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FROZEN_TEST_SPLIT_PATH = REPO_ROOT / "data" / "manifests" / "frozen-test-split-phase2.json"
GOLD_LABELS_PATH = REPO_ROOT / "data" / "manifests" / "gold-labels-phase2.json"


class FrozenSplitViolation(RuntimeError):
    """Raised when training/tuning/selection code touches a frozen test item."""


def load_frozen_test_ids(path: Path = FROZEN_TEST_SPLIT_PATH) -> set[UUID]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {UUID(i) for i in data["item_ids"]}


def load_gold_label_records(path: Path = GOLD_LABELS_PATH) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return list(data["records"])


def assert_no_frozen_test_ids(
    candidate_ids: Iterable[UUID],
    *,
    context: str,
    frozen_path: Path = FROZEN_TEST_SPLIT_PATH,
) -> None:
    """Raises FrozenSplitViolation if any id in `candidate_ids` is a
    frozen test item. `context` names the caller for a useful error
    message (e.g. "train_classifier dev split", "gold-validation
    classifier selection")."""
    frozen = load_frozen_test_ids(frozen_path)
    overlap = frozen & set(candidate_ids)
    if overlap:
        sample = sorted(str(i) for i in overlap)[:5]
        raise FrozenSplitViolation(
            f"{context}: touched {len(overlap)} frozen test item(s) -- "
            f"this must never happen. Sample: {sample}"
        )
