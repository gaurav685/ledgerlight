"""Phase 5 §3: the first real end-to-end HTTP test -- exercises
`ledgerlight.api.app`'s real FastAPI app, `deps.py`'s real identity
resolution, and the `auth` router's real login/logout/me, all against
the real local Postgres stack. Real rows are created via the owner
role (`real_session`, same pattern as test_api_auth.py); the app
itself always talks to Postgres as the restricted `ledgerlight_app`
role, exactly as it does in a real deployment.
"""

from __future__ import annotations

import json
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
        # Real logins made by this module's tests increment the shared
        # `login_ip:*` rate-limit counter -- cleared here so repeated test
        # runs inside the same real fixed window never trip the real
        # per-IP login limit meant for a genuine credential-stuffing attempt.
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


def _make_tenant_user_membership(
    session: Session, *, password: str = "CorrectHorseBatteryStaple", role: str = "analyst"
) -> tuple[Tenant, User]:
    tenant = Tenant(name="App Test Co", slug=f"app-test-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    session.flush()
    session.info["created"]["tenants"].append(tenant.id)
    user = User(
        tenant_id=tenant.id,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash=auth.hash_password(password),
    )
    session.add(user)
    session.flush()
    session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role, status="active"))
    session.commit()
    return tenant, user


@pytest.fixture
def client() -> TestClient:
    try:
        from ledgerlight.api.app import create_app
    except Exception as exc:
        pytest.skip(f"could not build the real FastAPI app: {exc}")
    return TestClient(create_app())


def test_healthz_is_always_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reaches_the_real_database(client: TestClient) -> None:
    response = client.get("/readyz")
    if response.status_code != 200:
        pytest.skip(f"ledgerlight_app role not reachable: {response.json()}")
    assert response.json() == {"status": "ready"}


def test_every_response_carries_a_real_request_id(client: TestClient) -> None:
    response = client.get("/healthz")
    assert "X-Request-ID" in response.headers


def test_login_with_the_real_correct_password_succeeds(
    client: TestClient, real_session: Session
) -> None:
    tenant, user = _make_tenant_user_membership(real_session, password="CorrectHorseBatteryStaple")
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
    body = response.json()
    assert body["identity"]["tenant_id"] == str(tenant.id)
    assert body["identity"]["role"] == "analyst"
    assert "csrf_token" in body


def test_login_with_a_wrong_password_is_rejected(client: TestClient, real_session: Session) -> None:
    tenant, user = _make_tenant_user_membership(real_session, password="CorrectHorseBatteryStaple")
    response = client.post(
        "/v1/auth/login",
        json={"tenant_slug": tenant.slug, "email": user.email, "password": "WrongPassword"},
    )
    if response.status_code == 503:
        pytest.skip("ledgerlight_app role not reachable")
    assert response.status_code == 401


def test_me_requires_a_real_session_and_reflects_it(
    client: TestClient, real_session: Session
) -> None:
    tenant, user = _make_tenant_user_membership(real_session)

    anon = client.get("/v1/auth/me")
    assert anon.status_code == 401

    login_response = client.post(
        "/v1/auth/login",
        json={
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "CorrectHorseBatteryStaple",
        },
    )
    if login_response.status_code == 503:
        pytest.skip("ledgerlight_app role not reachable")
    assert login_response.status_code == 200

    me_response = client.get("/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user_id"] == str(user.id)


def test_logout_without_csrf_header_is_rejected(client: TestClient, real_session: Session) -> None:
    tenant, user = _make_tenant_user_membership(real_session)
    login_response = client.post(
        "/v1/auth/login",
        json={
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "CorrectHorseBatteryStaple",
        },
    )
    if login_response.status_code == 503:
        pytest.skip("ledgerlight_app role not reachable")
    response = client.post("/v1/auth/logout")
    assert response.status_code == 403


def test_metrics_endpoint_exposes_real_prometheus_counters(client: TestClient) -> None:
    client.get("/healthz")
    client.get("/healthz")
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert (
        'ledgerlight_http_requests_total{method="GET",route="/healthz",status_code="200"}' in body
    )
    assert "ledgerlight_http_request_duration_seconds" in body


