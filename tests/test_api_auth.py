"""Tests for ledgerlight.api.auth -- Phase 5 §2. Password hashing is
pure; sessions/CSRF/lockout commit real rows (create_session,
rotate_session, revoke_session, record_login_attempt all flush/commit
internally), so this uses the same real, independent-session-with-
manual-cleanup pattern as test_agent_state_machine.py, never the
project's usual rolled-back `db_session` fixture.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.api import auth
from ledgerlight.api.models import Tenant, User
from ledgerlight.api.tenancy import make_app_session_factory, tenant_scope
from ledgerlight.config.settings import Settings
from ledgerlight.db.session import make_session_factory

pytestmark = pytest.mark.integration


# --- password hashing (pure) ---------------------------------------------------


def test_hash_password_produces_a_real_argon2id_hash() -> None:
    result = auth.hash_password("CorrectHorseBatteryStaple")
    assert result.startswith("$argon2id$")


def test_verify_password_accepts_the_real_correct_password() -> None:
    hashed = auth.hash_password("CorrectHorseBatteryStaple")
    assert auth.verify_password("CorrectHorseBatteryStaple", hashed)


def test_verify_password_rejects_a_real_wrong_password() -> None:
    hashed = auth.hash_password("CorrectHorseBatteryStaple")
    assert not auth.verify_password("WrongPassword", hashed)


def test_hash_password_never_stores_the_plaintext() -> None:
    assert "CorrectHorseBatteryStaple" not in auth.hash_password("CorrectHorseBatteryStaple")


# --- sessions / CSRF / lockout (real commits) ----------------------------------


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
        from sqlalchemy import text

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
                text("DELETE FROM users WHERE tenant_id = ANY(:ids)"), {"ids": created["tenants"]}
            )
            session.execute(
                text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": created["tenants"]}
            )
            session.commit()
        session.close()


def _make_tenant_and_user(session: Session) -> tuple[Tenant, User]:
    tenant = Tenant(name="Auth Test Co", slug=f"auth-test-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    session.flush()
    session.info["created"]["tenants"].append(tenant.id)
    user = User(tenant_id=tenant.id, email=f"{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    session.flush()
    return tenant, user


def test_create_and_validate_a_real_session(real_session: Session) -> None:
    tenant, user = _make_tenant_and_user(real_session)
    row, raw_token = auth.create_session(real_session, tenant.id, user.id)
    real_session.commit()

    validated = auth.validate_session(real_session, raw_token)
    assert validated is not None
    assert validated.id == row.id


def test_session_token_carries_a_real_tenant_id_routing_prefix(real_session: Session) -> None:
    tenant, user = _make_tenant_and_user(real_session)
    _row, raw_token = auth.create_session(real_session, tenant.id, user.id)
    real_session.commit()

    assert auth.extract_tenant_id_from_session_token(raw_token) == tenant.id


def test_extract_tenant_id_from_session_token_rejects_malformed_tokens() -> None:
    assert auth.extract_tenant_id_from_session_token("not-a-real-token") is None
    assert auth.extract_tenant_id_from_session_token("not-a-uuid.the-rest") is None


def test_validate_session_through_the_real_app_role_requires_tenant_scope(
    real_session: Session,
) -> None:
    """The real bug this closes: `sessions` is itself a real,
    RLS-protected table. A real app-role connection with NO tenant
    context set cannot see the real session row at all (not merely
    "wrong tenant" -- genuinely invisible), and the SAME connection
    with the real tenant context set (derived from the token's own
    routing prefix, exactly as `ledgerlight.api.deps._resolve_identity`
    does it) resolves it correctly."""
    tenant, user = _make_tenant_and_user(real_session)
    _row, raw_token = auth.create_session(real_session, tenant.id, user.id)
    real_session.commit()

    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    app_settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    try:
        app_factory = make_app_session_factory(app_settings)
        with app_factory() as probe:
            probe.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"ledgerlight_app role not reachable (migration 4dad2cd00443 applied?): {exc}")

    with app_factory() as app_session, app_session.begin():
        no_context_result = auth.validate_session(app_session, raw_token)
        assert no_context_result is None

    routing_tenant_id = auth.extract_tenant_id_from_session_token(raw_token)
    assert routing_tenant_id == tenant.id
    with (
        app_factory() as app_session,
        app_session.begin(),
        tenant_scope(app_session, routing_tenant_id),
    ):
        scoped_result = auth.validate_session(app_session, raw_token)
        assert scoped_result is not None
        assert scoped_result.user_id == user.id


def test_validate_session_rejects_an_unknown_token(real_session: Session) -> None:
    assert auth.validate_session(real_session, "not-a-real-token") is None


def test_validate_session_rejects_an_expired_session(real_session: Session) -> None:
    tenant, user = _make_tenant_and_user(real_session)
    _row, raw_token = auth.create_session(
        real_session, tenant.id, user.id, lifetime=dt.timedelta(seconds=-1)
    )
    real_session.commit()
    assert auth.validate_session(real_session, raw_token) is None


def test_rotate_session_kills_the_old_token_and_issues_a_live_new_one(
    real_session: Session,
) -> None:
    tenant, user = _make_tenant_and_user(real_session)
    old_row, old_token = auth.create_session(real_session, tenant.id, user.id)
    real_session.commit()

    new_row, new_token = auth.rotate_session(real_session, old_row)
    real_session.commit()

    assert auth.validate_session(real_session, old_token) is None
    validated_new = auth.validate_session(real_session, new_token)
    assert validated_new is not None and validated_new.id == new_row.id
    assert new_row.rotated_from_session_id == old_row.id


def test_revoke_session_kills_the_token(real_session: Session) -> None:
    tenant, user = _make_tenant_and_user(real_session)
    row, raw_token = auth.create_session(real_session, tenant.id, user.id)
    real_session.commit()

    auth.revoke_session(real_session, row)
    real_session.commit()
    assert auth.validate_session(real_session, raw_token) is None


def test_verify_csrf_accepts_the_real_token_and_rejects_a_wrong_one(
    real_session: Session,
) -> None:
    tenant, user = _make_tenant_and_user(real_session)
    row, _raw_token = auth.create_session(real_session, tenant.id, user.id)
    real_session.commit()

    assert auth.verify_csrf(row, row.csrf_token)
    assert not auth.verify_csrf(row, "wrong-csrf-token")


def test_check_lockout_trips_after_max_attempts(real_session: Session) -> None:
    """record_login_attempt/check_lockout both filter by tenant_id
    explicitly in their own SQL (defense in depth, real even when
    called -- as here -- via the owner role, which RLS does not
    restrict); no tenant_scope is needed for this test to be real."""
    tenant, _user = _make_tenant_and_user(real_session)
    for _ in range(auth.LOGIN_LOCKOUT_MAX_ATTEMPTS):
        auth.record_login_attempt(
            real_session, tenant.id, "locked@example.com", "1.2.3.4", success=False
        )
    real_session.commit()
    assert auth.check_lockout(real_session, tenant.id, "locked@example.com")


def test_check_lockout_is_false_below_max_attempts(real_session: Session) -> None:
    tenant, _user = _make_tenant_and_user(real_session)
    for _ in range(auth.LOGIN_LOCKOUT_MAX_ATTEMPTS - 1):
        auth.record_login_attempt(
            real_session, tenant.id, "notlocked@example.com", "1.2.3.4", success=False
        )
    real_session.commit()
    assert not auth.check_lockout(real_session, tenant.id, "notlocked@example.com")
