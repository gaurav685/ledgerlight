"""Phase 5 §3: real end-to-end tests for the api-keys router --
create (shown once), list (never the raw key again), revoke."""

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
                text("DELETE FROM api_keys WHERE tenant_id = ANY(:ids)"),
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
    tenant = Tenant(name="API Key Router Test Co", slug=f"apikey-router-{uuid.uuid4().hex[:8]}")
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
def client() -> TestClient:
    try:
        from ledgerlight.api.app import create_app
    except Exception as exc:
        pytest.skip(f"could not build the real FastAPI app: {exc}")
    return TestClient(create_app())


def test_analyst_cannot_manage_api_keys(client: TestClient, real_session: Session) -> None:
    _tenant, csrf_token = _login(client, real_session, role="analyst")  # lacks MANAGE_API_KEYS
    response = client.post(
        "/v1/api-keys",
        json={"name": "My Key", "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 403


def test_tenant_admin_can_create_list_and_revoke_a_real_key(
    client: TestClient, real_session: Session
) -> None:
    _tenant, csrf_token = _login(client, real_session, role="tenant_admin")
    headers = {"X-CSRF-Token": csrf_token}

    create_response = client.post(
        "/v1/api-keys", json={"name": "CI Key", "scopes": ["read"]}, headers=headers
    )
    assert create_response.status_code == 201, create_response.text
    body = create_response.json()
    key_id = body["id"]
    raw_key = body["raw_key"]
    assert raw_key.startswith("llk_")

    list_response = client.get("/v1/api-keys")
    assert list_response.status_code == 200
    listed = next(row for row in list_response.json() if row["id"] == key_id)
    assert "raw_key" not in listed  # never shown again

    # The real raw key works as a real Bearer credential against a
    # real protected endpoint -- proves api_keys.verify_api_key's own
    # RLS-bootstrapping routing-prefix fix end to end over real HTTP.
    bearer_response = client.get(
        "/v1/companies/search", params={"q": "x"}, headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert bearer_response.status_code == 200

    revoke_response = client.delete(f"/v1/api-keys/{key_id}", headers=headers)
    assert revoke_response.status_code == 204

    revoked_bearer_response = client.get(
        "/v1/companies/search", params={"q": "x"}, headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert revoked_bearer_response.status_code == 401


def test_create_api_key_without_csrf_header_is_rejected(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session, role="tenant_admin")
    response = client.post("/v1/api-keys", json={"name": "Should Fail", "scopes": []})
    assert response.status_code == 403
