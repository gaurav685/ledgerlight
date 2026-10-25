"""Garage admin-CLI helpers (`docker exec <container> /garage ...`).

Extracted from scripts/infra_check.py in Phase 1 so scripts/garage_provision.py
(which provisions a *persistent* key+bucket, versus infra_check's throwaway
one) can reuse the exact same layout-bootstrap and key/bucket logic instead
of duplicating it. Behaviour is unchanged from Phase 0/Correction 1.
"""

from __future__ import annotations

import subprocess

GARAGE_CONTAINER = "ledgerlight-phase0-garage-1"  # from infra/docker-compose.yml: name + service


def garage_cli(*args: str) -> str:
    proc = subprocess.run(
        ["docker", "exec", GARAGE_CONTAINER, "/garage", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return proc.stdout


def ensure_layout_applied() -> None:
    status = garage_cli("status")
    if "NO ROLE ASSIGNED" not in status:
        return  # already has a role from a previous run against the same volume
    node_id = None
    for line in status.splitlines():
        if "NO ROLE ASSIGNED" in line:
            node_id = line.split()[0]
            break
    if node_id is None:
        raise RuntimeError(f"could not parse node id from `garage status`:\n{status}")
    garage_cli("layout", "assign", node_id, "-z", "dc1", "-c", "1G")
    layout = garage_cli("layout", "show")
    version_line = next(ln for ln in layout.splitlines() if "layout apply --version" in ln)
    version = version_line.strip().split("--version")[1].strip()
    garage_cli("layout", "apply", "--version", version)


def provision_key_and_bucket(bucket: str, key_name: str) -> tuple[str, str]:
    """Create (or reuse) a bucket and an access key with rw access to it.

    Idempotent: if the bucket/key already exist this still returns a
    usable (access_key_id, secret_access_key) pair where possible — but
    note Garage only prints a key's secret at `key create` time, so a
    truly pre-existing key's secret cannot be recovered this way (callers
    needing persistence should keep the returned secret, e.g. in .env).
    """
    created = garage_cli("key", "create", key_name)
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
    garage_cli("bucket", "create", bucket)
    garage_cli("bucket", "allow", "--read", "--write", "--owner", bucket, "--key", key_name)
    return access_key_id, secret_access_key


def deprovision_key(key_name: str) -> None:
    garage_cli("key", "delete", "--yes", key_name)


def bucket_exists(bucket: str) -> bool:
    listing = garage_cli("bucket", "list")
    return any(line.strip() == bucket for line in listing.splitlines())


def key_exists(key_name: str) -> bool:
    listing = garage_cli("key", "list")
    return any(key_name in line for line in listing.splitlines())
