"""Phase 5 §3: real health/readiness endpoints -- `/healthz` never
touches the database (process-liveness only); `/readyz` runs one real
query against the real app-role connection, so a broken DB connection
or RLS/grant misconfiguration shows up as unready, not a 200."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(db: DbSession = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - deliberately reported as unready, not a 500
        raise HTTPException(status_code=503, detail=f"database not ready: {exc}") from exc
    return {"status": "ready"}
