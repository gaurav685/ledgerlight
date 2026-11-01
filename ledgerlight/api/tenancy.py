"""Phase 5 §2: the real per-request tenant context, and the real
app-role engine/session factory the API process actually connects
with (never the owner role migrations use -- see
`docs/adr/0008-api-auth-tenancy.md`).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ledgerlight.config.settings import Settings


def make_app_engine(settings: Settings, db_name: str | None = None) -> Engine:
    return create_engine(settings.app_database_url(db_name), future=True)


def make_app_session_factory(
    settings: Settings, db_name: str | None = None
) -> sessionmaker[Session]:
    """A real session bound to the restricted `ledgerlight_app` role --
    no BYPASSRLS, not a superuser, not the table owner, so every real
    RLS policy actually applies to it. Never used for migrations."""
    return sessionmaker(bind=make_app_engine(settings, db_name), expire_on_commit=False)


@contextmanager
def tenant_scope(session: Session, tenant_id: uuid.UUID) -> Iterator[Session]:
    """Sets the real per-transaction tenant context every RLS policy
    checks (`current_setting('app.tenant_id', true)`), via
    `set_config(..., is_local=true)` -- never a plain `SET LOCAL`
    string, which Postgres does not let bind parameters flow into
    (`SET LOCAL x = $1` is rejected by the extended query protocol;
    `set_config` is a normal function call and takes a normal bound
    parameter like any other). Scoped to exactly the current
    transaction -- reset automatically at commit/rollback, so a
    pooled connection reused for a later, unrelated request can never
    inherit a stale tenant context."""
    session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
    yield session
