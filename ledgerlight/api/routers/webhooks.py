"""Phase 5 §3: webhook register/test/list-deliveries. `webhooks`/
`webhook_deliveries` are real, tenant-owned, RLS-protected tables.
Gated behind `MANAGE_WEBHOOKS` (`tenant_admin` only). Every real
SSRF/signing concern lives in `ledgerlight.api.webhooks` -- this
router only wires it to real HTTP and real storage.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api import audit, rbac
from ledgerlight.api import webhooks as webhooks_module
from ledgerlight.api.deps import Identity, get_db, require_permission
from ledgerlight.api.models import Webhook, WebhookDelivery
from ledgerlight.api.schemas import (
    WebhookCreateRequest,
    WebhookCreateResponse,
    WebhookDeliveryOut,
    WebhookOut,
)
from ledgerlight.config.settings import load_settings

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])

_MANAGE = Depends(require_permission(rbac.MANAGE_WEBHOOKS))


def _to_out(row: Webhook) -> WebhookOut:
    return WebhookOut(id=row.id, url=row.url, is_active=row.is_active, created_at=row.created_at)


def _get_owned_webhook(db: DbSession, webhook_id: uuid.UUID) -> Webhook:
    row = db.get(Webhook, webhook_id)
    if row is None:
        raise HTTPException(status_code=404, detail="webhook not found")
    return row


@router.get("", response_model=list[WebhookOut], dependencies=[_MANAGE])
def list_webhooks(db: DbSession = Depends(get_db)) -> list[WebhookOut]:
    rows = db.scalars(select(Webhook).order_by(Webhook.created_at)).all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=WebhookCreateResponse, status_code=201)
def create_webhook(
    payload: WebhookCreateRequest,
    identity: Identity = Depends(require_permission(rbac.MANAGE_WEBHOOKS)),
    db: DbSession = Depends(get_db),
) -> WebhookCreateResponse:
    if identity.user_id is None:
        raise HTTPException(
            status_code=400,
            detail="webhooks can only be created by a real session-authenticated user",
        )
    try:
        webhooks_module.validate_webhook_url(payload.url)
    except webhooks_module.UnsafeWebhookUrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    settings = load_settings()
    raw_secret = webhooks_module.generate_webhook_secret()
    row = Webhook(
        tenant_id=identity.tenant_id,
        url=payload.url,
        secret_encrypted=webhooks_module.encrypt_secret(settings, raw_secret),
        created_by=identity.user_id,
    )
    db.add(row)
    db.flush()
    audit.write_audit_log(
        db,
        identity.tenant_id,
        "webhook_registered",
        actor_user_id=identity.user_id,
        target_type="webhook",
        target_id=str(row.id),
    )
    return WebhookCreateResponse(
        id=row.id, url=row.url, is_active=row.is_active, raw_secret=raw_secret
    )


@router.delete("/{webhook_id}", status_code=204, response_model=None, dependencies=[_MANAGE])
def delete_webhook(webhook_id: uuid.UUID, db: DbSession = Depends(get_db)) -> None:
    row = _get_owned_webhook(db, webhook_id)
    db.delete(row)


@router.post("/{webhook_id}/test", response_model=WebhookDeliveryOut)
def test_webhook(
    webhook_id: uuid.UUID,
    identity: Identity = Depends(require_permission(rbac.MANAGE_WEBHOOKS)),
    db: DbSession = Depends(get_db),
) -> WebhookDeliveryOut:
    """Sends one real, signed test delivery -- re-validates the real
    URL immediately before sending (never only at registration time),
    same as every other real delivery (`ledgerlight.api.webhooks.deliver_webhook`)."""
    webhook = _get_owned_webhook(db, webhook_id)
    settings = load_settings()
    secret = webhooks_module.decrypt_secret(settings, webhook.secret_encrypted)
    payload_bytes = json.dumps({"type": "test", "webhook_id": str(webhook_id)}).encode("utf-8")

    result = webhooks_module.deliver_webhook(webhook.url, secret, payload_bytes, sleep=False)

    delivery = WebhookDelivery(
        tenant_id=identity.tenant_id,
        webhook_id=webhook.id,
        payload={"type": "test", "webhook_id": str(webhook_id)},
        signature=webhooks_module.sign_payload(secret, payload_bytes, 0),
        attempt_count=result.attempt,
        status="success" if result.success else "failed",
        response_code=result.status_code,
    )
    db.add(delivery)
    db.flush()
    return WebhookDeliveryOut(
        id=delivery.id,
        webhook_id=delivery.webhook_id,
        status=delivery.status,
        attempt_count=delivery.attempt_count,
        response_code=delivery.response_code,
        created_at=delivery.created_at,
        delivered_at=delivery.delivered_at,
    )


@router.get(
    "/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut], dependencies=[_MANAGE]
)
def list_webhook_deliveries(
    webhook_id: uuid.UUID, db: DbSession = Depends(get_db)
) -> list[WebhookDeliveryOut]:
    _get_owned_webhook(db, webhook_id)
    rows = db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
    ).all()
    return [
        WebhookDeliveryOut(
            id=row.id,
            webhook_id=row.webhook_id,
            status=row.status,
            attempt_count=row.attempt_count,
            response_code=row.response_code,
            created_at=row.created_at,
            delivered_at=row.delivered_at,
        )
        for row in rows
    ]
