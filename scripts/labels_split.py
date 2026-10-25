"""Split label_items into dev/validation/test by company+time (never
randomly). Safe to re-run -- every item's split is recomputed from the
full current set each time."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.label_split import split_labels  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        stats = split_labels(session)

    print(f"groups: {stats.groups}")
    print(f"dev: {stats.dev}")
    print(f"validation: {stats.validation}")
    print(f"test: {stats.test}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