def test_metrics_route_label_uses_the_route_template_not_the_raw_path(
    client: TestClient, real_session: Session
) -> None:
    """A real company_id/investigation_id in the raw path must never
    leak into a metric label -- unbounded cardinality, and the
    brief's own cardinality requirement."""
    tenant, user = _make_tenant_user_membership(real_session)
    login_response = client.post(
        "/v1/auth/login",
        json={
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "CorrectHorseBatteryStaple",
        },
    )
    if login_response.status_code == 503:
        pytest.skip("ledgerlight_app role not reachable")
    fake_id = uuid.uuid4()
    client.get(f"/v1/dossiers/investigations/{fake_id}")
    response = client.get("/metrics")
    assert str(fake_id) not in response.text
    assert "/v1/dossiers/investigations/{investigation_id}" in response.text


def test_a_real_request_logs_json_with_the_bound_request_id(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Phase 5 §8: `configure_logging` must actually merge contextvars
    (request_id/tenant_id) into every real emitted log line -- this
    regression-tests a real bug where `merge_contextvars` was missing
    from the processor chain and bound values were silently dropped,
    so a real request_id/tenant_id never reached any log line at all.

    Exercised via the app's own real unhandled-exception handler (the
    only code path that logs during a real request) by mounting one
    deliberately-raising test-only route onto a real app instance --
    the real middleware stack and real exception handler are otherwise
    untouched."""
    from fastapi import APIRouter

    from ledgerlight.api.app import create_app

    app = create_app()
    boom_router = APIRouter()

    @boom_router.get("/__ledgerlight_test_boom__")
    def _boom() -> None:
        raise RuntimeError("deliberate test boom")

    app.include_router(boom_router)
    client = TestClient(app, raise_server_exceptions=False)

    capfd.readouterr()  # drain anything buffered before this test's own request
    response = client.get("/__ledgerlight_test_boom__")
    assert response.status_code == 500

    out, _ = capfd.readouterr()
    json_lines = [line for line in out.splitlines() if line.strip().startswith("{")]
    assert json_lines, f"expected at least one real JSON log line, got: {out!r}"
    request_id = response.headers.get("X-Request-ID")
    assert any(json.loads(line).get("request_id") == request_id for line in json_lines)


def test_an_unhandled_exception_still_carries_request_id_and_security_headers() -> None:
    """Regression test for a real bug: a handler registered for the
    bare `Exception` class is wired by Starlette into the OUTERMOST
    `ServerErrorMiddleware`, above every `@app.middleware("http")` --
    confirmed directly that on a real unhandled exception, the error
    propagates past `_request_id_middleware`/`_security_headers_middleware`
    before being caught, so their post-`call_next` header mutations
    never applied. `X-Request-ID` and all 4 security headers were
    silently missing from every real 500 response."""
    from fastapi import APIRouter

    from ledgerlight.api.app import create_app

    app = create_app()
    boom_router = APIRouter()

    @boom_router.get("/__ledgerlight_test_boom_headers__")
    def _boom() -> None:
        raise RuntimeError("deliberate test boom")

    app.include_router(boom_router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/__ledgerlight_test_boom_headers__")
    assert response.status_code == 500
    assert response.headers.get("X-Request-ID")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "no-referrer"
    assert (
        response.headers.get("Content-Security-Policy")
        == "default-src 'none'; frame-ancestors 'none'"
    )


def test_logout_with_the_real_csrf_header_revokes_the_session(
    client: TestClient, real_session: Session
) -> None:
    tenant, user = _make_tenant_user_membership(real_session)
    login_response = client.post(
        "/v1/auth/login",
        json={
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "CorrectHorseBatteryStaple",
        },
    )
    if login_response.status_code == 503:
        pytest.skip("ledgerlight_app role not reachable")
    csrf_token = login_response.json()["csrf_token"]

    logout_response = client.post("/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout_response.status_code == 200

    me_response = client.get("/v1/auth/me")
    assert me_response.status_code == 401
