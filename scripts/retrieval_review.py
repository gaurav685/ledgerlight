"""Phase 6A §7 `retrieval-review` command: a real human review CLI
over ~10 real silver queries x their real top-10 hybrid-search
results. Marks each result relevant or not, recorded to an
append-only audit log.

Usage:
    python3 -m uv run python scripts/retrieval_review.py --reviewer "your name"

Resumes automatically (see field_review.py's own docstring for the
mechanism -- identical here; one audit item per (query, result chunk)
pair).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import Chunk, LabelItem  # noqa: E402
from ledgerlight.knowledge.retrieval import hybrid_search, load_bm25_index  # noqa: E402
from ledgerlight.knowledge.retrieval_eval import GoldQuery, build_silver_queries  # noqa: E402
from ledgerlight.review_pack.audit import append_entry, latest_decisions  # noqa: E402
from ledgerlight.review_pack.sampling import sample_test_split_first  # noqa: E402

AUDIT_PATH = REPO_ROOT / "docs" / "phase-6" / "review-pack" / "retrieval-review-audit.jsonl"
N_QUERIES = 10
TOP_K = 10


def _select_queries(session: Session, limit: int) -> list[tuple[GoldQuery, str, bool]]:
    all_queries = build_silver_queries(session, limit=30)
    splits_by_chunk: dict[str, str] = {
        str(chunk_id): split
        for chunk_id, split in session.execute(
            select(LabelItem.chunk_id, LabelItem.split).where(LabelItem.split.is_not(None))
        ).all()
        if split is not None
    }
    triples = [
        (q, splits_by_chunk.get(str(q.relevant_chunk_id), "no_split"), str(q.relevant_chunk_id))
        for q in all_queries
    ]
    sampled = sample_test_split_first(triples, limit)
    return [(s.item, s.split, s.is_topup) for s in sampled]


def main() -> int:
    parser = argparse.ArgumentParser(description="Real human retrieval-review CLI.")
    parser.add_argument("--reviewer", required=True, help="your name/identifier")
    parser.add_argument("--limit", type=int, default=None, help="cap queries shown this run")
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)
    bm25_index = load_bm25_index()

    decided = latest_decisions(AUDIT_PATH)
    print(f"{len(decided)} item(s) already decided (resuming).")

    reviewed_this_run = 0
    with session_factory() as session:
        queries = _select_queries(session, N_QUERIES)
        if args.limit is not None:
            queries = queries[: args.limit]
        print(f"{len(queries)} real queries selected (of up to 30 silver queries).")

        for q_idx, (query, split, is_topup) in enumerate(queries):
            results = hybrid_search(
                session, bm25_index, query.query, query.as_of, query.company_id, top_k=TOP_K
            )
            print("\n" + "=" * 70)
            print(
                f"query {q_idx + 1}/{len(queries)}: {query.query!r} "
                f"(event_type={query.event_type}, split={split}"
                f"{' top-up' if is_topup else ''})"
            )
            print(f"known relevant chunk_id (silver): {query.relevant_chunk_id}")

            for rank, scored in enumerate(results, start=1):
                item_id = f"{q_idx}:{rank}:{scored.chunk_id}"
                if item_id in decided:
                    continue
                chunk = session.get(Chunk, scored.chunk_id)
                text_preview = chunk.text[:300] if chunk else "(chunk not found)"
                is_known_relevant = scored.chunk_id == query.relevant_chunk_id
                print(f"\n  rank {rank}  chunk_id={scored.chunk_id}  score={scored.score:.3f}")
                if is_known_relevant:
                    print("  (this is the silver set's own known-relevant chunk)")
                print(f"  {text_preview}")

                choice = (
                    input("  [r]elevant / [n]ot relevant / [k]skip / [q]uit > ").strip().lower()
                )
                if choice == "q":
                    return _finish(reviewed_this_run)
                decision_map = {"r": "relevant", "n": "not_relevant", "k": "skip"}
                decision = decision_map.get(choice)
                if decision is None:
                    print("  unrecognised choice, skipping this item")
                    continue

                note = None
                if decision == "skip":
                    note = input("  skip note (optional) > ").strip() or None

                append_entry(
                    AUDIT_PATH,
                    item_id=item_id,
                    decision=decision,
                    reviewer=args.reviewer,
                    note=note,
                    extra={
                        "query": query.query,
                        "event_type": query.event_type,
                        "rank": rank,
                        "chunk_id": str(scored.chunk_id),
                        "is_known_relevant_silver": is_known_relevant,
                        "split": split,
                        "is_topup": is_topup,
                    },
                )
                reviewed_this_run += 1

    return _finish(reviewed_this_run)


def _finish(reviewed_this_run: int) -> int:
    print(f"\nreviewed this run: {reviewed_this_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
