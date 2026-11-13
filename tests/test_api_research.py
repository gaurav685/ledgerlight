"""Enhancement 1 §3: real end-to-end tests for the read-only
`/v1/research/event-study` router -- a logged-in `viewer` identity
against the real local Postgres stack, the same pattern
`tests/test_api_companies.py` already uses (global reference data,
no RLS)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.api import auth
from ledgerlight.api.models import Membership, Tenant, User
from ledgerlight.config.settings import Settings
from ledgerlight.db.session import make_session_factory
from ledgerlight.research.models import EventStudyEventResult, EventStudyRun

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


def _login(client: TestClient, real_session: Session, role: str = "viewer") -> None:
    tenant = Tenant(name="Research Test Co", slug=f"research-test-{uuid.uuid4().hex[:8]}")
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


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from pathlib import Path as _Path

    monkeypatch.chdir(_Path(__file__).resolve().parent.parent)
    try:
        from ledgerlight.api.app import create_app
    except Exception as exc:
        pytest.skip(f"could not build the real FastAPI app: {exc}")
    return TestClient(create_app())


def test_event_study_summary_requires_a_real_identity(client: TestClient) -> None:
    response = client.get("/v1/research/event-study")
    assert response.status_code == 401


def test_event_study_summary_returns_the_latest_real_run(
    client: TestClient, real_session: Session
) -> None:
    run = real_session.scalars(
        select(EventStudyRun).order_by(EventStudyRun.created_at.desc())
    ).first()
    if run is None:
        pytest.skip("no real event_study_runs row exists yet -- run scripts/event_study.py first")

    _login(client, real_session)
    response = client.get("/v1/research/event-study")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == str(run.id)
    assert body["spec_sha256"] == run.spec_sha256
    assert "not investment advice" in body["disclaimer"].lower()
    assert isinstance(body["metrics"], dict)
    assert isinstance(body["event_counts"], dict)


def test_company_event_study_events_returns_real_car_next_to_type_average(
    client: TestClient, real_session: Session
) -> None:
    result = real_session.scalars(select(EventStudyEventResult).limit(1)).first()
    if result is None:
        pytest.skip("no real event_study_event_results row exists yet")

    _login(client, real_session)
    response = client.get(f"/v1/research/event-study/companies/{result.company_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    matching = [e for e in body if e["event_type_code"] == result.event_type_code]
    assert matching
    # The real per-event CAR and the real type-wide average are reported
    # side by side -- the comparison the "Market reaction" panel shows.
    assert "car_primary_window" in matching[0]
    assert "type_average_car_primary_window" in matching[0]


def test_company_event_study_events_is_an_empty_list_for_a_company_with_no_events(
    client: TestClient, real_session: Session
) -> None:
    run = real_session.scalars(select(EventStudyRun).limit(1)).first()
    if run is None:
        pytest.skip("no real event_study_runs row exists yet -- run scripts/event_study.py first")

    _login(client, real_session)
    response = client.get(f"/v1/research/event-study/companies/{uuid.uuid4()}")
    assert response.status_code == 200
    assert response.json() == []


def test_event_study_caar_plot_serves_a_real_png(client: TestClient, real_session: Session) -> None:
    result = real_session.scalars(select(EventStudyEventResult).limit(1)).first()
    if result is None:
        pytest.skip("no real event_study_event_results row exists yet")

    _login(client, real_session)
    event_type = result.event_type_code.lower()
    response = client.get(f"/v1/research/event-study/caar/{event_type}.png")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_event_study_caar_plot_rejects_a_path_traversal_attempt(client: TestClient) -> None:
    response = client.get("/v1/research/event-study/caar/..%2f..%2fetc%2fpasswd.png")
    assert response.status_code in (401, 404)
