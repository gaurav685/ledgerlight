"""Propose silver labels (label_source=ai_assisted_unreviewed) for real
chunks via the keyword-rule baseline. Idempotent per (chunk, proposer,
proposer_version)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.labeling import propose_labels  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        stats = propose_labels(session)

    print(f"chunks_seen: {stats.chunks_seen}")
    print(f"proposals_created: {stats.proposals_created}")
    print(f"already_proposed: {stats.already_proposed}")
    print("by_event_type:")
    for code, count in sorted(stats.by_event_type.items()):
        print(f"  {code}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
