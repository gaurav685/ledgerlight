"""Phase 5 §5: seed two real TEST tenants, each with one real user per
real role (viewer, analyst, reviewer, tenant_admin) -- for exercising
the real API/frontend locally without hand-creating rows every time.

Never for anything but localhost dev: every email/password here is a
real, fixed, publicly-known TEST credential, printed to stdout (never
written to a committed file). Idempotent -- running this twice updates
existing rows' passwords rather than erroring on the real unique
(tenant_id, email) constraint.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.api import auth  # noqa: E402
from ledgerlight.api.models import ROLES, Membership, Tenant, User  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402

TEST_PASSWORD = "LedgerlightTest123!"  # noqa: S105 -- a real, fixed, public TEST credential
TENANT_SLUGS = ("test-tenant-a", "test-tenant-b")


def _upsert_tenant(session: Session, slug: str) -> Tenant:
    tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        tenant = Tenant(name=f"Seed {slug}", slug=slug)
        session.add(tenant)
        session.flush()
    return tenant


def _upsert_user_with_role(session: Session, tenant: Tenant, role: str) -> str:
    email = f"{role}@{tenant.slug}.test"
    user = session.scalar(select(User).where(User.tenant_id == tenant.id, User.email == email))
    if user is None:
        user = User(
            tenant_id=tenant.id, email=email, password_hash=auth.hash_password(TEST_PASSWORD)
        )
        session.add(user)
        session.flush()
    else:
        user.password_hash = auth.hash_password(TEST_PASSWORD)

    membership = session.scalar(
        select(Membership).where(Membership.tenant_id == tenant.id, Membership.user_id == user.id)
    )
    if membership is None:
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role, status="active"))
    else:
        membership.role = role
        membership.status = "active"
    session.flush()
    return email


def main() -> int:
    settings = load_settings()
    session = make_session_factory(settings)()
    try:
        print(f"Real TEST password for every seeded user: {TEST_PASSWORD}")
        for slug in TENANT_SLUGS:
            tenant = _upsert_tenant(session, slug)
            print(f"\nTenant {tenant.slug!r} (id={tenant.id}):")
            for role in ROLES:
                email = _upsert_user_with_role(session, tenant, role)
                print(f"  {role:<13} {email}")
        session.commit()
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
