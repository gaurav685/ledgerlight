"""Phase 5 §5: real end-to-end test for scripts/seed_test_tenants.py
-- creates two real tenants with one real user per real role, and
re-running it is idempotent (same rows, not duplicates)."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.api.models import ROLES, Membership, Tenant, User
from ledgerlight.config.settings import Settings
from ledgerlight.db.session import make_session_factory

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "seed_test_tenants", REPO_ROOT / "scripts" / "seed_test_tenants.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["seed_test_tenants"] = _MODULE
_SPEC.loader.exec_module(_MODULE)


@pytest.fixture
def real_session() -> Iterator[Session]:
    try:
        settings = Settings(_env_file=str(REPO_ROOT / ".env"))  # type: ignore[call-arg]
    except Exception as exc:
        pytest.skip(f"could not load real .env for integration test: {exc}")
    try:
        session = make_session_factory(settings)()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable (is the Docker stack up?): {exc}")
    try:
        yield session
    finally:
        session.close()


def test_seed_creates_two_tenants_with_every_role_and_is_idempotent(
    real_session: Session,
) -> None:
    first_exit_code = _MODULE.main()
    assert first_exit_code == 0

    tenant_ids: dict[str, uuid.UUID] = {}
    for slug in _MODULE.TENANT_SLUGS:
        tenant = real_session.scalar(select(Tenant).where(Tenant.slug == slug))
        assert tenant is not None
        tenant_ids[slug] = tenant.id

        memberships = real_session.scalars(
            select(Membership).where(Membership.tenant_id == tenant.id)
        ).all()
        roles_seen = {m.role for m in memberships}
        assert roles_seen == set(ROLES)

        for membership in memberships:
            user = real_session.get(User, membership.user_id)
            assert user is not None
            assert user.email == f"{membership.role}@{slug}.test"

    # Re-running must be idempotent -- same real tenant/user rows, not duplicates.
    second_exit_code = _MODULE.main()
    assert second_exit_code == 0
    for slug, tenant_id in tenant_ids.items():
        tenant_again = real_session.scalar(select(Tenant).where(Tenant.slug == slug))
        assert tenant_again is not None
        assert tenant_again.id == tenant_id
        user_count = real_session.execute(
            text("SELECT count(*) FROM users WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar()
        assert user_count == len(ROLES)
