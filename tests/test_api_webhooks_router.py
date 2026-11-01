"""Phase 5 §3: real end-to-end tests for the webhooks router --
register, test delivery (the real outbound HTTP call is mocked via
respx, same as tests/test_api_webhooks.py's own delivery tests;
`https://1.1.1.1/hook` is a real public IP literal, needing no real
DNS resolution, so ledgerlight.api.webhooks.validate_webhook_url's
own real SSRF check still runs for real), list deliveries, delete.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
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
                text("DELETE FROM webhook_deliveries WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM webhooks WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
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


def _login(client: TestClient, real_session: Session, role: str) -> Tenant:
    tenant = Tenant(name="Webhook Router Test Co", slug=f"webhook-router-{uuid.uuid4().hex[:8]}")
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
    return tenant


@pytest.fixture
def client() -> TestClient:
    try:
        from ledgerlight.api.app import create_app
    except Exception as exc:
        pytest.skip(f"could not build the real FastAPI app: {exc}")
    return TestClient(create_app())


def test_register_rejects_a_non_https_url(client: TestClient, real_session: Session) -> None:
    _login(client, real_session, role="tenant_admin")
    response = client.post("/v1/webhooks", json={"url": "http://1.1.1.1/hook"})
    assert response.status_code == 422


def test_register_test_deliver_and_list_deliveries(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session, role="tenant_admin")

    create_response = client.post("/v1/webhooks", json={"url": "https://1.1.1.1/hook"})
    assert create_response.status_code == 201, create_response.text
    body = create_response.json()
    webhook_id = body["id"]
    assert "raw_secret" in body

    list_response = client.get("/v1/webhooks")
    listed = next(row for row in list_response.json() if row["id"] == webhook_id)
    assert "raw_secret" not in listed  # never shown again

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://1.1.1.1/hook").mock(return_value=Response(200))
        test_response = client.post(f"/v1/webhooks/{webhook_id}/test")
    assert test_response.status_code == 200, test_response.text
    assert test_response.json()["status"] == "success"

    deliveries_response = client.get(f"/v1/webhooks/{webhook_id}/deliveries")
    assert deliveries_response.status_code == 200
    assert len(deliveries_response.json()) == 1
    assert deliveries_response.json()[0]["status"] == "success"


def test_delete_webhook(client: TestClient, real_session: Session) -> None:
    _login(client, real_session, role="tenant_admin")
    webhook_id = client.post("/v1/webhooks", json={"url": "https://1.1.1.1/hook"}).json()["id"]
    response = client.delete(f"/v1/webhooks/{webhook_id}")
    assert response.status_code == 204

    get_deliveries = client.get(f"/v1/webhooks/{webhook_id}/deliveries")
    assert get_deliveries.status_code == 404


def test_analyst_cannot_manage_webhooks(client: TestClient, real_session: Session) -> None:
    _login(client, real_session, role="analyst")
    response = client.post("/v1/webhooks", json={"url": "https://1.1.1.1/hook"})
    assert response.status_code == 403
