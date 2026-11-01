"""Phase 5 §3: alert rules + alerts. `alert_rules`/`alerts` are real,
tenant-owned, RLS-protected tables -- same story as
`routers.watchlists`. An alert rule is always attached to one of the
caller's own watchlists (`MANAGE_OWN_WATCHLISTS`'s own ownership
check is reused here, not duplicated); the real Dagster job that
evaluates rules against new events/scores lives in
`ledgerlight.orchestration` (§3's own "alerts generation" job), not
in this router.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api import rbac
from ledgerlight.api.deps import Identity, get_db, require_csrf, require_permission
from ledgerlight.api.models import Alert, AlertRule, Watchlist
from ledgerlight.api.routers.watchlists import get_owned_watchlist
from ledgerlight.api.schemas import AlertOut, AlertRuleCreateRequest, AlertRuleOut

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])

_VALID_RULE_TYPES = ("new_event_type", "score_percentile_threshold")


def _rule_out(row: AlertRule) -> AlertRuleOut:
    return AlertRuleOut(
        id=row.id,
        watchlist_id=row.watchlist_id,
        rule_type=row.rule_type,
        config=row.config,
        is_active=row.is_active,
        created_at=row.created_at,
    )


def _alert_out(row: Alert) -> AlertOut:
    return AlertOut(
        id=row.id,
        alert_rule_id=row.alert_rule_id,
        company_id=row.company_id,
        payload=row.payload,
        triggered_at=row.triggered_at,
        acknowledged_at=row.acknowledged_at,
    )


@router.get("/rules", response_model=list[AlertRuleOut])
def list_alert_rules(
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> list[AlertRuleOut]:
    query = select(AlertRule).order_by(AlertRule.created_at)
    if not rbac.has_permission(identity.role, rbac.MANAGE_ALL_WATCHLISTS):
        query = query.join(Watchlist, Watchlist.id == AlertRule.watchlist_id).where(
            Watchlist.user_id == identity.user_id
        )
    rows = db.scalars(query).all()
    return [_rule_out(row) for row in rows]


@router.post(
    "/rules", response_model=AlertRuleOut, status_code=201, dependencies=[Depends(require_csrf)]
)
def create_alert_rule(
    payload: AlertRuleCreateRequest,
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> AlertRuleOut:
    if payload.rule_type not in _VALID_RULE_TYPES:
        raise HTTPException(status_code=422, detail=f"rule_type must be one of {_VALID_RULE_TYPES}")
    get_owned_watchlist(db, identity, payload.watchlist_id)  # real ownership gate
    row = AlertRule(
        tenant_id=identity.tenant_id,
        watchlist_id=payload.watchlist_id,
        rule_type=payload.rule_type,
        config=payload.config,
        created_by=identity.user_id,
    )
    db.add(row)
    db.flush()
    return _rule_out(row)


@router.delete(
    "/rules/{rule_id}", status_code=204, response_model=None, dependencies=[Depends(require_csrf)]
)
def delete_alert_rule(
    rule_id: uuid.UUID,
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> None:
    row = db.get(AlertRule, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="alert rule not found")
    get_owned_watchlist(db, identity, row.watchlist_id)  # real ownership gate
    db.delete(row)


@router.get("", response_model=list[AlertOut])
def list_alerts(
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> list[AlertOut]:
    query = select(Alert).order_by(Alert.triggered_at.desc())
    if not rbac.has_permission(identity.role, rbac.MANAGE_ALL_WATCHLISTS):
        query = (
            query.join(AlertRule, AlertRule.id == Alert.alert_rule_id)
            .join(Watchlist, Watchlist.id == AlertRule.watchlist_id)
            .where(Watchlist.user_id == identity.user_id)
        )
    rows = db.scalars(query).all()
    return [_alert_out(row) for row in rows]


@router.post(
    "/{alert_id}/acknowledge", response_model=AlertOut, dependencies=[Depends(require_csrf)]
)
def acknowledge_alert(
    alert_id: uuid.UUID,
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> AlertOut:
    row = db.get(Alert, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="alert not found")
    rule = db.get(AlertRule, row.alert_rule_id)
    assert rule is not None, "alert_rules.id is a real DB-level FK -- always resolvable"
    get_owned_watchlist(db, identity, rule.watchlist_id)  # real ownership gate

    row.acknowledged_at = dt.datetime.now(dt.UTC)
    row.acknowledged_by = identity.user_id
    db.flush()
    return _alert_out(row)
