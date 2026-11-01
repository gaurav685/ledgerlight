# RBAC Permission Matrix (Phase 5 §2)

The real single source of truth is `ledgerlight/api/rbac.py`
(`ROLE_PERMISSIONS`); this table is kept in sync with it by hand --
if they ever disagree, the code is authoritative, and this doc has a
real bug to fix.

Four real roles (`ledgerlight.api.models.ROLES`), one per real
`Membership` row (one role per (tenant, user) pair). No role
hierarchy is assumed anywhere in the real enforcement code
(`has_permission`/`require_permission`) -- each role's permissions are
listed explicitly, never derived from an implied ordering like
"reviewer >= analyst >= viewer".

| Permission | viewer | analyst | reviewer | tenant_admin |
|---|---|---|---|---|
| `view_company_data` (company overview, event timeline, scores, SHAP) | ✅ | ✅ | ✅ | ✅ |
| `view_dossier` | ✅ | ✅ | ✅ | ✅ |
| `export_dossier` (Markdown/JSON) | ✅ | ✅ | ✅ | ✅ |
| `create_investigation` | ❌ | ✅ | ❌ | ✅ |
| `manage_own_watchlists` (create/edit/delete one's own) | ❌ | ✅ | ❌ | ✅ |
| `manage_all_watchlists` (any tenant user's) | ❌ | ❌ | ❌ | ✅ |
| `view_review_queue` | ❌ | ❌ | ✅ | ✅ |
| `decide_review` (approve/approve_with_edits/reject/escalate) | ❌ | ❌ | ✅ | ✅ |
| `manage_review_assignments` (assign a real review task to a reviewer) | ❌ | ❌ | ❌ | ✅ |
| `manage_api_keys` (create/revoke) | ❌ | ❌ | ❌ | ✅ |
| `manage_users` (invite/change role/revoke membership) | ❌ | ❌ | ❌ | ✅ |
| `manage_webhooks` (register/test/list deliveries) | ❌ | ❌ | ❌ | ✅ |
| `view_audit_log` | ❌ | ❌ | ❌ | ✅ |

## Real enforcement

Every §3 endpoint calls `ledgerlight.api.rbac.require_permission(role,
permission)` before doing anything else -- a real, server-side check
on every request, never a client-side-only restriction (the frontend
hiding a button is a real UX nicety, not the actual control). An
unknown role (never produced by real code -- `memberships.role` has a
real database `CHECK` constraint limiting it to the four roles above)
has no real permissions and fails closed.

`require_permission` raises a plain `PermissionError` (this module has
no FastAPI import, by design -- see its own docstring); §3's real
endpoint layer catches that and returns a real `403`, never a stack
trace.

## API keys and scopes

A real API key (`ledgerlight.api.api_keys`) carries its own real
`scopes` list, independent of its creator's role at the time -- a
scope is checked in addition to, never instead of, the real RBAC
check for the acting user's own current role. A key's scopes can
therefore only ever narrow what that key can do relative to its
creator's role, never widen it.

## Tenant isolation is a separate, lower layer

RBAC answers "can this role do X at all"; real Row-Level Security
(`docs/adr/0008-api-auth-tenancy.md`, `tests/test_api_rls.py`) answers
"which tenant's rows can this connection see or write at all" --
independently of role. Both checks apply to every real request; RBAC
never substitutes for RLS, and RLS never substitutes for RBAC.
