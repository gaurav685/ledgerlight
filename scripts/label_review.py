"""Interactive label-review CLI. YOU (a human) run this to turn silver
(ai_assisted_unreviewed) label proposals into gold (human_reviewed)
labels. Claude/any automated process must never run this on your
behalf -- see docs/knowledge/taxonomy.md.

Usage:
    python scripts/label_review.py --reviewer "your name" [--limit N]
    python scripts/label_review.py --reviewer "your name" --sample-size 80
    python scripts/label_review.py --reviewer "your name" \
        --sample-manifest data/manifests/label-review-sample-42.jsonl

Sample mode (--sample-size or --sample-manifest) restricts review to
the pending items named in a data/manifests/label-review-sample-*.jsonl
manifest (built by scripts/build_label_sample.py) and shows progress as
"done/total" against the manifest's own size, counting items the
manifest says are already reviewed. Progress is saved after every
decision (including skip), so re-running the same command resumes with
whatever in the manifest is still pending.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.label_review import (  # noqa: E402
    apply_review_decision,
    pending_label_items,
)
from ledgerlight.knowledge.models import LabelItem  # noqa: E402

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


def _load_manifest_ids(path: Path) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            ids.add(uuid.UUID(row["label_item_id"]))
    return ids


def _resolve_sample_manifest(sample_manifest: str | None, sample_size: int | None) -> Path | None:
    if sample_manifest:
        return Path(sample_manifest)
    if sample_size is None:
        return None
    candidates = sorted((REPO_ROOT / "data" / "manifests").glob("label-review-sample-*.jsonl"))
    matches = [p for p in candidates if sum(1 for _ in p.open(encoding="utf-8")) == sample_size]
    if not matches:
        raise SystemExit(
            f"no data/manifests/label-review-sample-*.jsonl has exactly {sample_size} lines "
            f"(found {len(candidates)} manifest file(s) total). Run "
            "scripts/build_label_sample.py first, or pass --sample-manifest explicitly."
        )
    if len(matches) > 1:
        raise SystemExit(
            f"ambiguous: {len(matches)} manifests have exactly {sample_size} lines: "
            f"{[str(m) for m in matches]}. Pass --sample-manifest explicitly."
        )
    return matches[0]


def _manifest_progress(session: Session, manifest_ids: set[uuid.UUID]) -> tuple[int, int]:
    total = len(manifest_ids)
    pending_count = session.scalar(
        select(func.count())
        .select_from(LabelItem)
        .where(LabelItem.id.in_(manifest_ids), LabelItem.review_status == "pending")
    )
    return total - (pending_count or 0), total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer", required=True, help="your name/identifier")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--sample-manifest", default=None, help="path to a label-review-sample-*.jsonl manifest"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="auto-discover the manifest under data/manifests/ with exactly this many lines",
    )
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    manifest_path = _resolve_sample_manifest(args.sample_manifest, args.sample_size)
    manifest_ids = _load_manifest_ids(manifest_path) if manifest_path else None

    reviewed = 0
    with session_factory() as session:
        items = pending_label_items(session, limit=args.limit, only_ids=manifest_ids)

        if manifest_ids is not None:
            done, total = _manifest_progress(session, manifest_ids)
            print(f"sample manifest: {manifest_path}")
            print(
                f"{done}/{total} done, {len(items)} pending item(s) to show. "
                f"reviewer={args.reviewer!r}"
            )
        else:
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
                note = input("skip note (optional) > ").strip() or None
                apply_review_decision(session, item.id, "skip", args.reviewer, note=note)
                reviewed += 1
            elif choice == "a":
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
                continue

            if manifest_ids is not None:
                done, total = _manifest_progress(session, manifest_ids)
                print(f"progress: {done}/{total}")

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
