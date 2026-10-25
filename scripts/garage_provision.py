"""One-time provisioning of the persistent raw-object-storage bucket/key.

Unlike scripts/infra_check.py's throwaway per-run bucket, this creates (or
reuses) a stable bucket and access key for Phase 1's actual raw storage,
and writes the resulting credentials into .env (gitignored) so subsequent
runs of store-backfill / ingestion don't re-provision.

Idempotent: if LEDGERLIGHT_S3_ACCESS_KEY_ID is already set in .env, this
does nothing (Garage cannot print an existing key's secret again, so a
missing secret with a present key cannot be recovered — delete the key in
Garage and re-run this script if that happens).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.storage.garage_admin import (  # noqa: E402
    bucket_exists,
    ensure_layout_applied,
    garage_cli,
    key_exists,
    provision_key_and_bucket,
)

ENV_PATH = REPO_ROOT / ".env"
KEY_NAME = "ledgerlight-raw-store"


def _append_env_vars(pairs: dict[str, str]) -> None:
    existing = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    lines = [f"{k}={v}" for k, v in pairs.items() if f"{k}=" not in existing]
    if not lines:
        return
    with ENV_PATH.open("a", encoding="utf-8") as fh:
        fh.write("\n" + "\n".join(lines) + "\n")


def main() -> int:
    settings = load_settings()

    if settings.s3_access_key_id and settings.s3_secret_access_key:
        print(f"Already provisioned: bucket={settings.s3_bucket!r}, key already in .env. No-op.")
        return 0

    ensure_layout_applied()

    if key_exists(KEY_NAME):
        print(
            f"ERROR: Garage key '{KEY_NAME}' already exists but "
            "LEDGERLIGHT_S3_ACCESS_KEY_ID is not in .env — its secret cannot be "
            "recovered. Delete the key in Garage "
            f"(docker exec <garage> /garage key delete --yes {KEY_NAME}) and re-run."
        )
        return 1

    if bucket_exists(settings.s3_bucket):
        # Bucket exists (e.g. a prior partial run) but the key doesn't — create
        # just the key and grant it, rather than re-creating the bucket.
        created = garage_cli("key", "create", KEY_NAME)
        access_key_id = next(
            ln.split(":", 1)[1].strip()
            for ln in created.splitlines()
            if ln.strip().startswith("Key ID:")
        )
        secret_access_key = next(
            ln.split(":", 1)[1].strip()
            for ln in created.splitlines()
            if ln.strip().startswith("Secret key:")
        )
        garage_cli(
            "bucket", "allow", "--read", "--write", "--owner", settings.s3_bucket, "--key", KEY_NAME
        )
    else:
        access_key_id, secret_access_key = provision_key_and_bucket(settings.s3_bucket, KEY_NAME)

    _append_env_vars(
        {
            "LEDGERLIGHT_S3_ACCESS_KEY_ID": access_key_id,
            "LEDGERLIGHT_S3_SECRET_ACCESS_KEY": secret_access_key,
        }
    )
    print(f"Provisioned bucket '{settings.s3_bucket}' and key '{KEY_NAME}'; wrote creds to .env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
