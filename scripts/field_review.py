"""Phase 6A §7 `field-review` command: a real human review CLI over
~30 real extracted `EventField` values across event types. Shows the
value, the cited span and surrounding context, and records a real
reviewer decision (correct / wrong-value / unsupported / skip) to an
append-only audit log.

Usage:
    python3 -m uv run python scripts/field_review.py --reviewer "your name"

Resumes automatically: an item with an existing decision in
docs/phase-6/review-pack/field-review-audit.jsonl is skipped. Re-run
the same command after an interruption to continue where you left off.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import DocumentPage  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import (  # noqa: E402
    Company,
    Event,
    EventField,
    EventType,
    LabelItem,
)
from ledgerlight.review_pack import require_human_confirmation  # noqa: E402
from ledgerlight.review_pack.audit import append_entry, latest_decisions  # noqa: E402
from ledgerlight.review_pack.sampling import sample_test_split_first  # noqa: E402

AUDIT_PATH = REPO_ROOT / "docs" / "phase-6" / "review-pack" / "field-review-audit.jsonl"
SAMPLE_SIZE = 30


def _build_sample(session: Session, limit: int) -> list[tuple[EventField, str, bool]]:
    """Returns (field, split, is_topup) triples. Split is inherited
    from any real LabelItem sharing the same document version -- the
    closest real split signal available for an EventField, which has
    no split of its own."""
    rows = session.execute(select(EventField).order_by(EventField.id)).scalars().all()

    version_splits: dict[uuid.UUID, str] = {}
    for version_id, split in session.execute(
        select(LabelItem.version_id, LabelItem.split).where(LabelItem.split.is_not(None))
    ).all():
        # if a version has multiple label_items, prefer "test" if any chunk is test
        existing = version_splits.get(version_id)
        if split is not None and (existing is None or (existing != "test" and split == "test")):
            version_splits[version_id] = split

    triples = [
        (field, version_splits.get(field.evidence_version_id, "no_split"), str(field.id))
        for field in rows
    ]
    sampled = sample_test_split_first(triples, limit)
    return [(s.item, s.split, s.is_topup) for s in sampled]


def _show_field(session: Session, field: EventField, split: str, is_topup: bool) -> None:
    event = session.get(Event, field.event_id)
    event_type = session.get(EventType, event.event_type_id) if event else None
    company = session.get(Company, event.company_id) if event and event.company_id else None
    page = session.scalar(
        select(DocumentPage).where(
            DocumentPage.version_id == field.evidence_version_id,
            DocumentPage.page_number == field.evidence_page,
        )
    )

    print("\n" + "=" * 70)
    print(f"event_field_id: {field.id}")
    print(
        f"event_type: {event_type.code if event_type else '?'}  company: "
        f"{company.display_name if company else '?'}"
    )
    print(f"field_name: {field.field_name}")
    print(f"value: {field.value_json!r}")
    print(f"split: {split}" + (" (validation top-up)" if is_topup else " (real test split)"))
    if page is not None:
        start, end = field.evidence_char_start, field.evidence_char_end
        ctx_start = max(0, start - 150)
        ctx_end = min(len(page.raw_text), end + 150)
        print("--- cited span (marked with >>>...<<<) ---")
        print(
            page.raw_text[ctx_start:start]
            + ">>>"
            + page.raw_text[start:end]
            + "<<<"
            + page.raw_text[end:ctx_end]
        )
    else:
        print("(no real document_page found for this field's own evidence -- cannot show span)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Real human field-review CLI.")
    parser.add_argument("--reviewer", required=True, help="your name/identifier")
    parser.add_argument("--limit", type=int, default=None, help="cap items shown this run")
    parser.add_argument(
        "--human",
        action="store_true",
        help="confirms a real human is reviewing -- required to record any decision",
    )
    args = parser.parse_args()
    require_human_confirmation(args)

    settings = load_settings()
    session_factory = make_session_factory(settings)

    decided = latest_decisions(AUDIT_PATH)
    print(f"{len(decided)} item(s) already decided (resuming).")

    reviewed_this_run = 0
    with session_factory() as session:
        sample = _build_sample(session, SAMPLE_SIZE)
        pending = [(f, s, t) for f, s, t in sample if str(f.id) not in decided]
        if args.limit is not None:
            pending = pending[: args.limit]
        print(f"{len(pending)} pending item(s) of {len(sample)} in the real sample.")

        for field, split, is_topup in pending:
            _show_field(session, field, split, is_topup)
            choice = (
                input("[c]orrect / [w]rong-value / [u]nsupported / [s]kip / [q]uit > ")
                .strip()
                .lower()
            )
            if choice == "q":
                break
            decision_map = {"c": "correct", "w": "wrong-value", "u": "unsupported", "s": "skip"}
            decision = decision_map.get(choice)
            if decision is None:
                print("unrecognised choice, skipping this item")
                continue

            note = None
            corrected_value = None
            if decision == "skip":
                note = input("skip note (optional) > ").strip() or None
            elif decision == "wrong-value":
                corrected_value = input("corrected value > ").strip()

            append_entry(
                AUDIT_PATH,
                item_id=str(field.id),
                decision=decision,
                reviewer=args.reviewer,
                note=note,
                extra={
                    "field_name": field.field_name,
                    "original_value": field.value_json,
                    "corrected_value": corrected_value,
                    "split": split,
                    "is_topup": is_topup,
                },
            )
            reviewed_this_run += 1

    print(f"\nreviewed this run: {reviewed_this_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
