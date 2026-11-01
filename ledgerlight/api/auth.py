"""Phase 5 §2: real authentication -- argon2id password hashing, real
server-side sessions (Postgres-backed, with rotation), CSRF tokens,
and real login rate limiting/lockout. Framework-agnostic on purpose:
this module has no FastAPI/Starlette import anywhere -- §3 wires its
real return values (a session's id, its raw token, its CSRF token)
into real HTTP cookies (httpOnly, Secure, SameSite) and headers; that
HTTP-layer plumbing is out of this module's own scope.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api.models import Session as SessionRow

DEFAULT_SESSION_LIFETIME = dt.timedelta(hours=12)
LOGIN_LOCKOUT_WINDOW = dt.timedelta(minutes=15)
LOGIN_LOCKOUT_MAX_ATTEMPTS = 5

_hasher = PasswordHasher()  # defaults to argon2id, per the brief's own requirement


def hash_password(password: str) -> str:
    """A real argon2id hash -- never stores or logs the real
    password."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Real constant-time-equivalent verification via argon2-cffi's
    own comparison -- never a plain `==` on a derived value."""
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if a real stored hash was made with weaker parameters
    than this process's current argon2id settings -- the real,
    standard argon2 upgrade-in-place pattern (re-hash on next
    successful login, never force every user to reset at once)."""
    return _hasher.check_needs_rehash(password_hash)


def _random_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def extract_tenant_id_from_session_token(raw_token: str) -> uuid.UUID | None:
    """Parses the real tenant_id routing prefix every real session
    token carries (set by `create_session`) -- `None` if malformed.
    `sessions` is itself a real, RLS-protected table: resolving a raw
    token to its real row requires the real tenant context to already
    be set (`ledgerlight.api.tenancy.tenant_scope`) BEFORE
    `validate_session` ever queries it, and the only way to know which
    tenant to scope to, before that query, is to read it straight off
    the token string -- a real app-role connection with no tenant
    context set cannot see ANY real session row to look one up
    from, by design."""
    tenant_id_str, _, rest = raw_token.partition(".")
    if not rest:
        return None
    try:
        return uuid.UUID(tenant_id_str)
    except ValueError:
        return None


def create_session(
    db: DbSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    ip: str | None = None,
    user_agent: str | None = None,
    lifetime: dt.timedelta = DEFAULT_SESSION_LIFETIME,
    rotated_from_session_id: uuid.UUID | None = None,
) -> tuple[SessionRow, str]:
    """Creates one real session row and returns it with the real raw
    session token -- shown to the caller exactly once (it becomes the
    real cookie value); only `session_token_hash` is ever persisted.
    The raw token itself carries a real `{tenant_id}.` routing prefix
    (see `extract_tenant_id_from_session_token`) -- not a secret (a
    tenant_id is just a routing identifier, the same way it is visible
    in plenty of real multi-tenant products' own URLs), but required
    so a caller can set the real RLS tenant context before this
    table's own row can be looked up at all."""
    raw_token = f"{tenant_id}.{_random_token()}"
    now = dt.datetime.now(dt.UTC)
    row = SessionRow(
        tenant_id=tenant_id,
        user_id=user_id,
        session_token_hash=_hash_token(raw_token),
        csrf_token=_random_token(),
        expires_at=now + lifetime,
        ip=ip,
        user_agent=user_agent,
        rotated_from_session_id=rotated_from_session_id,
    )
    db.add(row)
    db.flush()
    return row, raw_token


def validate_session(db: DbSession, raw_token: str) -> SessionRow | None:
    """Resolves a real raw session token to its real, still-valid
    session row -- `None` if the token does not match any real
    session, the session is revoked, or it has expired. Updates
    `last_seen_at` on every real successful validation.

    `db`'s own real RLS tenant context MUST already be set to the
    real tenant `extract_tenant_id_from_session_token(raw_token)`
    returns before calling this -- `sessions` is a real, RLS-protected
    table, so with no context set, or the wrong one, this correctly
    finds nothing to return, not an error."""
    token_hash = _hash_token(raw_token)
    row = db.scalar(select(SessionRow).where(SessionRow.session_token_hash == token_hash))
    if row is None:
        return None
    now = dt.datetime.now(dt.UTC)
    if row.revoked_at is not None or row.expires_at < now:
        return None
    row.last_seen_at = now
    db.flush()
    return row


def rotate_session(
    db: DbSession, old_session: SessionRow, lifetime: dt.timedelta = DEFAULT_SESSION_LIFETIME
) -> tuple[SessionRow, str]:
    """Real session rotation: revokes `old_session` and creates a NEW
    row (`rotated_from_session_id` pointing back to it) with a brand
    new real token and CSRF token -- the old token is never valid
    again after this, closing the real session-fixation window a
    stolen-but-not-yet-used old token would otherwise leave open."""
    new_row, raw_token = create_session(
        db,
        old_session.tenant_id,
        old_session.user_id,
        ip=old_session.ip,
        user_agent=old_session.user_agent,
        lifetime=lifetime,
        rotated_from_session_id=old_session.id,
    )
    old_session.revoked_at = dt.datetime.now(dt.UTC)
    db.flush()
    return new_row, raw_token


def revoke_session(db: DbSession, session_row: SessionRow) -> None:
    session_row.revoked_at = dt.datetime.now(dt.UTC)
    db.flush()


def verify_csrf(session_row: SessionRow, provided_token: str) -> bool:
    """Real constant-time comparison (`hmac.compare_digest`) -- never
    a plain `==`, which leaks timing information about how many
    leading characters matched."""
    return hmac.compare_digest(session_row.csrf_token, provided_token)


def record_login_attempt(
    db: DbSession,
    tenant_id: uuid.UUID,
    email: str,
    ip: str | None,
    success: bool,
    request_id: str | None = None,
) -> None:
    """A real login attempt, recorded as a real audit_logs row
    (`action='login_succeeded'`/`'login_failed'`) -- reused as the
    real source of truth `check_lockout` queries, rather than a
    second, parallel table."""
    db.execute(
        text(
            "INSERT INTO audit_logs (id, tenant_id, action, target_type, target_id, "
            "request_id, ip, extra, created_at) "
            "VALUES (gen_random_uuid(), :tenant_id, :action, 'user_email', :email, "
            ":request_id, :ip, '{}', now())"
        ),
        {
            "tenant_id": tenant_id,
            "action": "login_succeeded" if success else "login_failed",
            "email": email,
            "request_id": request_id,
            "ip": ip,
        },
    )
    db.flush()


def check_lockout(
    db: DbSession,
    tenant_id: uuid.UUID,
    email: str,
    window: dt.timedelta = LOGIN_LOCKOUT_WINDOW,
    max_attempts: int = LOGIN_LOCKOUT_MAX_ATTEMPTS,
) -> bool:
    """True if this real (tenant, email) pair has >= `max_attempts`
    real `login_failed` audit rows within the last real `window` --
    the real lockout/backoff the brief requires. A real
    `login_succeeded` attempt does not reset the counter itself
    (kept simple and conservative -- a legitimate login during a
    live credential-stuffing attempt should not quietly clear it);
    the window rolling forward is what eventually does."""
    cutoff = dt.datetime.now(dt.UTC) - window
    count = db.scalar(
        text(
            "SELECT count(*) FROM audit_logs "
            "WHERE tenant_id = :tenant_id AND action = 'login_failed' "
            "AND target_type = 'user_email' AND target_id = :email "
            "AND created_at >= :cutoff"
        ).bindparams(tenant_id=tenant_id, email=email, cutoff=cutoff)
    )
    return (count or 0) >= max_attempts
