"""Phase 5 §9: cross-tenant IDOR attempts at the API level, for every
resource type the brief names that `tests/test_api_dossiers.py`
(investigations) and `tests/test_api_review.py` (review tasks) don't
already cover -- watchlists, alerts, API keys, webhooks.

Each case: tenant A creates a real resource; tenant B's own,
fully-privileged (`tenant_admin`) identity then tries to read or
mutate it by its real id. Every single attempt must get a clean 404,
never a 403 -- a 403 would itself leak that the id exists and belongs
to someone else, which is exactly the information an IDOR probe is
trying to extract. `tests/test_api_rls.py` already proves this at the
DB/RLS level directly; this file proves the same boundary holds
through the real HTTP API, end to end.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.api import auth
from ledgerlight.api.models import Alert, Membership, Tenant, User
from ledgerlight.config.settings import Settings
from ledgerlight.db.session import make_session_factory
from ledgerlight.knowledge.models import Company

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

    created: dict[str, list[uuid.UUID]] = {"tenants": [], "companies": []}
    session.info["created"] = created
    try:
        yield session
    finally:
        session.execute(text("DELETE FROM rate_limit_counters WHERE key LIKE 'login_ip:%'"))
        if created["tenants"]:
            for table in (
                "webhook_deliveries",
                "webhooks",
                "api_keys",
                "alerts",
                "alert_rules",
                "watchlist_items",
                "watchlists",
                "audit_logs",
                "sessions",
                "memberships",
                "users",
            ):
                session.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = ANY(:ids)"),  # noqa: S608
                    {"ids": created["tenants"]},
                )
            session.execute(
                text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": created["tenants"]}
            )
        if created["companies"]:
            session.execute(
                text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": created["companies"]}
            )
        session.commit()
        session.close()


def _login(client: TestClient, real_session: Session, name: str) -> tuple[Tenant, str]:
    tenant = Tenant(name=name, slug=f"idor-{uuid.uuid4().hex[:8]}")
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
    real_session.add(
        Membership(tenant_id=tenant.id, user_id=user.id, role="tenant_admin", status="active")
    )
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
def two_tenants(
    real_session: Session,
) -> tuple[tuple[TestClient, str, Tenant], tuple[TestClient, str, Tenant]]:
    from ledgerlight.api.app import create_app

    client_a = TestClient(create_app())
    tenant_a, csrf_a = _login(client_a, real_session, "IDOR Tenant A")
    client_b = TestClient(create_app())
    tenant_b, csrf_b = _login(client_b, real_session, "IDOR Tenant B")
    return (client_a, csrf_a, tenant_a), (client_b, csrf_b, tenant_b)


def test_cross_tenant_idor_is_blocked_everywhere(
    two_tenants: tuple[tuple[TestClient, str, Tenant], tuple[TestClient, str, Tenant]],
    real_session: Session,
) -> None:
    (client_a, csrf_a, tenant_a), (client_b, csrf_b, _tenant_b) = two_tenants

    # --- tenant A creates one real resource of each kind ---------------
    watchlist_resp = client_a.post(
        "/v1/watchlists", json={"name": "A's watchlist"}, headers={"X-CSRF-Token": csrf_a}
    )
    assert watchlist_resp.status_code == 201, watchlist_resp.text
    watchlist_id = watchlist_resp.json()["id"]

    rule_resp = client_a.post(
        "/v1/alerts/rules",
        json={"watchlist_id": watchlist_id, "rule_type": "new_event_type", "config": {}},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert rule_resp.status_code == 201, rule_resp.text
    rule_id = rule_resp.json()["id"]

    company = Company(display_name=f"IDOR Target Co {uuid.uuid4().hex[:8]}")
    real_session.add(company)
    real_session.flush()
    real_session.info["created"]["companies"].append(company.id)
    alert = Alert(
        tenant_id=tenant_a.id,
        alert_rule_id=uuid.UUID(rule_id),
        company_id=company.id,
        payload={"event_id": "test"},
    )
    real_session.add(alert)
    real_session.commit()
    alert_id = str(alert.id)

    key_resp = client_a.post(
        "/v1/api-keys", json={"name": "A's key"}, headers={"X-CSRF-Token": csrf_a}
    )
    assert key_resp.status_code == 201, key_resp.text
    key_id = key_resp.json()["id"]

    webhook_resp = client_a.post(
        "/v1/webhooks",
        json={"url": "https://example.com/webhook"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert webhook_resp.status_code == 201, webhook_resp.text
    webhook_id = webhook_resp.json()["id"]

    # --- tenant B tries to read/mutate every one of A's real ids -------
    idor_attempts: list[tuple[str, str]] = [
        ("GET", f"/v1/watchlists/{watchlist_id}/items"),
        ("DELETE", f"/v1/watchlists/{watchlist_id}"),
        ("DELETE", f"/v1/alerts/rules/{rule_id}"),
        ("POST", f"/v1/alerts/{alert_id}/acknowledge"),
        ("DELETE", f"/v1/api-keys/{key_id}"),
        ("DELETE", f"/v1/webhooks/{webhook_id}"),
        ("GET", f"/v1/webhooks/{webhook_id}/deliveries"),
        ("POST", f"/v1/webhooks/{webhook_id}/test"),
    ]
    for method, path in idor_attempts:
        response = client_b.request(method, path, headers={"X-CSRF-Token": csrf_b})
        assert response.status_code == 404, (
            f"IDOR: tenant B got {response.status_code} (not 404) for "
            f"{method} {path} on tenant A's own resource -- {response.text}"
        )

    # --- positive control: tenant A can still see/act on its own rows --
    assert client_a.get(f"/v1/watchlists/{watchlist_id}/items").status_code == 200
    assert client_a.get("/v1/api-keys").status_code == 200
    assert any(row["id"] == key_id for row in client_a.get("/v1/api-keys").json())
