"""Phase 5 §9: the remaining required security tests not already
covered by a more specific test file -- security headers on a normal
(non-error) response, rate-limit 429+Retry-After through the real
HTTP login endpoint, session-fixation defense, and the input-
validation/error-model contract.

CSRF rejection, lockout/backoff, and API-key hash-only storage/
revocation/scope enforcement are already real, dedicated tests in
`tests/test_api_auth.py` / `tests/test_api_api_keys.py` /
`tests/test_api_app.py`; not duplicated here.
"""

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
    # Start every test in this file from a real, known-clean rate-limit
    # window -- the login_ip counter is shared, keyed only by IP, across
    # every test in the whole suite that calls /v1/auth/login.
    session.execute(text("DELETE FROM rate_limit_counters WHERE key LIKE 'login_ip:%'"))
    session.commit()
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


@pytest.fixture
def client() -> TestClient:
    try:
        from ledgerlight.api.app import create_app
    except Exception as exc:
        pytest.skip(f"could not build the real FastAPI app: {exc}")
    return TestClient(create_app())


def test_security_headers_present_on_a_normal_response(client: TestClient) -> None:
    """The existing regression test in `tests/test_api_app.py` proves
    these survive an unhandled 500; this proves they are also present
    on the ordinary, successful path -- both halves of the real
    `_security_headers_middleware` contract."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "no-referrer"
    assert (
        response.headers.get("Content-Security-Policy")
        == "default-src 'none'; frame-ancestors 'none'"
    )


def test_login_rate_limit_returns_429_with_retry_after(
    client: TestClient, real_session: Session
) -> None:
    """`rate_limit.check_and_increment` runs as the very first
    statement in `POST /v1/auth/login`, before the tenant lookup --
    so a nonexistent tenant_slug exercises the real limiter without
    ever touching real lockout state for a real user."""
    responses = [
        client.post(
            "/v1/auth/login",
            json={
                "tenant_slug": "no-such-tenant",
                "email": "nobody@example.com",
                "password": "wrong",
            },
        )
        for _ in range(11)
    ]
    statuses = [r.status_code for r in responses]
    assert statuses[:10] == [401] * 10, statuses
    assert statuses[10] == 429, statuses
    assert "Retry-After" in responses[10].headers
    assert int(responses[10].headers["Retry-After"]) > 0


def test_login_never_reuses_an_attacker_supplied_session_cookie(
    client: TestClient, real_session: Session
) -> None:
    """Classic session-fixation probe: an attacker sets a known
    session cookie value in the victim's browser before they log in,
    hoping the server adopts it as their real, now-authenticated
    session. `POST /v1/auth/login` never reads any existing cookie at
    all -- it always calls `auth.create_session`, a brand-new random
    token -- so the attacker's pre-set value is simply overwritten,
    never adopted."""
    tenant = Tenant(name="Fixation Test Co", slug=f"fixation-{uuid.uuid4().hex[:8]}")
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
        Membership(tenant_id=tenant.id, user_id=user.id, role="viewer", status="active")
    )
    real_session.commit()

    attacker_chosen_token = "attacker-controlled-session-value"

    # Sent explicitly as this one request's own Cookie header (not via
    # the shared client-wide jar, which httpx scopes by domain -- a
    # manually-`.set()` cookie with no domain and the real response's
    # own cookie can coexist as two distinct jar entries, which proves
    # nothing about what the server actually did with the one it was
    # sent). This guarantees the attacker's value is genuinely
    # presented to the real login endpoint on this exact request.
    response = client.post(
        "/v1/auth/login",
        json={
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "CorrectHorseBatteryStaple",
        },
        cookies={"ll_session": attacker_chosen_token},
    )
    assert response.status_code == 200, response.text

    real_cookie = response.cookies.get("ll_session")
    assert real_cookie is not None
    assert real_cookie != attacker_chosen_token

    me_response = client.get("/v1/auth/me", cookies={"ll_session": real_cookie})
    assert me_response.status_code == 200
    assert me_response.json()["user_id"] == str(user.id)


def test_malformed_login_body_returns_422_with_no_stack_trace(client: TestClient) -> None:
    response = client.post("/v1/auth/login", json={"tenant_slug": "x"})
    assert response.status_code == 422
    body_text = response.text
    assert "Traceback" not in body_text
    assert 'File "' not in body_text
    assert "detail" in response.json()
