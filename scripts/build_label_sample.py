"""Builds data/manifests/label-review-sample-<seed>.jsonl: a deterministic
80-item review sample combining the 38 already-reviewed label_items with
42 newly-selected pending ones (test-split preferred, validation fallback,
filling per-class minimums first -- see ledgerlight/knowledge/label_sample.py
for the exact algorithm). Read-only against label_items: this script never
reviews, decides, or writes any review_status.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.label_sample import build_label_sample  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        result = build_label_sample(session)

    manifest_path = REPO_ROOT / "data" / "manifests" / f"label-review-sample-{result.seed}.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        for item in result.items:
            row = {"label_item_id": str(item.label_item_id), "split": item.split}
            f.write(json.dumps(row) + "\n")

    print(f"manifest: {manifest_path}")
    print(f"seed: {result.seed}")
    print(f"reviewed_total: {result.reviewed_total}")
    print(f"reviewed_in_test_split: {result.reviewed_in_test_split}")
    print(f"new_total: {result.new_total}")
    print(f"sample_total: {len(result.items)}")
    if result.under_minimum_classes:
        print(f"under_minimum (target={result.target_per_class}): {result.under_minimum_classes}")
    print()
    header = f"{'class':12} {'already':>8} {'new':>5} {'total':>6} {'new_test':>9} {'new_val':>8}"
    print(header)
    print("-" * len(header))
    for c in result.composition:
        print(
            f"{c.event_class:12} {c.already_reviewed:>8} {c.newly_added:>5} "
            f"{c.total:>6} {c.new_test:>9} {c.new_validation:>8}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
