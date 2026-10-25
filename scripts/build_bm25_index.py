"""(Re)build the persisted BM25 index at data/indexes/bm25_index.pkl
from every chunk in the database. Rebuildable, gitignored artifact."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.retrieval import build_bm25_index  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        count = build_bm25_index(session)
    print(f"chunks indexed: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
