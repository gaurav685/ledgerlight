"""Phase 5 §2: real DB-level Row-Level-Security isolation tests.
Connects as the real, restricted `ledgerlight_app` role (no BYPASSRLS,
not a superuser, not the table owner -- see migration `4dad2cd00443`),
sets a real per-transaction tenant context via
`ledgerlight.api.tenancy.tenant_scope`, and proves a second real
tenant's rows are genuinely invisible AND unwritable -- not merely
filtered by application code that could be bypassed.

Real, committed fixture rows are required here (the app-role
connection is a SEPARATE real connection -- it can only ever see
already-committed data, never another transaction's in-progress
rows), so this uses the same real, independent-session-with-manual-
cleanup pattern as `test_agent_state_machine.py`, never the project's
usual rolled-back `db_session` fixture.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any, cast

import pytest
from sqlalchemy import CursorResult, delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from ledgerlight.api.models import Tenant, User, Watchlist
from ledgerlight.api.tenancy import make_app_session_factory, tenant_scope
from ledgerlight.config.settings import Settings
from ledgerlight.db.session import make_session_factory

pytestmark = pytest.mark.integration


@pytest.fixture
def owner_session() -> Iterator[Session]:
    """A real, independent, committing session via the existing owner
    role -- used only to set up and tear down real fixture rows the
    separate app-role connection must then see as already-committed."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    try:
        settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    except Exception as exc:
        pytest.skip(f"could not load real .env for integration test: {exc}")

    try:
        session = make_session_factory(settings)()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable (is the Docker stack up?): {exc}")

    created_tenant_ids: list[uuid.UUID] = []
    session.info["created_tenant_ids"] = created_tenant_ids
    try:
        yield session
    finally:
        if created_tenant_ids:
            session.execute(
                text("DELETE FROM watchlists WHERE tenant_id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            session.execute(
                text("DELETE FROM users WHERE tenant_id = ANY(:ids)"), {"ids": created_tenant_ids}
            )
            session.execute(
                text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": created_tenant_ids}
            )
            session.commit()
        session.close()


@pytest.fixture
def app_session_factory(owner_session: Session) -> sessionmaker[Session]:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    factory = make_app_session_factory(settings)
    try:
        with factory() as probe:
            probe.execute(select(1))
    except Exception as exc:
        pytest.skip(f"ledgerlight_app role not reachable (migration 4dad2cd00443 applied?): {exc}")
    return factory


def _make_tenant_with_user(session: Session, name: str) -> tuple[Tenant, User]:
    tenant = Tenant(name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    session.flush()
    session.info["created_tenant_ids"].append(tenant.id)
    user = User(tenant_id=tenant.id, email=f"{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    session.flush()
    return tenant, user


def test_tenant_a_cannot_read_tenant_bs_rows(
    owner_session: Session, app_session_factory: sessionmaker[Session]
) -> None:
    tenant_a, user_a = _make_tenant_with_user(owner_session, "RLS Test A")
    tenant_b, user_b = _make_tenant_with_user(owner_session, "RLS Test B")
    owner_session.add(Watchlist(tenant_id=tenant_a.id, user_id=user_a.id, name="A list"))
    owner_session.add(Watchlist(tenant_id=tenant_b.id, user_id=user_b.id, name="B list"))
    owner_session.commit()

    with (
        app_session_factory() as app_session,
        app_session.begin(),
        tenant_scope(app_session, tenant_a.id),
    ):
        rows = (
            app_session.execute(
                select(Watchlist).where(Watchlist.tenant_id.in_([tenant_a.id, tenant_b.id]))
            )
            .scalars()
            .all()
        )
        assert [r.name for r in rows] == ["A list"]


def test_no_tenant_context_sees_zero_rows(
    owner_session: Session, app_session_factory: sessionmaker[Session]
) -> None:
    """Fails closed: a connection with no real tenant context set sees
    NO tenant-owned rows at all, never every tenant's rows by default."""
    tenant_a, user_a = _make_tenant_with_user(owner_session, "RLS No Context A")
    owner_session.add(Watchlist(tenant_id=tenant_a.id, user_id=user_a.id, name="A list"))
    owner_session.commit()

    with app_session_factory() as app_session, app_session.begin():
        rows = (
            app_session.execute(select(Watchlist).where(Watchlist.tenant_id == tenant_a.id))
            .scalars()
            .all()
        )
        assert rows == []


def test_tenant_a_cannot_insert_a_row_claiming_tenant_b(
    owner_session: Session, app_session_factory: sessionmaker[Session]
) -> None:
    """The real WITH CHECK half of the policy: even with INSERT
    privilege at the table level, a real app-role connection scoped to
    tenant A cannot forge a row claiming a different tenant_id."""
    tenant_a, user_a = _make_tenant_with_user(owner_session, "RLS Forge A")
    tenant_b, _user_b = _make_tenant_with_user(owner_session, "RLS Forge B")
    owner_session.commit()

    with (
        app_session_factory() as app_session,
        pytest.raises(DBAPIError),
        app_session.begin(),
        tenant_scope(app_session, tenant_a.id),
    ):
        forged = Watchlist(tenant_id=tenant_b.id, user_id=user_a.id, name="Forged B row")
        app_session.add(forged)
        app_session.flush()


def test_tenant_a_cannot_update_or_delete_tenant_bs_row(
    owner_session: Session, app_session_factory: sessionmaker[Session]
) -> None:
    tenant_a, _user_a = _make_tenant_with_user(owner_session, "RLS Attack A")
    tenant_b, user_b = _make_tenant_with_user(owner_session, "RLS Attack B")
    wl_b = Watchlist(tenant_id=tenant_b.id, user_id=user_b.id, name="B list to attack")
    owner_session.add(wl_b)
    owner_session.commit()
    wl_b_id = wl_b.id

    with (
        app_session_factory() as app_session,
        app_session.begin(),
        tenant_scope(app_session, tenant_a.id),
    ):
        update_stmt = update(Watchlist).where(Watchlist.id == wl_b_id).values(name="HACKED")
        update_result = cast("CursorResult[Any]", app_session.execute(update_stmt))
        assert update_result.rowcount == 0
        delete_result = cast(
            "CursorResult[Any]",
            app_session.execute(delete(Watchlist).where(Watchlist.id == wl_b_id)),
        )
        assert delete_result.rowcount == 0

    # The real row survives, completely unmodified, confirmed from the owner role.
    owner_session.expire_all()
    still_there = owner_session.get(Watchlist, wl_b_id)
    assert still_there is not None
    assert still_there.name == "B list to attack"


def test_tenant_b_sees_its_own_row_in_a_separate_transaction(
    owner_session: Session, app_session_factory: sessionmaker[Session]
) -> None:
    """Confirms tenant_scope's real, per-transaction GUC is not sticky
    across separate transactions on a reused connection -- each real
    `with app_session.begin():` block gets its own, correctly-scoped
    context, never a leftover one from an earlier request."""
    tenant_a, user_a = _make_tenant_with_user(owner_session, "RLS Sep A")
    tenant_b, user_b = _make_tenant_with_user(owner_session, "RLS Sep B")
    owner_session.add(Watchlist(tenant_id=tenant_a.id, user_id=user_a.id, name="A list"))
    owner_session.add(Watchlist(tenant_id=tenant_b.id, user_id=user_b.id, name="B list"))
    owner_session.commit()

    with app_session_factory() as app_session:
        with app_session.begin(), tenant_scope(app_session, tenant_a.id):
            rows_a = (
                app_session.execute(
                    select(Watchlist).where(Watchlist.tenant_id.in_([tenant_a.id, tenant_b.id]))
                )
                .scalars()
                .all()
            )
            assert [r.name for r in rows_a] == ["A list"]

        with app_session.begin(), tenant_scope(app_session, tenant_b.id):
            rows_b = (
                app_session.execute(
                    select(Watchlist).where(Watchlist.tenant_id.in_([tenant_a.id, tenant_b.id]))
                )
                .scalars()
                .all()
            )
            assert [r.name for r in rows_b] == ["B list"]
