"""Verify local infra health: pgvector extension + a generic-S3 bucket round-trip.

Assumes `docker compose -f infra/docker-compose.yml up -d` has already been
run and both services report healthy. Creates no application schema.

Object storage is Garage (see docs/adr/0003-object-storage.md), which —
unlike MinIO — has no static root user/password: a bucket and an access
key must be provisioned through Garage's own admin CLI (`docker exec ...
/garage ...`) before any S3-API client can use them. That one-time
provisioning step is Garage-specific infra setup, not "application
schema" — the actual round-trip (list/put/get/delete object, then delete
the bucket) is done entirely through a generic boto3 S3 client, so the
object-storage backend can be swapped without any application code change.

Phase 1: the Garage-CLI helpers moved to ledgerlight/storage/garage_admin.py
so scripts/garage_provision.py (which provisions the *persistent* raw-object
bucket/key, as opposed to this script's throwaway one) can reuse them
instead of duplicating the docker-exec logic. Behaviour here is unchanged.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.storage.garage_admin import (  # noqa: E402
    deprovision_key,
    ensure_layout_applied,
    provision_key_and_bucket,
)


def check_postgres_pgvector() -> tuple[bool, str]:
    try:
        import psycopg
    except ImportError:
        return False, "psycopg not installed (dev dependency missing) — cannot check pgvector"

    settings = load_settings()
    dsn = (
        f"host={settings.postgres_host} port={settings.postgres_port} "
        f"dbname={settings.postgres_db} user={settings.postgres_user} "
        f"password={settings.postgres_password}"
    )
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
            row = cur.fetchone()
            conn.commit()
            version = row[0] if row else "unknown"
            return True, f"pgvector extension version: {version}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {exc}"


def check_s3_bucket_roundtrip() -> tuple[bool, str]:
    try:
        import boto3
        from botocore.client import Config
    except ImportError:
        return False, "boto3 not installed (dev dependency missing) — cannot check S3"

    settings = load_settings()
    suffix = uuid.uuid4().hex[:8]
    bucket = f"ledgerlight-phase0-check-{suffix}"
    key_name = f"ledgerlight-phase0-check-{suffix}"

    try:
        ensure_layout_applied()
        access_key_id, secret_access_key = provision_key_and_bucket(bucket, key_name)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, StopIteration) as exc:
        return False, f"Garage CLI provisioning failed: {exc}"

    endpoint = f"http://{settings.s3_endpoint}"
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(signature_version="s3v4"),
            region_name=settings.s3_region,
        )
        s3.put_object(Bucket=bucket, Key="healthcheck.txt", Body=b"ledgerlight phase0 infra-check")
        body = s3.get_object(Bucket=bucket, Key="healthcheck.txt")["Body"].read()
        if body != b"ledgerlight phase0 infra-check":
            return False, f"round-trip content mismatch: got {body!r}"
        s3.delete_object(Bucket=bucket, Key="healthcheck.txt")
        s3.delete_bucket(Bucket=bucket)
        return (
            True,
            f"created, wrote/read/deleted an object in, and deleted bucket '{bucket}' via boto3",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {exc}"
    finally:
        # best-effort cleanup; a failure here does not affect the check's PASS/FAIL result
        with contextlib.suppress(subprocess.CalledProcessError):
            deprovision_key(key_name)


def main() -> int:
    pg_ok, pg_detail = check_postgres_pgvector()
    print(f"[{'PASS' if pg_ok else 'FAIL'}] Postgres + pgvector: {pg_detail}")

    s3_ok, s3_detail = check_s3_bucket_roundtrip()
    print(f"[{'PASS' if s3_ok else 'FAIL'}] S3 (Garage) bucket round-trip: {s3_detail}")

    return 0 if (pg_ok and s3_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
