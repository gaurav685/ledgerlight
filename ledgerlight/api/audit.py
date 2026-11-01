"""Phase 5 §3: the real, generic append-only audit log writer every
endpoint calls -- `ledgerlight.api.auth`'s own `record_login_attempt`
is a narrower, auth-specific sibling of this same real table."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as DbSession

from ledgerlight.api.models import AuditLog


def write_audit_log(
    db: DbSession,
    tenant_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    actor_api_key_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    request_id: str | None = None,
    ip: str | None = None,
    extra: dict[str, object] | None = None,
) -> AuditLog:
    row = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_api_key_id=actor_api_key_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        ip=ip,
        extra=extra or {},
    )
    db.add(row)
    db.flush()
    return row
