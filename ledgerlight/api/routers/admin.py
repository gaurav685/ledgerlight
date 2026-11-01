"""Phase 5 §3: tenant admin -- user/role management and the audit
log viewer. Everything here is gated behind `MANAGE_USERS` (users) or
`VIEW_AUDIT_LOG` (audit log), both `tenant_admin`-only per
`docs/security/rbac.md`. No email-sending "invite" flow exists in
this project -- a tenant_admin creates a new user with a real,
caller-supplied password directly (simplified, but still a real
argon2id hash, never a plaintext default).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api import audit, auth, rbac
from ledgerlight.api.deps import Identity, get_db, require_permission
from ledgerlight.api.models import ROLES, AuditLog, Membership, User
from ledgerlight.api.schemas import AuditLogOut, RoleUpdateRequest, UserCreateRequest, UserOut

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _user_out(user: User, membership: Membership) -> UserOut:
    return UserOut(
        user_id=user.id,
        email=user.email,
        role=membership.role,
        membership_status=membership.status,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[UserOut])
def list_users(
    identity: Identity = Depends(require_permission(rbac.MANAGE_USERS)),
    db: DbSession = Depends(get_db),
) -> list[UserOut]:
    rows = db.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == identity.tenant_id)
        .order_by(User.created_at)
    ).all()
    return [_user_out(user, membership) for user, membership in rows]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreateRequest,
    identity: Identity = Depends(require_permission(rbac.MANAGE_USERS)),
    db: DbSession = Depends(get_db),
) -> UserOut:
    if payload.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
    existing = db.scalar(
        select(User).where(User.tenant_id == identity.tenant_id, User.email == payload.email)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="a user with this email already exists")

    user = User(
        tenant_id=identity.tenant_id,
        email=payload.email,
        password_hash=auth.hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    membership = Membership(
        tenant_id=identity.tenant_id,
        user_id=user.id,
        role=payload.role,
        status="active",
        invited_by=identity.user_id,
    )
    db.add(membership)
    db.flush()
    audit.write_audit_log(
        db,
        identity.tenant_id,
        "user_created",
        actor_user_id=identity.user_id,
        target_type="user",
        target_id=str(user.id),
        extra={"role": payload.role},
    )
    return _user_out(user, membership)


def _get_membership(db: DbSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    membership = db.scalar(
        select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="user not found in this tenant")
    return membership


@router.patch("/users/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: uuid.UUID,
    payload: RoleUpdateRequest,
    identity: Identity = Depends(require_permission(rbac.MANAGE_USERS)),
    db: DbSession = Depends(get_db),
) -> UserOut:
    if payload.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
    membership = _get_membership(db, identity.tenant_id, user_id)
    user = db.get(User, user_id)
    assert user is not None, "a membership row always has a real, existing user"

    before_role = membership.role
    membership.role = payload.role
    db.flush()
    audit.write_audit_log(
        db,
        identity.tenant_id,
        "user_role_changed",
        actor_user_id=identity.user_id,
        target_type="user",
        target_id=str(user_id),
        extra={"before_role": before_role, "after_role": payload.role},
    )
    return _user_out(user, membership)


@router.delete("/users/{user_id}", status_code=204, response_model=None)
def revoke_user(
    user_id: uuid.UUID,
    identity: Identity = Depends(require_permission(rbac.MANAGE_USERS)),
    db: DbSession = Depends(get_db),
) -> None:
    """Revokes the real membership (status='revoked') -- never a hard
    delete of the `User` row itself, which would break every real
    historical audit_logs/review_decisions_audit row still referencing
    it by id."""
    membership = _get_membership(db, identity.tenant_id, user_id)
    membership.status = "revoked"
    db.flush()
    audit.write_audit_log(
        db,
        identity.tenant_id,
        "user_revoked",
        actor_user_id=identity.user_id,
        target_type="user",
        target_id=str(user_id),
    )


@router.get("/audit-log", response_model=list[AuditLogOut])
def list_audit_log(
    identity: Identity = Depends(require_permission(rbac.VIEW_AUDIT_LOG)),
    db: DbSession = Depends(get_db),
) -> list[AuditLogOut]:
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == identity.tenant_id)
        .order_by(AuditLog.created_at.desc())
        .limit(500)
    ).all()
    return [
        AuditLogOut(
            id=row.id,
            actor_user_id=row.actor_user_id,
            actor_api_key_id=row.actor_api_key_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            created_at=row.created_at,
        )
        for row in rows
    ]
