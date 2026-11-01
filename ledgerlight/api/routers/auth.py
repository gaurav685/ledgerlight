"""Phase 5 §3: real login/logout/me -- the first router to exercise
`ledgerlight.api.deps`'s identity-resolution machinery end to end over
real HTTP. Session cookie is httpOnly, SameSite=Lax, Secure per
`Settings.cookie_secure` (false only on plain-http localhost dev)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api import audit, auth, rate_limit
from ledgerlight.api.deps import SESSION_COOKIE_NAME, Identity, get_db, get_identity, require_csrf
from ledgerlight.api.models import Membership, Tenant, User
from ledgerlight.api.schemas import IdentityOut, LoginRequest, LoginResponse
from ledgerlight.api.tenancy import tenant_scope
from ledgerlight.config.settings import load_settings

router = APIRouter(prefix="/v1/auth", tags=["auth"])

LOGIN_RATE_LIMIT_PER_WINDOW = 10
LOGIN_RATE_LIMIT_WINDOW = dt.timedelta(minutes=1)


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest, request: Request, response: Response, db: DbSession = Depends(get_db)
) -> LoginResponse:
    client_ip = request.client.host if request.client else None
    rate_limit.check_and_increment(
        db,
        f"login_ip:{client_ip or 'unknown'}",
        LOGIN_RATE_LIMIT_PER_WINDOW,
        LOGIN_RATE_LIMIT_WINDOW,
    )

    # `tenants` carries no tenant_id of its own and is not RLS-protected
    # (it is the root of tenancy, not a tenant-owned table) -- a real
    # lookup by slug needs no tenant_scope.
    tenant = db.scalar(select(Tenant).where(Tenant.slug == payload.tenant_slug, Tenant.is_active))
    if tenant is None:
        raise HTTPException(status_code=401, detail="invalid tenant, email, or password")

    with tenant_scope(db, tenant.id):
        if auth.check_lockout(db, tenant.id, payload.email):
            raise HTTPException(
                status_code=401, detail="account temporarily locked after too many failed attempts"
            )

        user = db.scalar(
            select(User).where(
                User.tenant_id == tenant.id, User.email == payload.email, User.is_active
            )
        )
        password_ok = user is not None and auth.verify_password(
            payload.password, user.password_hash
        )
        auth.record_login_attempt(
            db, tenant.id, payload.email, client_ip, success=bool(password_ok)
        )
        if not password_ok or user is None:
            raise HTTPException(status_code=401, detail="invalid tenant, email, or password")

        membership = db.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant.id,
                Membership.user_id == user.id,
                Membership.status == "active",
            )
        )
        if membership is None:
            raise HTTPException(status_code=401, detail="this user has no active membership")

        session_row, raw_token = auth.create_session(
            db, tenant.id, user.id, ip=client_ip, user_agent=request.headers.get("User-Agent")
        )
        audit.write_audit_log(
            db,
            tenant.id,
            "login_succeeded",
            actor_user_id=user.id,
            request_id=getattr(request.state, "request_id", None),
            ip=client_ip,
        )

    settings = load_settings()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        raw_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=int(auth.DEFAULT_SESSION_LIFETIME.total_seconds()),
    )
    return LoginResponse(
        identity=IdentityOut(
            user_id=user.id, tenant_id=tenant.id, role=membership.role, api_key_id=None
        ),
        csrf_token=session_row.csrf_token,
    )


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout(
    response: Response, identity: Identity = Depends(get_identity), db: DbSession = Depends(get_db)
) -> dict[str, str]:
    if identity.session_row is not None:
        auth.revoke_session(db, identity.session_row)
        audit.write_audit_log(db, identity.tenant_id, "logout", actor_user_id=identity.user_id)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "logged_out"}


@router.get("/me", response_model=IdentityOut)
def me(identity: Identity = Depends(get_identity)) -> IdentityOut:
    return IdentityOut(
        user_id=identity.user_id,
        tenant_id=identity.tenant_id,
        role=identity.role,
        api_key_id=identity.api_key_id,
    )
