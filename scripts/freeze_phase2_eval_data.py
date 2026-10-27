"""Freezes the Phase 2 evaluation data before any Phase 3 training/tuning
touches it: the test-split item IDs, and the gold-labelled item IDs with
their final labels. Writes data/manifests/frozen-test-split-phase2.json
and data/manifests/gold-labels-phase2.json, each with a sha256 of the
sorted IDs so tampering or drift is detectable. Read-only against
label_items -- never reviews, decides, or writes anything."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import LabelItem  # noqa: E402


def _sha256_of_sorted_ids(ids: list[str]) -> str:
    blob = "\n".join(sorted(ids)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        test_items = session.scalars(select(LabelItem).where(LabelItem.split == "test")).all()
        gold_items = session.scalars(
            select(LabelItem).where(LabelItem.label_source == "human_reviewed")
        ).all()

        test_ids = [str(i.id) for i in test_items]
        frozen_test = {
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "description": (
                "Phase 2 frozen TEST split (label_items.split='test'). Never used for "
                "training, tuning, or threshold selection in Phase 3. Guarded by "
                "tests/test_frozen_split_guard.py."
            ),
            "count": len(test_ids),
            "item_ids": sorted(test_ids),
            "sha256_of_sorted_ids": _sha256_of_sorted_ids(test_ids),
        }

        gold_records = []
        for item in gold_items:
            final_label = (
                item.proposed_event_type_code
                if item.review_status == "rejected"
                else (item.corrected_event_type_code or item.proposed_event_type_code)
            )
            gold_records.append(
                {
                    "label_item_id": str(item.id),
                    "split": item.split,
                    "proposed_event_type_code": item.proposed_event_type_code,
                    "review_status": item.review_status,
                    "final_label": final_label,
                    "counts_toward_class_coverage": item.review_status != "rejected",
                    "reviewer": item.reviewer,
                    "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
                }
            )
        gold_ids = [r["label_item_id"] for r in gold_records]
        gold_frozen = {
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "description": (
                "Phase 2 gold-labelled items (label_source='human_reviewed'). Includes "
                "accepted/corrected/rejected; excludes 'skipped' (never promoted to gold). "
                "final_label is the resolved class for accepted/corrected items; for "
                "rejected items it is the original proposed code with "
                "counts_toward_class_coverage=false (a rejection is not valid evidence "
                "for that class)."
            ),
            "count": len(gold_records),
            "records": sorted(gold_records, key=lambda r: r["label_item_id"]),
            "sha256_of_sorted_ids": _sha256_of_sorted_ids(gold_ids),
        }

    manifests_dir = REPO_ROOT / "data" / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    test_path = manifests_dir / "frozen-test-split-phase2.json"
    with test_path.open("w", encoding="utf-8") as f:
        json.dump(frozen_test, f, indent=2)
    print(f"wrote {test_path}: {frozen_test['count']} items")
    print(f"  sha256={frozen_test['sha256_of_sorted_ids']}")

    gold_path = manifests_dir / "gold-labels-phase2.json"
    with gold_path.open("w", encoding="utf-8") as f:
        json.dump(gold_frozen, f, indent=2)
    print(f"wrote {gold_path}: {gold_frozen['count']} items")
    print(f"  sha256={gold_frozen['sha256_of_sorted_ids']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
