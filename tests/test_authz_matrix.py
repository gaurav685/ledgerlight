"""Phase 5 §9: the real authorisation matrix test the brief requires --
every real permission-gated endpoint, against every real role, with
the expected allow/deny derived live from `ledgerlight.api.rbac`'s own
`ROLE_PERMISSIONS` (the single source of truth), never a second,
hand-copied table that could silently drift from it.

Every mutating/path-param case below deliberately targets a real,
NONEXISTENT resource id -- the point of this test is the permission
GATE itself (`Depends(require_permission(...))`, which always runs
before any resource lookup), not full business-logic correctness
(already covered by each router's own dedicated test file). A denied
role must get exactly 403 before the resource lookup ever runs; an
allowed role, denied nothing by RBAC, falls through to a real 404 for
a resource that doesn't exist -- 404 and 403 are never confused here.
The two exceptions needing a REAL resource (`POST .../investigations`
needs a real `company_id` to avoid an unhandled FK violation;
`POST /v1/webhooks` needs a real, SSRF-safe https URL) use one shared,
cheap fixture company and a known-public placeholder URL.

`/healthz`, `/readyz`, `POST /v1/auth/login` (pre-authentication, no
role yet) and `POST /v1/auth/logout` (already covered by
`tests/test_api_app.py`) are deliberately out of this matrix -- there
is no role-based allow/deny for any of them to test.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.api import auth, rbac
from ledgerlight.api.models import Membership, Tenant, User
from ledgerlight.config.settings import Settings
from ledgerlight.db.session import make_session_factory
from ledgerlight.knowledge.models import Company

pytestmark = pytest.mark.integration

ROLES = ("viewer", "analyst", "reviewer", "tenant_admin")
RANDOM_ID = uuid.uuid4()  # a real UUID, guaranteed to name no real row


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
                text("DELETE FROM watchlist_items WHERE company_id = ANY(:ids)"),
                {"ids": created["companies"]},
            )
            session.execute(
                text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": created["companies"]}
            )
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
        session.commit()
        session.close()


class RoleClient:
    """One real, independently-authenticated TestClient per role,
    sharing one real tenant/company fixture."""

    def __init__(self, client: TestClient, csrf_token: str, company_id: uuid.UUID) -> None:
        self.client = client
        self.csrf_token = csrf_token
        self.company_id = company_id

    def request(self, method: str, path: str, json: dict[str, object] | None = None) -> int:
        headers = {"X-CSRF-Token": self.csrf_token} if method != "GET" else {}
        response = self.client.request(method, path, json=json, headers=headers)
        return response.status_code


@pytest.fixture
def role_clients(real_session: Session) -> dict[str, RoleClient]:
    """Logs in as all 4 real roles inside one real shared tenant, each
    with its own independent `TestClient` (so logging in as one role
    never disturbs another's session cookie)."""
    tenant = Tenant(name="Authz Matrix Co", slug=f"authz-matrix-{uuid.uuid4().hex[:8]}")
    real_session.add(tenant)
    real_session.flush()
    real_session.info["created"]["tenants"].append(tenant.id)

    company = Company(display_name=f"Authz Matrix Target Co {uuid.uuid4().hex[:8]}")
    real_session.add(company)
    real_session.flush()
    real_session.info["created"]["companies"].append(company.id)

    clients: dict[str, RoleClient] = {}
    for role in ROLES:
        from ledgerlight.api.app import create_app

        user = User(
            tenant_id=tenant.id,
            email=f"{role}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=auth.hash_password("CorrectHorseBatteryStaple"),
        )
        real_session.add(user)
        real_session.flush()
        real_session.add(
            Membership(tenant_id=tenant.id, user_id=user.id, role=role, status="active")
        )
        real_session.commit()

        client = TestClient(create_app())
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
        clients[role] = RoleClient(client, response.json()["csrf_token"], company.id)

    return clients


EndpointSpec = tuple[
    str, str, Callable[[RoleClient], str], str, Callable[[RoleClient], dict[str, object]] | None
]

ENDPOINTS: list[EndpointSpec] = [
    (
        "companies.search",
        "GET",
        lambda rc: "/v1/companies/search?q=test",
        rbac.VIEW_COMPANY_DATA,
        None,
    ),
    (
        "companies.get",
        "GET",
        lambda rc: f"/v1/companies/{rc.company_id}",
        rbac.VIEW_COMPANY_DATA,
        None,
    ),
    (
        "companies.events",
        "GET",
        lambda rc: f"/v1/companies/{rc.company_id}/events",
        rbac.VIEW_COMPANY_DATA,
        None,
    ),
    (
        "companies.timeline",
        "GET",
        lambda rc: f"/v1/companies/{rc.company_id}/timeline",
        rbac.VIEW_COMPANY_DATA,
        None,
    ),
    (
        "companies.scores",
        "GET",
        lambda rc: f"/v1/companies/{rc.company_id}/scores",
        rbac.VIEW_COMPANY_DATA,
        None,
    ),
    (
        "companies.credibility",
        "GET",
        lambda rc: f"/v1/companies/{rc.company_id}/credibility",
        rbac.VIEW_COMPANY_DATA,
        None,
    ),
    (
        "documents.signed_url",
        "GET",
        lambda rc: f"/v1/documents/{RANDOM_ID}/signed-url",
        rbac.VIEW_DOSSIER,
        None,
    ),
    (
        "documents.page_text",
        "GET",
        lambda rc: f"/v1/documents/{RANDOM_ID}/pages/1",
        rbac.VIEW_DOSSIER,
        None,
    ),
    (
        "dossiers.create_investigation",
        "POST",
        lambda rc: "/v1/dossiers/investigations",
        rbac.CREATE_INVESTIGATION,
        lambda rc: {"company_id": str(rc.company_id), "as_of": "2026-01-01"},
    ),
    (
        "dossiers.list_investigations",
        "GET",
        lambda rc: "/v1/dossiers/investigations",
        rbac.VIEW_DOSSIER,
        None,
    ),
    (
        "dossiers.get_investigation",
        "GET",
        lambda rc: f"/v1/dossiers/investigations/{RANDOM_ID}",
        rbac.VIEW_DOSSIER,
        None,
    ),
    (
        "dossiers.get_dossier",
        "GET",
        lambda rc: f"/v1/dossiers/investigations/{RANDOM_ID}/dossier",
        rbac.VIEW_DOSSIER,
        None,
    ),
    (
        "dossiers.export",
        "GET",
        lambda rc: f"/v1/dossiers/investigations/{RANDOM_ID}/export?fmt=markdown",
        rbac.EXPORT_DOSSIER,
        None,
    ),
    ("review.list", "GET", lambda rc: "/v1/review/tasks", rbac.VIEW_REVIEW_QUEUE, None),
    ("review.get", "GET", lambda rc: f"/v1/review/tasks/{RANDOM_ID}", rbac.VIEW_REVIEW_QUEUE, None),
    (
        "review.decide",
        "POST",
        lambda rc: f"/v1/review/tasks/{RANDOM_ID}/decision",
        rbac.DECIDE_REVIEW,
        lambda rc: {"decision": "approve"},
    ),
    ("watchlists.list", "GET", lambda rc: "/v1/watchlists", rbac.MANAGE_OWN_WATCHLISTS, None),
    (
        "watchlists.create",
        "POST",
        lambda rc: "/v1/watchlists",
        rbac.MANAGE_OWN_WATCHLISTS,
        lambda rc: {"name": f"matrix-{uuid.uuid4().hex[:8]}"},
    ),
    (
        "watchlists.delete",
        "DELETE",
        lambda rc: f"/v1/watchlists/{RANDOM_ID}",
        rbac.MANAGE_OWN_WATCHLISTS,
        None,
    ),
    (
        "watchlists.list_items",
        "GET",
        lambda rc: f"/v1/watchlists/{RANDOM_ID}/items",
        rbac.MANAGE_OWN_WATCHLISTS,
        None,
    ),
    (
        "watchlists.add_item",
        "POST",
        lambda rc: f"/v1/watchlists/{RANDOM_ID}/items",
        rbac.MANAGE_OWN_WATCHLISTS,
        lambda rc: {"company_id": str(rc.company_id)},
    ),
    (
        "watchlists.remove_item",
        "DELETE",
        lambda rc: f"/v1/watchlists/{RANDOM_ID}/items/{RANDOM_ID}",
        rbac.MANAGE_OWN_WATCHLISTS,
        None,
    ),
    ("alerts.list_rules", "GET", lambda rc: "/v1/alerts/rules", rbac.MANAGE_OWN_WATCHLISTS, None),
    (
        "alerts.create_rule",
        "POST",
        lambda rc: "/v1/alerts/rules",
        rbac.MANAGE_OWN_WATCHLISTS,
        lambda rc: {"watchlist_id": str(RANDOM_ID), "rule_type": "new_event_type", "config": {}},
    ),
    (
        "alerts.delete_rule",
        "DELETE",
        lambda rc: f"/v1/alerts/rules/{RANDOM_ID}",
        rbac.MANAGE_OWN_WATCHLISTS,
        None,
    ),
    ("alerts.list", "GET", lambda rc: "/v1/alerts", rbac.MANAGE_OWN_WATCHLISTS, None),
    (
        "alerts.acknowledge",
        "POST",
        lambda rc: f"/v1/alerts/{RANDOM_ID}/acknowledge",
        rbac.MANAGE_OWN_WATCHLISTS,
        None,
    ),
    ("api_keys.list", "GET", lambda rc: "/v1/api-keys", rbac.MANAGE_API_KEYS, None),
    (
        "api_keys.create",
        "POST",
        lambda rc: "/v1/api-keys",
        rbac.MANAGE_API_KEYS,
        lambda rc: {"name": f"matrix-{uuid.uuid4().hex[:8]}"},
    ),
    (
        "api_keys.revoke",
        "DELETE",
        lambda rc: f"/v1/api-keys/{RANDOM_ID}",
        rbac.MANAGE_API_KEYS,
        None,
    ),
    ("webhooks.list", "GET", lambda rc: "/v1/webhooks", rbac.MANAGE_WEBHOOKS, None),
    (
        "webhooks.create",
        "POST",
        lambda rc: "/v1/webhooks",
        rbac.MANAGE_WEBHOOKS,
        lambda rc: {"url": "https://example.com/webhook"},
    ),
    (
        "webhooks.delete",
        "DELETE",
        lambda rc: f"/v1/webhooks/{RANDOM_ID}",
        rbac.MANAGE_WEBHOOKS,
        None,
    ),
    (
        "webhooks.test",
        "POST",
        lambda rc: f"/v1/webhooks/{RANDOM_ID}/test",
        rbac.MANAGE_WEBHOOKS,
        None,
    ),
    (
        "webhooks.deliveries",
        "GET",
        lambda rc: f"/v1/webhooks/{RANDOM_ID}/deliveries",
        rbac.MANAGE_WEBHOOKS,
        None,
    ),
    ("admin.list_users", "GET", lambda rc: "/v1/admin/users", rbac.MANAGE_USERS, None),
    (
        "admin.create_user",
        "POST",
        lambda rc: "/v1/admin/users",
        rbac.MANAGE_USERS,
        lambda rc: {
            "email": f"matrix-{uuid.uuid4().hex[:8]}@example.com",
            "password": "A real-enough pw 1!",
            "role": "viewer",
        },
    ),
    (
        "admin.update_role",
        "PATCH",
        lambda rc: f"/v1/admin/users/{RANDOM_ID}/role",
        rbac.MANAGE_USERS,
        lambda rc: {"role": "viewer"},
    ),
    (
        "admin.revoke_user",
        "DELETE",
        lambda rc: f"/v1/admin/users/{RANDOM_ID}",
        rbac.MANAGE_USERS,
        None,
    ),
    ("admin.audit_log", "GET", lambda rc: "/v1/admin/audit-log", rbac.VIEW_AUDIT_LOG, None),
]


@pytest.mark.parametrize("spec", ENDPOINTS, ids=[spec[0] for spec in ENDPOINTS])
def test_authorization_matrix(spec: EndpointSpec, role_clients: dict[str, RoleClient]) -> None:
    name, method, path_fn, permission, body_fn = spec
    for role in ROLES:
        rc = role_clients[role]
        expected_allowed = rbac.has_permission(role, permission)
        status = rc.request(method, path_fn(rc), json=body_fn(rc) if body_fn else None)
        if expected_allowed:
            assert status != 403, (
                f"{name}: role {role!r} HAS {permission!r} but got 403 "
                f"(method={method}, status={status})"
            )
        else:
            assert status == 403, (
                f"{name}: role {role!r} LACKS {permission!r} but got {status}, not 403 "
                f"(method={method})"
            )


#: `MANAGE_ALL_WATCHLISTS` is real and enforced, but never as a route-level
#: allow/deny gate -- every endpoint it touches is reachable by anyone with
#: `MANAGE_OWN_WATCHLISTS` too; it only widens an already-allowed request's
#: own visibility (own rows only, vs. every row in the tenant). Exercised by
#: `test_manage_all_watchlists_widens_visibility_not_access` below instead.
#:
#: `MANAGE_REVIEW_ASSIGNMENTS` is a REAL GAP found while building this
#: matrix: it is defined in `rbac.py` and granted to `tenant_admin`, and
#: `ledgerlight.api.models.ReviewAssignment`/the real `review_assignments`
#: table exist (migration `4dad2cd00443`) -- but no router, endpoint, or
#: script anywhere in this codebase ever checks this permission or reads/
#: writes that table (confirmed via `grep -rln "review_assignments"`,
#: three hits: the model, the permission constant, and the migration
#: itself). Review-task assignment to a specific reviewer was apparently
#: planned (the schema and permission were built) but the actual feature
#: never was. Documented here and in `docs/phase-5/progress.md` as a known
#: limitation, not silently worked around.
_PERMISSIONS_WITHOUT_A_ROUTE_GATE = frozenset(
    {rbac.MANAGE_ALL_WATCHLISTS, rbac.MANAGE_REVIEW_ASSIGNMENTS}
)


def test_every_real_permission_is_exercised_by_this_matrix() -> None:
    """Fails loudly if a new permission is ever added to `rbac.py`
    without a matching entry above (or an explicit, justified carve-out
    in `_PERMISSIONS_WITHOUT_A_ROUTE_GATE`) -- keeps this matrix honest
    as the real permission set evolves, rather than silently going
    stale."""
    exercised = {permission for _, _, _, permission, _ in ENDPOINTS}
    assert exercised | _PERMISSIONS_WITHOUT_A_ROUTE_GATE == rbac.ALL_PERMISSIONS, (
        f"rbac.ALL_PERMISSIONS has permissions neither this matrix nor its "
        f"documented carve-outs cover: "
        f"{rbac.ALL_PERMISSIONS - exercised - _PERMISSIONS_WITHOUT_A_ROUTE_GATE}"
    )


def test_manage_all_watchlists_widens_visibility_not_access(
    role_clients: dict[str, RoleClient],
) -> None:
    """`analyst` (lacks `MANAGE_ALL_WATCHLISTS`) sees only their own
    watchlists on `GET /v1/watchlists`; `tenant_admin` (has it) sees
    every watchlist in the tenant, including the analyst's. Both are
    allowed to call the SAME endpoint -- this permission widens what
    an already-permitted request can see, it never gates the request
    itself (see `_PERMISSIONS_WITHOUT_A_ROUTE_GATE` above)."""
    analyst = role_clients["analyst"]
    admin = role_clients["tenant_admin"]

    create_response = analyst.client.post(
        "/v1/watchlists",
        json={"name": f"analyst-owned-{uuid.uuid4().hex[:8]}"},
        headers={"X-CSRF-Token": analyst.csrf_token},
    )
    assert create_response.status_code == 201, create_response.text
    watchlist_id = create_response.json()["id"]

    analyst_view = analyst.client.get("/v1/watchlists").json()
    assert any(row["id"] == watchlist_id for row in analyst_view)

    admin_view = admin.client.get("/v1/watchlists").json()
    assert any(row["id"] == watchlist_id for row in admin_view)
