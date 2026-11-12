"""Phase 5 §3: real end-to-end tests for the admin router -- user
create/list/role-change/revoke, audit log viewing, all gated behind
tenant_admin-only permissions."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.api import auth
from ledgerlight.api.models import Membership, Tenant, User
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
        session.execute(text("DELETE FROM rate_limit_counters WHERE key LIKE 'login_ip:%'"))
        if created["tenants"]:
            session.execute(
                text("DELETE FROM audit_logs WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM sessions WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM memberships WHERE tenant_id = ANY(:ids)"),
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


def _login(client: TestClient, real_session: Session, role: str) -> tuple[Tenant, str]:
    tenant = Tenant(name="Admin Router Test Co", slug=f"admin-router-{uuid.uuid4().hex[:8]}")
    real_session.add(tenant)
    real_session.flush()
    real_session.info["created"]["tenants"].append(tenant.id)
    user = User(
        tenant_id=tenant.id,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash=auth.hash_password("CorrectHorseBatteryStaple"),
    )
    real_session.add(user)
    real_session.flush()
    real_session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role, status="active"))
    real_session.commit()

    response = client.post(
        "/v1/auth/login",
        json={
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "CorrectHorseBatteryStaple",
        },
    )
    if response.status_code == 503:
        pytest.skip("ledgerlight_app role not reachable")
    assert response.status_code == 200, response.text
    return tenant, response.json()["csrf_token"]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # conftest.py's autouse _isolate_env fixture chdir's to a tmp_path
    # for every test, so create_app()'s own load_settings() would
    # otherwise resolve ".env" relative to that empty tmp_path and
    # silently fall back to Settings' hardcoded field defaults instead
    # of this machine's real local config. Restore cwd to the repo
    # root for this one call.
    from pathlib import Path as _Path

    monkeypatch.chdir(_Path(__file__).resolve().parent.parent)
    try:
        from ledgerlight.api.app import create_app
    except Exception as exc:
        pytest.skip(f"could not build the real FastAPI app: {exc}")
    return TestClient(create_app())


def test_analyst_cannot_manage_users(client: TestClient, real_session: Session) -> None:
    _tenant, csrf_token = _login(client, real_session, role="analyst")
    response = client.post(
        "/v1/admin/users",
        json={"email": "new@example.com", "password": "SomeRealPassword1", "role": "viewer"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 403


def test_tenant_admin_creates_lists_changes_role_and_revokes_a_user(
    client: TestClient, real_session: Session
) -> None:
    _tenant, csrf_token = _login(client, real_session, role="tenant_admin")
    headers = {"X-CSRF-Token": csrf_token}

    create_response = client.post(
        "/v1/admin/users",
        json={
            "email": f"{uuid.uuid4().hex[:8]}@example.com",
            "password": "SomeRealPassword1",
            "role": "viewer",
        },
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    user_id = create_response.json()["user_id"]

    list_response = client.get("/v1/admin/users")
    assert any(row["user_id"] == user_id for row in list_response.json())

    role_response = client.patch(
        f"/v1/admin/users/{user_id}/role", json={"role": "analyst"}, headers=headers
    )
    assert role_response.status_code == 200
    assert role_response.json()["role"] == "analyst"

    revoke_response = client.delete(f"/v1/admin/users/{user_id}", headers=headers)
    assert revoke_response.status_code == 204

    list_after = client.get("/v1/admin/users")
    revoked_row = next(row for row in list_after.json() if row["user_id"] == user_id)
    assert revoked_row["membership_status"] == "revoked"


def test_create_user_rejects_a_duplicate_email(client: TestClient, real_session: Session) -> None:
    _tenant, csrf_token = _login(client, real_session, role="tenant_admin")
    headers = {"X-CSRF-Token": csrf_token}
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    first = client.post(
        "/v1/admin/users",
        json={"email": email, "password": "SomeRealPassword1", "role": "viewer"},
        headers=headers,
    )
    assert first.status_code == 201
    second = client.post(
        "/v1/admin/users",
        json={"email": email, "password": "AnotherPassword1", "role": "viewer"},
        headers=headers,
    )
    assert second.status_code == 409


def test_create_user_rejects_an_invalid_role(client: TestClient, real_session: Session) -> None:
    _tenant, csrf_token = _login(client, real_session, role="tenant_admin")
    response = client.post(
        "/v1/admin/users",
        json={
            "email": f"{uuid.uuid4().hex[:8]}@example.com",
            "password": "SomeRealPassword1",
            "role": "superuser",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 422


def test_audit_log_shows_real_actions_and_is_tenant_scoped(
    client: TestClient, real_session: Session
) -> None:
    _tenant, csrf_token = _login(client, real_session, role="tenant_admin")
    client.post(
        "/v1/admin/users",
        json={
            "email": f"{uuid.uuid4().hex[:8]}@example.com",
            "password": "SomeRealPassword1",
            "role": "viewer",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    audit_response = client.get("/v1/admin/audit-log")
    assert audit_response.status_code == 200
    assert any(row["action"] == "user_created" for row in audit_response.json())

    # A different tenant's admin sees none of the first tenant's audit rows.
    _login(client, real_session, role="tenant_admin")
    other_audit_response = client.get("/v1/admin/audit-log")
    other_actions = [row for row in other_audit_response.json() if row["action"] == "user_created"]
    assert other_actions == []


def test_create_user_without_csrf_header_is_rejected(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session, role="tenant_admin")
    response = client.post(
        "/v1/admin/users",
        json={
            "email": "should-fail@example.com",
            "password": "SomeRealPassword1",
            "role": "viewer",
        },
    )
    assert response.status_code == 403
