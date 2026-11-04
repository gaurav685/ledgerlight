"""Phase 5 §8: a REAL restore drill -- not simulated.

Restores the most recent `scripts/backup.py` output into a fresh,
disposable Postgres database and a fresh, disposable Garage bucket, then
verifies and prints real evidence: every real table's row count in the
restored database compared against the real source database, and every
restored object's sha256 compared against its own content-addressed key.
The drill database and bucket are dropped again at the end -- this script
proves a restore WORKS, it is not meant to leave a second live copy of
real data sitting around.

Usage: `python scripts/restore_drill.py` (always operates on the most
recent backup under `../ledgerlight-backups/`).
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from ledgerlight.common.hashing import sha256_bytes  # noqa: E402
from ledgerlight.config.settings import Settings, load_settings  # noqa: E402
from ledgerlight.storage.garage_admin import (  # noqa: E402
    bucket_exists,
    deprovision_key,
    garage_cli,
    provision_key_and_bucket,
)

POSTGRES_CONTAINER = "ledgerlight-phase0-postgres-1"
BACKUP_ROOT = REPO_ROOT.parent / "ledgerlight-backups"
DRILL_DB = "ledgerlight_restore_drill"
DRILL_BUCKET = "ledgerlight-raw-restore-drill"
DRILL_KEY_NAME = "ledgerlight-restore-drill"


def _latest(subdir: str) -> Path:
    candidates = sorted((BACKUP_ROOT / subdir).iterdir())
    if not candidates:
        raise RuntimeError(f"no backups found under {BACKUP_ROOT / subdir} -- run backup.py first")
    return candidates[-1]


def _psql(*args: str) -> str:
    proc = subprocess.run(
        ["docker", "exec", POSTGRES_CONTAINER, "psql", "-U", "ledgerlight", *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return proc.stdout


def restore_database(settings: Settings, dump_path: Path) -> None:
    print(f"Restoring {dump_path} into a fresh database {DRILL_DB!r}...")
    _psql("-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {DRILL_DB}")
    _psql("-d", "postgres", "-c", f"CREATE DATABASE {DRILL_DB} OWNER {settings.postgres_user}")

    with (BACKUP_ROOT / "_restore_drill.dump").open("wb") as fh:
        fh.write(dump_path.read_bytes())
    subprocess.run(
        [
            "docker",
            "cp",
            str(BACKUP_ROOT / "_restore_drill.dump"),
            f"{POSTGRES_CONTAINER}:/tmp/drill.dump",
        ],
        check=True,
        timeout=120,
    )
    (BACKUP_ROOT / "_restore_drill.dump").unlink()

    proc = subprocess.run(
        [
            "docker",
            "exec",
            POSTGRES_CONTAINER,
            "pg_restore",
            "-U",
            settings.postgres_user,
            "-d",
            DRILL_DB,
            "--no-owner",
            "/tmp/drill.dump",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    # pg_restore commonly exits non-zero on harmless warnings (e.g. a role
    # that doesn't exist in the drill database for a GRANT statement) --
    # the real correctness check is the row-count comparison below, not
    # this exit code.
    if "error" in proc.stderr.lower():
        print(proc.stderr)


def compare_row_counts(settings: Settings) -> list[tuple[str, int, int]]:
    source_engine = create_engine(settings.database_url())
    drill_engine = create_engine(settings.database_url(DRILL_DB))

    with source_engine.connect() as conn:
        tables = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "ORDER BY tablename"
                )
            )
        ]

    mismatches: list[tuple[str, int, int]] = []
    print(f"\n{'table':<35} {'source':>10} {'restored':>10}")
    print("-" * 57)
    with source_engine.connect() as src_conn, drill_engine.connect() as drill_conn:
        for table in tables:
            source_count: int = src_conn.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar_one()
            drill_count: int = drill_conn.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar_one()
            flag = "" if source_count == drill_count else "  <-- MISMATCH"
            print(f"{table:<35} {source_count:>10} {drill_count:>10}{flag}")
            if source_count != drill_count:
                mismatches.append((table, source_count, drill_count))

    source_engine.dispose()
    drill_engine.dispose()
    return mismatches


def restore_objects(objects_dir: Path) -> tuple[int, int]:
    print(f"\nRestoring {objects_dir} into a fresh bucket {DRILL_BUCKET!r}...")
    if bucket_exists(DRILL_BUCKET):
        garage_cli("bucket", "delete", "--yes", DRILL_BUCKET)
    access_key_id, secret_access_key = provision_key_and_bucket(DRILL_BUCKET, DRILL_KEY_NAME)

    import boto3
    from botocore.client import Config

    settings = load_settings()
    client = boto3.client(
        "s3",
        endpoint_url=f"http://{settings.s3_endpoint}",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name=settings.s3_region,
    )

    uploaded = 0
    verified = 0
    for path in objects_dir.rglob("*"):
        if not path.is_file():
            continue
        key = str(path.relative_to(objects_dir)).replace("\\", "/")
        body = path.read_bytes()
        client.put_object(Bucket=DRILL_BUCKET, Key=key, Body=body)
        uploaded += 1

        readback = client.get_object(Bucket=DRILL_BUCKET, Key=key)["Body"].read()
        expected_hash = key.rsplit("/", 1)[-1].split(".", 1)[0]
        actual_hash = sha256_bytes(readback)
        if actual_hash == expected_hash:
            verified += 1
        else:
            print(f"  HASH MISMATCH restoring {key!r}: expected {expected_hash}, got {actual_hash}")

    print(f"Restored {uploaded} objects, {verified} sha256-verified after restore.")
    return uploaded, verified


def cleanup() -> None:
    print("\nCleaning up drill resources...")
    _psql("-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {DRILL_DB}")
    if bucket_exists(DRILL_BUCKET):
        garage_cli("bucket", "delete", "--yes", DRILL_BUCKET)
    # key may not exist if provisioning failed partway
    with contextlib.suppress(subprocess.CalledProcessError):
        deprovision_key(DRILL_KEY_NAME)
    print("Drill database and bucket removed.")


def main() -> int:
    settings = load_settings()
    dump_path = _latest("db")
    objects_dir = _latest("objects")

    restore_database(settings, dump_path)
    mismatches = compare_row_counts(settings)
    uploaded, verified = restore_objects(objects_dir)

    cleanup()

    print(f"\n{'=' * 57}")
    print(f"RESTORE DRILL: {dump_path.name} + {objects_dir.name}")
    print(f"Row counts: {'ALL MATCH' if not mismatches else f'{len(mismatches)} MISMATCHES'}")
    print(f"Objects: {uploaded} restored, {verified} sha256-verified")
    print(f"{'=' * 57}")

    return 1 if (mismatches or uploaded != verified) else 0


if __name__ == "__main__":
    raise SystemExit(main())
