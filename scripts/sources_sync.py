"""Sync data/manifests/sources.yaml into the `sources` table."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.sources_sync import sync_sources  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        synced = sync_sources(session, REPO_ROOT / "data" / "manifests" / "sources.yaml")
    print(f"Synced {len(synced)} sources: {sorted(synced)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
