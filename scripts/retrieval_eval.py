"""Retrieval evaluation: Recall@5, Recall@10, MRR for lexical/vector/
hybrid against a SILVER (ai_constructed_unreviewed) query set built from
real label proposals -- see ledgerlight.knowledge.retrieval_eval."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.retrieval import load_bm25_index  # noqa: E402
from ledgerlight.knowledge.retrieval_eval import build_silver_queries, evaluate_all  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)
    bm25_index = load_bm25_index()

    with session_factory() as session:
        queries = build_silver_queries(session, limit=30)
        print(f"SILVER query set (ai_constructed_unreviewed): {len(queries)} queries")
        by_type: dict[str, int] = {}
        for q in queries:
            by_type[q.event_type] = by_type.get(q.event_type, 0) + 1
        for event_type, count in sorted(by_type.items()):
            print(f"  {event_type}: {count}")

        results = evaluate_all(session, bm25_index, queries)

    print()
    print(f"{'method':<15} {'n':>4} {'recall@5':>10} {'recall@10':>10} {'mrr':>8}")
    for r in results:
        row = f"{r.method:<15} {r.n_queries:>4} {r.recall_at_5:>10.3f}"
        row += f" {r.recall_at_10:>10.3f} {r.mrr:>8.3f}"
        print(row)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
