"""Phase 5 §2: real API keys -- shown to the caller once, stored
hashed, with a real prefix for fast lookup, real scopes, expiry,
revocation, and a real last-used timestamp.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api.models import ApiKey

KEY_PREFIX_LEN = 8
_RAW_SECRET_BYTES = 32


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def extract_tenant_id_from_api_key(raw_key: str) -> uuid.UUID | None:
    """Parses the real tenant_id routing segment every real API key
    carries (set by `create_api_key`) -- `None` if malformed.
    `api_keys` is itself a real, RLS-protected table: a caller must
    set the real RLS tenant context (`ledgerlight.api.tenancy.tenant_scope`)
    to this value BEFORE `verify_api_key` can see any real row to look
    one up from at all -- the same real bootstrapping reason
    `ledgerlight.api.auth.extract_tenant_id_from_session_token` exists."""
    parts = raw_key.split(".", 2)
    if len(parts) != 3:
        return None
    try:
        return uuid.UUID(parts[1])
    except ValueError:
        return None


def create_api_key(
    db: DbSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    scopes: list[str],
    expires_at: dt.datetime | None = None,
) -> tuple[ApiKey, str]:
    """Creates one real API key and returns it with the real, full raw
    key -- shown to the caller exactly once; only `key_prefix` (safe
    to display again later, e.g. "llk_a1b2c3d4...") and `key_hash`
    (never the real secret itself) are persisted. The real key carries
    a real `tenant_id` routing segment (see
    `extract_tenant_id_from_api_key`) -- not a secret, just a routing
    identifier, but required for the same real RLS-bootstrapping
    reason a session token's own tenant_id prefix is."""
    prefix = f"llk_{secrets.token_hex(KEY_PREFIX_LEN // 2)}"
    secret = secrets.token_urlsafe(_RAW_SECRET_BYTES)
    raw_key = f"{prefix}.{tenant_id}.{secret}"
    row = ApiKey(
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        key_prefix=prefix,
        key_hash=_hash_key(raw_key),
        scopes=list(scopes),
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    return row, raw_key


def verify_api_key(db: DbSession, raw_key: str) -> ApiKey | None:
    """Resolves a real raw API key to its real, still-valid row --
    `None` if malformed, unknown, revoked, or expired. Updates
    `last_used_at` on every real successful verification. Looks up by
    the real `key_prefix` first (indexed, fast, never ambiguous on
    its own since the full hash is still checked after) rather than
    scanning every real key's hash.

    `db`'s own real RLS tenant context MUST already be set to the real
    tenant `extract_tenant_id_from_api_key(raw_key)` returns before
    calling this."""
    parts = raw_key.split(".", 2)
    if len(parts) != 3:
        return None
    prefix = parts[0]
    row = db.scalar(select(ApiKey).where(ApiKey.key_prefix == prefix))
    if row is None or row.key_hash != _hash_key(raw_key):
        return None
    now = dt.datetime.now(dt.UTC)
    if row.revoked_at is not None:
        return None
    if row.expires_at is not None and row.expires_at < now:
        return None
    row.last_used_at = now
    db.flush()
    return row


def revoke_api_key(db: DbSession, api_key_row: ApiKey) -> None:
    api_key_row.revoked_at = dt.datetime.now(dt.UTC)
    db.flush()


def has_scope(api_key_row: ApiKey, scope: str) -> bool:
    return scope in api_key_row.scopes
