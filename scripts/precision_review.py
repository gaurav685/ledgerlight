"""Enhancement `precision-review` §3: a real human review CLI over the
frozen, fresh sample in `data/manifests/precision-review-v1.jsonl`
(built by `scripts/build_precision_review_sample.py`). For each sampled
chunk, shows the flagged event type, the chunk text (the real cited
evidence for a whole-chunk classifier -- see the note printed for each
item), the company, document type/date, and records a real reviewer
decision (correct / wrong-type / not-an-event / skip) to an append-only
audit log.

YOU (a human) run this. Claude/any automated process must never run
this on your behalf -- see ledgerlight.review_pack and
docs/phase-6/phase-6-correction-1.md.

Usage (uv):
    uv run python scripts/precision_review.py --reviewer "your name" --human

Usage (Windows PowerShell, .venv directly):
    .venv\\Scripts\\python.exe scripts\\precision_review.py --reviewer "your name" --human

Resumes automatically: an item with an existing decision in
docs/enhancements/precision-review/precision-review-audit.jsonl is
skipped. Re-run the same command after an interruption to continue.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import Document, DocumentVersion  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import Chunk, Company, Filing  # noqa: E402
from ledgerlight.review_pack import require_human_confirmation  # noqa: E402
from ledgerlight.review_pack.audit import append_entry, latest_decisions  # noqa: E402

SAMPLE_MANIFEST_PATH = REPO_ROOT / "data" / "manifests" / "precision-review-v1.jsonl"
AUDIT_PATH = (
    REPO_ROOT / "docs" / "enhancements" / "precision-review" / "precision-review-audit.jsonl"
)

DECISION_MAP = {"c": "correct", "w": "wrong-type", "n": "not-an-event", "s": "skip"}


def _load_sample(path: Path) -> list[dict[str, str]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _show_item(session: Session, row: dict[str, str]) -> None:
    chunk_id = uuid.UUID(row["id"])
    chunk = session.get(Chunk, chunk_id)
    print("\n" + "=" * 70)
    print(f"chunk_id: {chunk_id}")
    print(f"flagged_event_type: {row['type']}")
    print(f"company (sample manifest): {row['company']}")
    if chunk is None:
        print("(chunk not found -- it may have been deleted since the sample was built)")
        return

    version = session.get(DocumentVersion, chunk.version_id)
    document = session.get(Document, version.document_id) if version else None
    filing = session.scalar(select(Filing).where(Filing.version_id == chunk.version_id))
    company = session.get(Company, filing.company_id) if filing else None

    print(f"company (fresh lookup): {company.display_name if company else '?'}")
    if document is not None:
        print(f"document_type: {document.document_type}  source: {document.source_id}")
    if version is not None:
        print(f"published_at: {version.published_at}  retrieval_url: {version.retrieval_url}")
    print(f"page: {chunk.page_number}")
    print(
        "--- cited evidence: whole-chunk classification, no sub-span citation for this "
        "detection method (rules_baseline/tfidf_lr both classify the full chunk) ---"
    )
    print(chunk.text[:2000])
    print("------------------")


def main() -> int:
    parser = argparse.ArgumentParser(description="Real human precision-review CLI.")
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

    sample = _load_sample(SAMPLE_MANIFEST_PATH)
    decided = latest_decisions(AUDIT_PATH)
    print(f"sample manifest: {SAMPLE_MANIFEST_PATH} ({len(sample)} item(s))")
    print(f"{len(decided)} item(s) already decided (resuming).")

    by_type_total: dict[str, int] = {}
    by_type_done: dict[str, int] = {}
    for row in sample:
        by_type_total[row["type"]] = by_type_total.get(row["type"], 0) + 1
        if row["id"] in decided:
            by_type_done[row["type"]] = by_type_done.get(row["type"], 0) + 1

    pending = [row for row in sample if row["id"] not in decided]
    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"{len(pending)} pending item(s) of {len(sample)}.")

    reviewed_this_run = 0
    with session_factory() as session:
        for row in pending:
            event_type = row["type"]
            print(
                f"\nprogress: {event_type} {by_type_done.get(event_type, 0)}/"
                f"{by_type_total.get(event_type, 0)}"
            )
            _show_item(session, row)

            choice = (
                input("[c]orrect / [w]rong-type / [n]ot-an-event / [s]kip / [q]uit > ")
                .strip()
                .lower()
            )
            if choice == "q":
                break
            decision = DECISION_MAP.get(choice)
            if decision is None:
                print("unrecognised choice, skipping this item")
                continue

            note = None
            if decision == "skip":
                note = input("skip note (optional) > ").strip() or None

            append_entry(
                AUDIT_PATH,
                item_id=row["id"],
                decision=decision,
                reviewer=args.reviewer,
                note=note,
                extra={
                    "event_type": event_type,
                    "company": row["company"],
                    "seed": row["seed"],
                },
            )
            by_type_done[event_type] = by_type_done.get(event_type, 0) + 1
            reviewed_this_run += 1

    print(f"\nreviewed this run: {reviewed_this_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
