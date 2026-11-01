"""Phase 5 §3: real end-to-end tests for the dossiers router -- a
logged-in `analyst` identity (has CREATE_INVESTIGATION/VIEW_DOSSIER/
EXPORT_DOSSIER) creates a real investigation against a real, fresh
company with no data, through the real async job path (the
background task runs synchronously to completion inside Starlette's
TestClient, so no polling is needed here), then fetches and exports
the real resulting dossier. Also proves the real tenant-isolation
story this router's own docstring describes: another tenant's
identity gets a real 404 for the exact same investigation id, never
a 403 that would confirm it exists."""

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
        session.execute(text("DELETE FROM rate_limit_counters WHERE key LIKE 'login_ip:%'"))
        if created["companies"]:
            session.execute(
                text(
                    "DELETE FROM review_decisions_audit WHERE review_task_id IN "
                    "(SELECT id FROM review_tasks WHERE dossier_id IN "
                    "(SELECT id FROM dossiers WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text(
                    "DELETE FROM review_tasks WHERE dossier_id IN "
                    "(SELECT id FROM dossiers WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids)))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text(
                    "DELETE FROM dossiers WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text(
                    "DELETE FROM claims WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text(
                    "DELETE FROM investigation_steps WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text("DELETE FROM investigations WHERE company_id = ANY(:ids)"),
                {"ids": created["companies"]},
            )
            session.execute(
                text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": created["companies"]}
            )
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


def _login(client: TestClient, real_session: Session, role: str = "analyst") -> tuple[Tenant, str]:
    tenant = Tenant(name="Dossiers Test Co", slug=f"dossiers-test-{uuid.uuid4().hex[:8]}")
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


def _make_company(real_session: Session, name: str) -> Company:
    company = Company(display_name=name)
    real_session.add(company)
    real_session.flush()
    real_session.info["created"]["companies"].append(company.id)
    real_session.commit()
    return company


@pytest.fixture
def client() -> TestClient:
    try:
        from ledgerlight.api.app import create_app
    except Exception as exc:
        pytest.skip(f"could not build the real FastAPI app: {exc}")
    return TestClient(create_app())


def test_create_investigation_runs_to_a_real_finalised_dossier(
    client: TestClient, real_session: Session
) -> None:
    _tenant, csrf_token = _login(client, real_session)
    company = _make_company(real_session, f"Dossier Target Co {uuid.uuid4().hex[:8]}")

    create_response = client.post(
        "/v1/dossiers/investigations",
        json={"company_id": str(company.id), "as_of": "2026-01-01"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert create_response.status_code == 202, create_response.text
    investigation_id = create_response.json()["id"]

    status_response = client.get(f"/v1/dossiers/investigations/{investigation_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["state"] == "FINALISE"
    assert body["final_status"] == "FINALISED"

    list_response = client.get("/v1/dossiers/investigations")
    assert list_response.status_code == 200
    assert any(row["id"] == investigation_id for row in list_response.json())

    dossier_response = client.get(f"/v1/dossiers/investigations/{investigation_id}/dossier")
    assert dossier_response.status_code == 200
    dossier_body = dossier_response.json()
    assert dossier_body["status"] == "FINALISED"
    assert "summary" in dossier_body["sections"]

    export_md = client.get(
        f"/v1/dossiers/investigations/{investigation_id}/export", params={"fmt": "markdown"}
    )
    assert export_md.status_code == 200
    assert "# Investigation Dossier" in export_md.json()["content"]

    export_json = client.get(
        f"/v1/dossiers/investigations/{investigation_id}/export", params={"fmt": "json"}
    )
    assert export_json.status_code == 200
    assert export_json.json()["format"] == "json"


def test_create_investigation_requires_create_investigation_permission(
    client: TestClient, real_session: Session
) -> None:
    _tenant, csrf_token = _login(client, real_session, role="viewer")  # lacks CREATE_INVESTIGATION
    company = _make_company(real_session, f"No Permission Co {uuid.uuid4().hex[:8]}")
    response = client.post(
        "/v1/dossiers/investigations",
        json={"company_id": str(company.id), "as_of": "2026-01-01"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 403


def test_another_tenant_gets_a_real_404_never_a_403(
    client: TestClient, real_session: Session
) -> None:
    """The real tenant-isolation proof: investigations is RLS-protected,
    so a second tenant's own app-role-scoped connection genuinely
    cannot see the first tenant's row -- this must read as "not
    found", identical to a truly unknown id, never a 403 (which would
    itself leak that the id exists)."""
    _tenant, csrf_token = _login(client, real_session, role="analyst")
    company = _make_company(real_session, f"Isolation Target Co {uuid.uuid4().hex[:8]}")
    create_response = client.post(
        "/v1/dossiers/investigations",
        json={"company_id": str(company.id), "as_of": "2026-01-01"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert create_response.status_code == 202
    investigation_id = create_response.json()["id"]

    # A second, unrelated tenant logging in replaces the shared TestClient's
    # own session cookie -- the first tenant's session is still valid
    # server-side, but this client is now acting as the second tenant.
    _login(client, real_session, role="analyst")
    response = client.get(f"/v1/dossiers/investigations/{investigation_id}")
    assert response.status_code == 404

    list_response = client.get("/v1/dossiers/investigations")
    assert all(row["id"] != investigation_id for row in list_response.json())


def test_create_investigation_without_csrf_header_is_rejected(
    client: TestClient, real_session: Session
) -> None:
    _tenant, _csrf_token = _login(client, real_session)
    company = _make_company(real_session, f"No CSRF Co {uuid.uuid4().hex[:8]}")
    response = client.post(
        "/v1/dossiers/investigations",
        json={"company_id": str(company.id), "as_of": "2026-01-01"},
    )
    assert response.status_code == 403
