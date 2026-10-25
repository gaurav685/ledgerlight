"""Interactive label-review CLI. YOU (a human) run this to turn silver
(ai_assisted_unreviewed) label proposals into gold (human_reviewed)
labels. Claude/any automated process must never run this on your
behalf -- see docs/knowledge/taxonomy.md.

Usage: python scripts/label_review.py --reviewer "your name" [--limit N]
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.label_review import (  # noqa: E402
    apply_review_decision,
    pending_label_items,
)

VALID_EVENT_TYPE_CODES = {
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
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer", required=True, help="your name/identifier")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    reviewed = 0
    with session_factory() as session:
        items = pending_label_items(session, limit=args.limit)
        print(f"{len(items)} pending label item(s). reviewer={args.reviewer!r}")

        for item in items:
            print("\n" + "=" * 70)
            print(f"label_item_id: {item.id}")
            print(f"version_id: {item.version_id}  page: {item.page_number}")
            print(f"proposed_event_type_code: {item.proposed_event_type_code}")
            print(f"proposer: {item.proposer_name} v{item.proposer_version}")
            text = _chunk_text(session, item.chunk_id)
            if text:
                print("--- chunk text ---")
                print(text[:1500])
                print("------------------")

            choice = input("[a]ccept / [c]orrect / [r]eject / [s]kip / [q]uit > ").strip().lower()
            if choice == "q":
                break
            if choice == "s":
                continue
            if choice == "a":
                apply_review_decision(session, item.id, "accept", args.reviewer)
                reviewed += 1
            elif choice == "c":
                corrected = input(
                    f"corrected event_type_code {sorted(VALID_EVENT_TYPE_CODES)}: "
                ).strip()
                if corrected not in VALID_EVENT_TYPE_CODES:
                    print(f"not a valid code, skipping: {corrected!r}")
                    continue
                apply_review_decision(
                    session, item.id, "correct", args.reviewer, corrected_event_type_code=corrected
                )
                reviewed += 1
            elif choice == "r":
                apply_review_decision(session, item.id, "reject", args.reviewer)
                reviewed += 1
            else:
                print("unrecognised choice, skipping")

    print(f"\nreviewed: {reviewed}")
    return 0


def _chunk_text(session: Session, chunk_id: uuid.UUID | None) -> str | None:
    if chunk_id is None:
        return None
    from ledgerlight.knowledge.models import Chunk

    chunk = session.get(Chunk, chunk_id)
    return chunk.text if chunk else None


if __name__ == "__main__":
    raise SystemExit(main())
