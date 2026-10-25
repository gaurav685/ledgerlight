"""Load data/taxonomy/taxonomy-v*.yaml into taxonomy_versions/event_types.
Idempotent: re-running with the same version is a no-op."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.taxonomy import load_taxonomy  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/taxonomy_load.py PATH_TO_TAXONOMY_YAML")
        return 2
    yaml_path = Path(sys.argv[1])

    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        result = load_taxonomy(session, yaml_path)

    print(f"version: {result.version}")
    print(f"was_new: {result.was_new}")
    print(f"event_types_loaded: {result.event_types_loaded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
