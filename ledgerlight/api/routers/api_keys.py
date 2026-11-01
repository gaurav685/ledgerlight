"""Phase 5 §3: API key management -- create (shown once), list,
revoke. `api_keys` is a real, tenant-owned, RLS-protected table.
Gated behind `MANAGE_API_KEYS` (`tenant_admin` only, per
`docs/security/rbac.md`) -- an API key is tenant-wide credential
material, never a per-analyst "own" resource the way a watchlist is.
"""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api import api_keys as api_keys_module
from ledgerlight.api import audit, rbac
from ledgerlight.api.deps import Identity, get_db, require_csrf, require_permission
from ledgerlight.api.models import ApiKey
from ledgerlight.api.schemas import ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyOut

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])

_MANAGE = Depends(require_permission(rbac.MANAGE_API_KEYS))


def _to_out(row: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=cast("list[str]", row.scopes),
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
    )


@router.get("", response_model=list[ApiKeyOut], dependencies=[_MANAGE])
def list_api_keys(db: DbSession = Depends(get_db)) -> list[ApiKeyOut]:
    rows = db.scalars(select(ApiKey).order_by(ApiKey.created_at)).all()
    return [_to_out(row) for row in rows]


@router.post(
    "", response_model=ApiKeyCreateResponse, status_code=201, dependencies=[Depends(require_csrf)]
)
def create_api_key(
    payload: ApiKeyCreateRequest,
    identity: Identity = Depends(require_permission(rbac.MANAGE_API_KEYS)),
    db: DbSession = Depends(get_db),
) -> ApiKeyCreateResponse:
    if identity.user_id is None:
        raise HTTPException(
            status_code=400,
            detail="API keys can only be created by a real session-authenticated user",
        )
    row, raw_key = api_keys_module.create_api_key(
        db, identity.tenant_id, identity.user_id, payload.name, payload.scopes, payload.expires_at
    )
    audit.write_audit_log(
        db,
        identity.tenant_id,
        "api_key_created",
        actor_user_id=identity.user_id,
        target_type="api_key",
        target_id=str(row.id),
    )
    return ApiKeyCreateResponse(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=cast("list[str]", row.scopes),
        expires_at=row.expires_at,
        raw_key=raw_key,
    )


@router.delete(
    "/{api_key_id}", status_code=204, response_model=None, dependencies=[Depends(require_csrf)]
)
def revoke_api_key(
    api_key_id: uuid.UUID,
    identity: Identity = Depends(require_permission(rbac.MANAGE_API_KEYS)),
    db: DbSession = Depends(get_db),
) -> None:
    row = db.get(ApiKey, api_key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="API key not found")
    api_keys_module.revoke_api_key(db, row)
    audit.write_audit_log(
        db,
        identity.tenant_id,
        "api_key_revoked",
        actor_user_id=identity.user_id,
        target_type="api_key",
        target_id=str(api_key_id),
    )
