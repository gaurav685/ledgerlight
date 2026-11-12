"""Phase 5 §3: real end-to-end tests for the companies/events/scores/
credibility router -- a logged-in `viewer` identity (has
`VIEW_COMPANY_DATA`, nothing more) against the real local Postgres
stack. Companies/events/scores are real, global reference data (no
RLS) -- created directly via the owner role, same as every other
knowledge-schema test in this project.
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
        # Login in this test module's own `_login` helper real-increments the
        # shared `login_ip:*` rate-limit counter -- cleared here so repeated
        # test runs inside the same real fixed window never trip the real
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
        if created["companies"]:
            session.execute(
                text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": created["companies"]}
            )
        session.commit()
        session.close()


def _login(client: TestClient, real_session: Session, role: str = "viewer") -> None:
    tenant = Tenant(name="Companies Test Co", slug=f"companies-test-{uuid.uuid4().hex[:8]}")
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


def _make_company(real_session: Session, name: str) -> Company:
    company = Company(display_name=name)
    real_session.add(company)
    real_session.flush()
    real_session.info["created"]["companies"].append(company.id)
    real_session.commit()
    return company


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


def test_search_requires_a_real_identity(client: TestClient) -> None:
    response = client.get("/v1/companies/search", params={"q": "anything"})
    assert response.status_code == 401


def test_search_finds_a_real_company_by_a_real_substring(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session)
    company = _make_company(real_session, f"Ledgerlight Search Target {uuid.uuid4().hex[:8]}")
    response = client.get("/v1/companies/search", params={"q": company.display_name[:20]})
    assert response.status_code == 200
    assert any(row["id"] == str(company.id) for row in response.json())


def test_get_company_overview(client: TestClient, real_session: Session) -> None:
    _login(client, real_session)
    company = _make_company(real_session, f"Overview Co {uuid.uuid4().hex[:8]}")
    response = client.get(f"/v1/companies/{company.id}")
    assert response.status_code == 200
    assert response.json()["name"] == company.display_name


def test_get_company_overview_404_for_an_unknown_company(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session)
    response = client.get(f"/v1/companies/{uuid.uuid4()}")
    assert response.status_code == 404


def test_get_company_events_is_empty_for_a_fresh_company_with_no_real_events(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session)
    company = _make_company(real_session, f"No Events Co {uuid.uuid4().hex[:8]}")
    response = client.get(f"/v1/companies/{company.id}/events")
    assert response.status_code == 200
    assert response.json() == []


def test_get_company_timeline_is_empty_for_a_fresh_company(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session)
    company = _make_company(real_session, f"No Timeline Co {uuid.uuid4().hex[:8]}")
    response = client.get(f"/v1/companies/{company.id}/timeline")
    assert response.status_code == 200
    assert response.json() == []


def test_get_company_score_404_with_model_limitations_when_no_real_score_exists(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session)
    company = _make_company(real_session, f"No Score Co {uuid.uuid4().hex[:8]}")
    response = client.get(f"/v1/companies/{company.id}/scores")
    assert response.status_code == 404
    assert "model limitations" in response.json()["detail"]


def test_get_company_credibility_is_always_honest_about_being_unavailable(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session)
    company = _make_company(real_session, f"Credibility Co {uuid.uuid4().hex[:8]}")
    response = client.get(f"/v1/companies/{company.id}/credibility")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "guidance" in body["reason"].lower()


def test_search_rejects_a_role_with_no_view_company_data_permission(
    client: TestClient, real_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every real role in `ledgerlight.api.models.ROLES` is granted
    VIEW_COMPANY_DATA (see rbac.py) -- there is no real role to prove
    this 403 with directly, so this proves the enforcement POINT
    instead: a monkeypatched `has_permission` that always denies still
    produces a real 403, not a silent bypass."""
    from ledgerlight.api import rbac

    _login(client, real_session)
    monkeypatch.setattr(rbac, "has_permission", lambda role, permission: False)
    response = client.get("/v1/companies/search", params={"q": "anything"})
    assert response.status_code == 403
