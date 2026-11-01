"""Phase 5 §3: real end-to-end tests for the review router. A real
`ReviewTask` is created directly (via the owner role) on top of a
real, minimal `Investigation`/`Dossier` pair owned by one real tenant
-- exercising `ledgerlight.agent.review.create_review_tasks`'s own
routing logic again is Phase 4's own test surface; this module proves
the real HTTP/RBAC/tenant-isolation layer on top of it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.agent.models import Dossier, Investigation, ReviewTask
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


def _login(client: TestClient, real_session: Session, role: str) -> Tenant:
    tenant = Tenant(name="Review Test Co", slug=f"review-test-{uuid.uuid4().hex[:8]}")
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


def _make_review_task(real_session: Session, tenant_id: uuid.UUID) -> ReviewTask:
    company = Company(display_name=f"Review Target Co {uuid.uuid4().hex[:8]}")
    real_session.add(company)
    real_session.flush()
    real_session.info["created"]["companies"].append(company.id)

    investigation = Investigation(
        company_id=company.id,
        as_of="2026-01-01",
        requested_by="test-fixture",
        tenant_id=tenant_id,
        state="FINALISE",
        final_status="NEEDS_REVIEW",
        budget_config={},
        usage={},
    )
    real_session.add(investigation)
    real_session.flush()

    dossier = Dossier(
        investigation_id=investigation.id,
        version=1,
        status="NEEDS_REVIEW",
        sections={},
        claim_id_map={},
        renderer_name="offline_template",
        renderer_version="1.0",
    )
    real_session.add(dossier)
    real_session.flush()

    task = ReviewTask(
        dossier_id=dossier.id, reason_code="verification_failed", priority=10, status="open"
    )
    real_session.add(task)
    real_session.commit()
    return task


@pytest.fixture
def client() -> TestClient:
    try:
        from ledgerlight.api.app import create_app
    except Exception as exc:
        pytest.skip(f"could not build the real FastAPI app: {exc}")
    return TestClient(create_app())


def test_list_review_tasks_shows_a_real_open_task_for_the_owning_tenant(
    client: TestClient, real_session: Session
) -> None:
    tenant = _login(client, real_session, role="reviewer")
    task = _make_review_task(real_session, tenant.id)

    response = client.get("/v1/review/tasks")
    assert response.status_code == 200
    assert any(row["id"] == str(task.id) for row in response.json())


def test_list_review_tasks_hides_another_tenants_task(
    client: TestClient, real_session: Session
) -> None:
    owner_tenant = Tenant(name="Owner", slug=f"owner-{uuid.uuid4().hex[:8]}")
    real_session.add(owner_tenant)
    real_session.flush()
    real_session.info["created"]["tenants"].append(owner_tenant.id)
    real_session.commit()
    task = _make_review_task(real_session, owner_tenant.id)

    _login(client, real_session, role="reviewer")  # a different, second tenant
    response = client.get("/v1/review/tasks")
    assert response.status_code == 200
    assert all(row["id"] != str(task.id) for row in response.json())

    get_response = client.get(f"/v1/review/tasks/{task.id}")
    assert get_response.status_code == 404


def test_viewer_role_cannot_decide_a_review_task(client: TestClient, real_session: Session) -> None:
    tenant = _login(client, real_session, role="viewer")  # viewer lacks DECIDE_REVIEW
    task = _make_review_task(real_session, tenant.id)
    response = client.post(
        f"/v1/review/tasks/{task.id}/decision", json={"decision": "approve", "notes": None}
    )
    assert response.status_code == 403


def test_reviewer_can_decide_a_real_task_and_it_is_audited(
    client: TestClient, real_session: Session
) -> None:
    tenant = _login(client, real_session, role="reviewer")
    task = _make_review_task(real_session, tenant.id)

    response = client.post(
        f"/v1/review/tasks/{task.id}/decision",
        json={"decision": "approve_with_edits", "notes": "looks fine after a minor edit"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "closed"
    assert body["decision"] == "approve_with_edits"

    audit_count = real_session.execute(
        text(
            "SELECT count(*) FROM audit_logs WHERE tenant_id = :tenant_id "
            "AND action = 'review_decision' AND target_id = :task_id"
        ),
        {"tenant_id": tenant.id, "task_id": str(task.id)},
    ).scalar()
    assert audit_count == 1


def test_decide_rejects_an_invalid_decision_value(
    client: TestClient, real_session: Session
) -> None:
    tenant = _login(client, real_session, role="reviewer")
    task = _make_review_task(real_session, tenant.id)
    response = client.post(
        f"/v1/review/tasks/{task.id}/decision", json={"decision": "not_a_real_decision"}
    )
    assert response.status_code == 422
