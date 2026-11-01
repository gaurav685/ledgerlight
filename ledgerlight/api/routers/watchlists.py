"""Phase 5 §3: watchlists CRUD. `watchlists`/`watchlist_items` are
real, tenant-owned, RLS-protected tables (migration `4dad2cd00443`) --
every query here runs through the plain `get_db`/`get_identity`
dependencies, which already leave the real per-request tenant context
set; no manual filtering is needed, Postgres's own RLS policy does it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api import rbac
from ledgerlight.api.deps import Identity, get_db, require_permission
from ledgerlight.api.models import Watchlist, WatchlistItem
from ledgerlight.api.schemas import (
    WatchlistCreateRequest,
    WatchlistItemCreateRequest,
    WatchlistItemOut,
    WatchlistOut,
)
from ledgerlight.knowledge.models import Company

router = APIRouter(prefix="/v1/watchlists", tags=["watchlists"])


def _to_out(row: Watchlist) -> WatchlistOut:
    return WatchlistOut(id=row.id, name=row.name, created_at=row.created_at)


def get_owned_watchlist(db: DbSession, identity: Identity, watchlist_id: uuid.UUID) -> Watchlist:
    """RLS already restricts this to the caller's real tenant; a role
    with only `MANAGE_OWN_WATCHLISTS` (not `MANAGE_ALL_WATCHLISTS`,
    e.g. `analyst`) is further restricted here to watchlists it
    itself created -- both an invisible-to-this-tenant and a
    belongs-to-a-tenant-mate-but-not-me watchlist 404 identically,
    never a 403 that would confirm a sibling's watchlist exists."""
    row = db.get(Watchlist, watchlist_id)
    if row is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    if row.user_id != identity.user_id and not rbac.has_permission(
        identity.role, rbac.MANAGE_ALL_WATCHLISTS
    ):
        raise HTTPException(status_code=404, detail="watchlist not found")
    return row


@router.get("", response_model=list[WatchlistOut])
def list_watchlists(
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> list[WatchlistOut]:
    query = select(Watchlist).order_by(Watchlist.created_at)
    if not rbac.has_permission(identity.role, rbac.MANAGE_ALL_WATCHLISTS):
        query = query.where(Watchlist.user_id == identity.user_id)
    rows = db.scalars(query).all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=WatchlistOut, status_code=201)
def create_watchlist(
    payload: WatchlistCreateRequest,
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> WatchlistOut:
    row = Watchlist(tenant_id=identity.tenant_id, user_id=identity.user_id, name=payload.name)
    db.add(row)
    db.flush()
    return _to_out(row)


@router.delete("/{watchlist_id}", status_code=204, response_model=None)
def delete_watchlist(
    watchlist_id: uuid.UUID,
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> None:
    row = get_owned_watchlist(db, identity, watchlist_id)
    db.delete(row)


@router.get("/{watchlist_id}/items", response_model=list[WatchlistItemOut])
def list_watchlist_items(
    watchlist_id: uuid.UUID,
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> list[WatchlistItemOut]:
    get_owned_watchlist(db, identity, watchlist_id)
    rows = db.scalars(
        select(WatchlistItem)
        .where(WatchlistItem.watchlist_id == watchlist_id)
        .order_by(WatchlistItem.added_at)
    ).all()
    return [
        WatchlistItemOut(
            id=row.id,
            watchlist_id=row.watchlist_id,
            company_id=row.company_id,
            added_at=row.added_at,
        )
        for row in rows
    ]


@router.post("/{watchlist_id}/items", response_model=WatchlistItemOut, status_code=201)
def add_watchlist_item(
    watchlist_id: uuid.UUID,
    payload: WatchlistItemCreateRequest,
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> WatchlistItemOut:
    get_owned_watchlist(db, identity, watchlist_id)
    if db.get(Company, payload.company_id) is None:
        raise HTTPException(status_code=404, detail="company not found")
    row = WatchlistItem(
        tenant_id=identity.tenant_id, watchlist_id=watchlist_id, company_id=payload.company_id
    )
    db.add(row)
    db.flush()
    return WatchlistItemOut(
        id=row.id, watchlist_id=row.watchlist_id, company_id=row.company_id, added_at=row.added_at
    )


@router.delete("/{watchlist_id}/items/{item_id}", status_code=204, response_model=None)
def remove_watchlist_item(
    watchlist_id: uuid.UUID,
    item_id: uuid.UUID,
    identity: Identity = Depends(require_permission(rbac.MANAGE_OWN_WATCHLISTS)),
    db: DbSession = Depends(get_db),
) -> None:
    get_owned_watchlist(db, identity, watchlist_id)
    row = db.get(WatchlistItem, item_id)
    if row is None or row.watchlist_id != watchlist_id:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    db.delete(row)
