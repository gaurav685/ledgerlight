"""Phase 5 §8: real backup -- a `pg_dump` of the real app database (custom
format, via the real running Postgres container) plus a real object-by-
object sync of the real Garage raw-storage bucket, both written under
`../ledgerlight-backups/` (outside the repo -- never committed; same
convention this project already uses for its git bundle backups).

Every object downloaded during the Garage sync is content-addressed
(`raw/<sha256[:2]>/<sha256><ext>`) -- its own key names the hash its
content must match, so a real sha256 check runs on every object as it is
written, never deferred to the restore drill alone.

Usage: `python scripts/backup.py` (no args -- always backs up the one
real local dev stack; never pointed at a remote/production host from
here).
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.common.hashing import sha256_bytes  # noqa: E402
from ledgerlight.config.settings import Settings, load_settings  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402

POSTGRES_CONTAINER = "ledgerlight-phase0-postgres-1"  # from infra/docker-compose.yml
BACKUP_ROOT = REPO_ROOT.parent / "ledgerlight-backups"


def backup_database(settings: Settings, timestamp: str) -> Path:
    out_dir = BACKUP_ROOT / "db"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ledgerlight-{timestamp}.dump"

    print(f"pg_dump: {settings.postgres_db!r} from {POSTGRES_CONTAINER} -> {out_path}")
    proc = subprocess.run(
        [
            "docker",
            "exec",
            POSTGRES_CONTAINER,
            "pg_dump",
            "-U",
            settings.postgres_user,
            "-Fc",
            settings.postgres_db,
        ],
        capture_output=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {proc.stderr.decode('utf-8', errors='replace')}")
    out_path.write_bytes(proc.stdout)
    print(f"pg_dump: wrote {len(proc.stdout):,} bytes")
    return out_path


def backup_objects(settings: Settings, timestamp: str) -> tuple[Path, int]:
    out_dir = BACKUP_ROOT / "objects" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    store = ObjectStore(settings)
    client = store._client  # noqa: SLF001 -- this script owns real admin-level bucket access
    bucket = settings.s3_bucket

    count = 0
    continuation_token: str | None = None
    while True:
        kwargs = {"Bucket": bucket}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        page = client.list_objects_v2(**kwargs)
        for obj in page.get("Contents", []):
            key = obj["Key"]
            body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
            expected_hash = key.rsplit("/", 1)[-1].split(".", 1)[0]
            actual_hash = sha256_bytes(body)
            if actual_hash != expected_hash:
                raise RuntimeError(
                    f"hash mismatch syncing {key!r}: key says {expected_hash}, got {actual_hash}"
                )
            dest = out_dir / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            count += 1
        if page.get("IsTruncated"):
            continuation_token = page["NextContinuationToken"]
        else:
            break

    print(f"Garage sync: {count} objects, every one sha256-verified -> {out_dir}")
    return out_dir, count


def main() -> int:
    settings = load_settings()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

    db_path = backup_database(settings, timestamp)
    objects_dir, object_count = backup_objects(settings, timestamp)

    print(f"\nBackup complete: {timestamp}")
    print(f"  database dump: {db_path}")
    print(f"  objects ({object_count}): {objects_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
