"""Verify local infra health: pgvector extension + MinIO bucket round-trip.

Assumes `docker compose -f infra/docker-compose.yml up -d` has already been
run and both services report healthy. Creates no application schema.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402


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


def check_minio_bucket_roundtrip() -> tuple[bool, str]:
    try:
        import boto3
        from botocore.client import Config
    except ImportError:
        return False, "boto3 not installed (dev dependency missing) — cannot check MinIO"

    settings = load_settings()
    bucket = f"ledgerlight-phase0-check-{uuid.uuid4().hex[:8]}"
    endpoint = f"http://{settings.minio_endpoint}"
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.minio_root_user,
            aws_secret_access_key=settings.minio_root_password,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        s3.create_bucket(Bucket=bucket)
        s3.delete_bucket(Bucket=bucket)
        return True, f"created and deleted test bucket '{bucket}'"
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {exc}"


def main() -> int:
    pg_ok, pg_detail = check_postgres_pgvector()
    print(f"[{'PASS' if pg_ok else 'FAIL'}] Postgres + pgvector: {pg_detail}")

    minio_ok, minio_detail = check_minio_bucket_roundtrip()
    print(f"[{'PASS' if minio_ok else 'FAIL'}] MinIO bucket round-trip: {minio_detail}")

    return 0 if (pg_ok and minio_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
