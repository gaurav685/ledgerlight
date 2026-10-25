"""Load every Phase 0/Correction-1 manifest file into object storage and
the metadata DB. Idempotent — safe to run repeatedly."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.backfill_from_manifest import run_store_backfill  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402


def main() -> int:
    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)

    manifest_dir = settings.data_dir / "manifests"
    manifest_paths = sorted(manifest_dir.glob("*.jsonl"))

    with session_factory() as session:
        stats = run_store_backfill(session, store, manifest_paths)

    print(f"Manifest entries seen: {stats.entries_seen}")
    print(f"Documents created: {stats.documents_created}")
    print(f"Versions created: {stats.versions_created}")
    print(f"Versions already present (idempotent skip): {stats.versions_already_present}")
    print(f"Objects uploaded: {stats.objects_uploaded}")
    print(f"Objects already present (content-addressed skip): {stats.objects_already_present}")
    if stats.hash_mismatches:
        print(f"HASH MISMATCHES ({len(stats.hash_mismatches)}):")
        for p in stats.hash_mismatches:
            print(f"  - {p}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
