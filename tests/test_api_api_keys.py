"""Tests for ledgerlight.api.api_keys -- Phase 5 §2. Real commits
(create_api_key/revoke_api_key flush internally), so this uses the
same real, independent-session-with-manual-cleanup pattern as
test_agent_state_machine.py.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from ledgerlight.api import api_keys
from ledgerlight.api.models import Tenant, User
from ledgerlight.config.settings import Settings
from ledgerlight.db.session import make_session_factory

pytestmark = pytest.mark.integration


@pytest.fixture
def real_session() -> Iterator[Session]:
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

    created: dict[str, list[uuid.UUID]] = {"tenants": []}
    session.info["created"] = created
    try:
        yield session
    finally:
        from sqlalchemy import text

        if created["tenants"]:
            session.execute(
                text("DELETE FROM api_keys WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM users WHERE tenant_id = ANY(:ids)"), {"ids": created["tenants"]}
            )
            session.execute(
                text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": created["tenants"]}
            )
            session.commit()
        session.close()


def _make_tenant_and_user(session: Session) -> tuple[Tenant, User]:
    tenant = Tenant(name="API Key Test Co", slug=f"apikey-test-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    session.flush()
    session.info["created"]["tenants"].append(tenant.id)
    user = User(tenant_id=tenant.id, email=f"{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    session.flush()
    return tenant, user


def test_create_and_verify_a_real_api_key(real_session: Session) -> None:
    tenant, user = _make_tenant_and_user(real_session)
    row, raw_key = api_keys.create_api_key(real_session, tenant.id, user.id, "My Key", ["read"])
    real_session.commit()

    verified = api_keys.verify_api_key(real_session, raw_key)
    assert verified is not None
    assert verified.id == row.id
    assert verified.last_used_at is not None


def test_verify_api_key_rejects_an_unknown_key(real_session: Session) -> None:
    assert api_keys.verify_api_key(real_session, "llk_deadbeef.not-a-real-secret") is None


def test_verify_api_key_rejects_a_malformed_key(real_session: Session) -> None:
    assert api_keys.verify_api_key(real_session, "not-even-the-right-format") is None


def test_verify_api_key_rejects_a_revoked_key(real_session: Session) -> None:
    tenant, user = _make_tenant_and_user(real_session)
    row, raw_key = api_keys.create_api_key(real_session, tenant.id, user.id, "My Key", ["read"])
    real_session.commit()

    api_keys.revoke_api_key(real_session, row)
    real_session.commit()
    assert api_keys.verify_api_key(real_session, raw_key) is None


def test_verify_api_key_rejects_an_expired_key(real_session: Session) -> None:
    import datetime as dt

    tenant, user = _make_tenant_and_user(real_session)
    _row, raw_key = api_keys.create_api_key(
        real_session,
        tenant.id,
        user.id,
        "My Key",
        ["read"],
        expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1),
    )
    real_session.commit()
    assert api_keys.verify_api_key(real_session, raw_key) is None


def test_has_scope(real_session: Session) -> None:
    tenant, user = _make_tenant_and_user(real_session)
    row, _raw_key = api_keys.create_api_key(
        real_session, tenant.id, user.id, "My Key", ["read:dossiers"]
    )
    real_session.commit()

    assert api_keys.has_scope(row, "read:dossiers")
    assert not api_keys.has_scope(row, "write:dossiers")
