"""Phase 5 §3: real per-request dependencies -- the app-role DB
session (one real transaction per request, tenant-scoped for RLS),
real identity resolution (a session cookie or an API key, never
both assumed), and the real RBAC/CSRF enforcement points every real
endpoint uses.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

import structlog
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from ledgerlight.api import api_keys, auth, rbac
from ledgerlight.api.models import Membership
from ledgerlight.api.models import Session as SessionRow
from ledgerlight.api.tenancy import make_app_session_factory, tenant_scope
from ledgerlight.config.settings import load_settings

SESSION_COOKIE_NAME = "ll_session"


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[DbSession]:
    return make_app_session_factory(load_settings())


def get_db() -> Iterator[DbSession]:
    """One real, app-role-authenticated session per request, wrapped
    in exactly one real transaction spanning the whole request --
    committed on a clean response, rolled back on any exception
    (`Session.begin()`'s own real behaviour)."""
    factory = _session_factory()
    with factory() as session, session.begin():
        yield session


@dataclass
class Identity:
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    api_key_id: uuid.UUID | None
    role: str
    session_row: SessionRow | None = None  # set only for a cookie-authenticated request


def _resolve_identity(request: Request, db: DbSession) -> Identity:
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        raw_api_key = authorization[len("bearer ") :].strip()
        # api_keys is itself a real, RLS-protected table -- the real tenant
        # context must be set from the key's own routing segment BEFORE
        # verify_api_key can see any real row to look one up from at all.
        routing_tenant_id = api_keys.extract_tenant_id_from_api_key(raw_api_key)
        if routing_tenant_id is None:
            raise HTTPException(status_code=401, detail="malformed API key")
        with tenant_scope(db, routing_tenant_id):
            key_row = api_keys.verify_api_key(db, raw_api_key)
            if key_row is None:
                raise HTTPException(status_code=401, detail="invalid or expired API key")
            membership = db.scalar(
                select(Membership).where(
                    Membership.tenant_id == key_row.tenant_id,
                    Membership.user_id == key_row.user_id,
                    Membership.status == "active",
                )
            )
        if membership is None:
            raise HTTPException(
                status_code=401, detail="the API key's own user has no active membership"
            )
        return Identity(
            tenant_id=key_row.tenant_id,
            user_id=key_row.user_id,
            api_key_id=key_row.id,
            role=membership.role,
        )

    raw_session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if raw_session_token:
        # sessions is the same real story -- the routing prefix must be
        # parsed and scoped to before validate_session can see anything.
        routing_tenant_id = auth.extract_tenant_id_from_session_token(raw_session_token)
        if routing_tenant_id is None:
            raise HTTPException(status_code=401, detail="malformed session token")
        with tenant_scope(db, routing_tenant_id):
            session_row = auth.validate_session(db, raw_session_token)
            if session_row is None:
                raise HTTPException(status_code=401, detail="invalid or expired session")
            membership = db.scalar(
                select(Membership).where(
                    Membership.tenant_id == session_row.tenant_id,
                    Membership.user_id == session_row.user_id,
                    Membership.status == "active",
                )
            )
        if membership is None:
            raise HTTPException(
                status_code=401, detail="the session's own user has no active membership"
            )
        return Identity(
            tenant_id=session_row.tenant_id,
            user_id=session_row.user_id,
            api_key_id=None,
            role=membership.role,
            session_row=session_row,
        )

    raise HTTPException(status_code=401, detail="no real session cookie or API key provided")


def get_identity(request: Request, db: DbSession = Depends(get_db)) -> Identity:
    """Resolves the real caller identity AND leaves the real
    per-request tenant context set on `db` for every subsequent real
    query this same request makes -- `_resolve_identity`'s own
    `tenant_scope` blocks each only cover the one membership lookup,
    so it is set again here, for the rest of the request, exactly
    once identity is known."""
    identity = _resolve_identity(request, db)
    with tenant_scope(db, identity.tenant_id):
        pass
    # Phase 5 §8: binds the real tenant_id into every subsequent real
    # structured log line for this request (the request_id is already
    # bound earlier, by app.py's own request-ID middleware, before
    # identity is even known) -- never anything else from `identity`
    # (no email, no raw token) is ever logged.
    structlog.contextvars.bind_contextvars(tenant_id=str(identity.tenant_id))
    return identity


def require_csrf(request: Request, identity: Identity = Depends(get_identity)) -> None:
    """Real CSRF enforcement for cookie-authenticated mutating
    requests. An API-key-authenticated request is never subject to
    this -- a bearer token is never auto-attached by a browser, so
    there is no real CSRF risk for it to defend against."""
    if identity.session_row is None:
        return
    provided = request.headers.get("X-CSRF-Token")
    if not provided or not auth.verify_csrf(identity.session_row, provided):
        raise HTTPException(status_code=403, detail="missing or invalid CSRF token")


def require_permission(permission: str):  # type: ignore[no-untyped-def]
    """A real dependency factory -- `Depends(require_permission(rbac.DECIDE_REVIEW))`
    -- the real, server-side RBAC check every endpoint that needs one
    calls before doing anything else."""

    def _dependency(identity: Identity = Depends(get_identity)) -> Identity:
        if not rbac.has_permission(identity.role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"role {identity.role!r} lacks permission {permission!r}",
            )
        return identity

    return _dependency
