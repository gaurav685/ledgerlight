"""Tests for ledgerlight.api.rbac -- Phase 5 §2. Pure unit tests; the
real permission matrix has no DB dependency."""

from __future__ import annotations

import pytest

from ledgerlight.api.models import ROLES
from ledgerlight.api.rbac import (
    ALL_PERMISSIONS,
    CREATE_INVESTIGATION,
    DECIDE_REVIEW,
    MANAGE_API_KEYS,
    ROLE_PERMISSIONS,
    VIEW_COMPANY_DATA,
    has_permission,
    require_permission,
)


def test_every_real_role_has_an_entry_in_the_matrix() -> None:
    for role in ROLES:
        assert role in ROLE_PERMISSIONS


def test_every_permission_in_the_matrix_is_a_real_known_permission() -> None:
    for perms in ROLE_PERMISSIONS.values():
        assert perms <= ALL_PERMISSIONS


def test_viewer_can_view_but_not_create_investigations() -> None:
    assert has_permission("viewer", VIEW_COMPANY_DATA)
    assert not has_permission("viewer", CREATE_INVESTIGATION)


def test_analyst_can_create_investigations_but_not_decide_reviews() -> None:
    assert has_permission("analyst", CREATE_INVESTIGATION)
    assert not has_permission("analyst", DECIDE_REVIEW)


def test_reviewer_can_decide_reviews_but_not_create_investigations() -> None:
    assert has_permission("reviewer", DECIDE_REVIEW)
    assert not has_permission("reviewer", CREATE_INVESTIGATION)


def test_only_tenant_admin_can_manage_api_keys() -> None:
    for role in ROLES:
        if role == "tenant_admin":
            assert has_permission(role, MANAGE_API_KEYS)
        else:
            assert not has_permission(role, MANAGE_API_KEYS)


def test_an_unknown_role_has_no_real_permissions() -> None:
    assert not has_permission("not_a_real_role", VIEW_COMPANY_DATA)


def test_require_permission_raises_for_a_lacking_role() -> None:
    with pytest.raises(PermissionError):
        require_permission("viewer", MANAGE_API_KEYS)


def test_require_permission_does_not_raise_for_a_granted_role() -> None:
    require_permission("tenant_admin", MANAGE_API_KEYS)
