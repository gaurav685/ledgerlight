"""Phase 5 §2: the real RBAC permission matrix -- the single source
of truth `docs/security/rbac.md` is generated from (by hand, kept in
sync -- see that doc's own note) and §3's real endpoints check against
server-side, on every request.

Four real roles (`ledgerlight.api.models.ROLES`): `viewer`, `analyst`,
`reviewer`, `tenant_admin`. A role is a real, single string on one
`Membership` row (per real (tenant, user) pair) -- no role hierarchy
is assumed anywhere in this module; each role's own permission set is
listed out explicitly below, not derived from "reviewer >= analyst
>= viewer" or any other implied ordering, since that is exactly the
kind of assumption a real permission bug hides inside.
"""

from __future__ import annotations

VIEW_COMPANY_DATA = "view_company_data"
VIEW_DOSSIER = "view_dossier"
EXPORT_DOSSIER = "export_dossier"
CREATE_INVESTIGATION = "create_investigation"
MANAGE_OWN_WATCHLISTS = "manage_own_watchlists"
MANAGE_ALL_WATCHLISTS = "manage_all_watchlists"
VIEW_REVIEW_QUEUE = "view_review_queue"
DECIDE_REVIEW = "decide_review"
MANAGE_REVIEW_ASSIGNMENTS = "manage_review_assignments"
MANAGE_API_KEYS = "manage_api_keys"
MANAGE_USERS = "manage_users"
MANAGE_WEBHOOKS = "manage_webhooks"
VIEW_AUDIT_LOG = "view_audit_log"

ALL_PERMISSIONS = frozenset(
    {
        VIEW_COMPANY_DATA,
        VIEW_DOSSIER,
        EXPORT_DOSSIER,
        CREATE_INVESTIGATION,
        MANAGE_OWN_WATCHLISTS,
        MANAGE_ALL_WATCHLISTS,
        VIEW_REVIEW_QUEUE,
        DECIDE_REVIEW,
        MANAGE_REVIEW_ASSIGNMENTS,
        MANAGE_API_KEYS,
        MANAGE_USERS,
        MANAGE_WEBHOOKS,
        VIEW_AUDIT_LOG,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({VIEW_COMPANY_DATA, VIEW_DOSSIER, EXPORT_DOSSIER}),
    "analyst": frozenset(
        {
            VIEW_COMPANY_DATA,
            VIEW_DOSSIER,
            EXPORT_DOSSIER,
            CREATE_INVESTIGATION,
            MANAGE_OWN_WATCHLISTS,
        }
    ),
    "reviewer": frozenset(
        {
            VIEW_COMPANY_DATA,
            VIEW_DOSSIER,
            EXPORT_DOSSIER,
            VIEW_REVIEW_QUEUE,
            DECIDE_REVIEW,
        }
    ),
    "tenant_admin": frozenset(
        {
            VIEW_COMPANY_DATA,
            VIEW_DOSSIER,
            EXPORT_DOSSIER,
            CREATE_INVESTIGATION,
            MANAGE_OWN_WATCHLISTS,
            MANAGE_ALL_WATCHLISTS,
            VIEW_REVIEW_QUEUE,
            DECIDE_REVIEW,
            MANAGE_REVIEW_ASSIGNMENTS,
            MANAGE_API_KEYS,
            MANAGE_USERS,
            MANAGE_WEBHOOKS,
            VIEW_AUDIT_LOG,
        }
    ),
}


def has_permission(role: str, permission: str) -> bool:
    """The real, server-side enforcement point every endpoint calls.
    An unknown role (never a real one in this project -- the
    `memberships.role` CHECK constraint already rules that out at the
    database level) has no real permissions, fails closed."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def require_permission(role: str, permission: str) -> None:
    """Raises if `role` lacks `permission` -- the real guard §3's
    endpoints call before doing anything else. Deliberately raises a
    plain `PermissionError`, not an HTTP-specific exception: this
    module has no FastAPI import, per its own docstring; §3 catches
    `PermissionError` and turns it into a real 403."""
    if not has_permission(role, permission):
        raise PermissionError(f"role {role!r} lacks permission {permission!r}")
