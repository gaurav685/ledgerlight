# ADR 0008: API Authentication and Tenancy (Phase 5)

## Status
Accepted (Phase 5).

## Context
Phase 5 needed real multi-tenant isolation (Postgres Row-Level
Security), real authentication (password hashing, server-side
sessions, CSRF, API keys), and a real RBAC permission matrix, on top
of Phase 1-4's existing, single-tenant schema (companies, events,
scores, the investigation agent's own tables). Several real design
decisions were made along the way; this records them.

## Decisions

### 1. A `User` belongs to exactly one real tenant

`users.tenant_id` is a direct, required column -- the same literal
person cannot share one login identity across two tenants in this
schema. `memberships` still exists as a separate table (role, status,
invited_by) rather than folding a `role` column directly onto `users`,
so every tenant-owned table's own RLS policy filters on its own
direct `tenant_id` column, never a cross-table join inside a policy.

**Consequence**: if a real person legitimately needs access to two
tenants later, they need two separate `User` rows (one per tenant),
with two separate email/password credentials. Accepted for Phase 5 --
simpler RLS, simpler session model, and no real customer need for
cross-tenant users was stated in the brief.

### 2. RLS via `set_config`, never a parameterized `SET LOCAL`

Postgres's extended query protocol does not allow a real bound
parameter inside a `SET LOCAL x = $1` statement's own value position
-- confirmed directly while building `ledgerlight.api.tenancy.tenant_scope`.
`SELECT set_config('app.tenant_id', :tenant_id, true)` is a normal
function call and takes a normal bound parameter correctly, with the
same `is_local=true` (transaction-scoped) behavior `SET LOCAL` would
have given.

### 3. A Python-side `ForeignKey` cannot cross `ledgerlight.agent`/
`ledgerlight.api`/`ledgerlight.knowledge` package boundaries safely

SQLAlchemy resolves a `ForeignKey("other_table.id")` object's target
table lazily, but eagerly enough that the FIRST real persistence
through a mapper that needs to sort tables by FK dependency (any real
INSERT/UPDATE/DELETE) requires every referenced table to already be
registered on the shared `Base.metadata` -- which only happens if the
module that defines it has actually been imported. Confirmed as a
real, reproducible `NoReferencedTableError` running `run_investigation`
against real GENSOL/DHFL data after adding `investigations.tenant_id`
with a real Python `ForeignKey("tenants.id")`: `ledgerlight.agent.*`
and all of Phase 1-4's CLI scripts never import `ledgerlight.api.models`,
so the target table was never registered.

**Decision**: every cross-package FK reference (`investigations.tenant_id`
-> `tenants.id`; `WatchlistItem`/`Alert.company_id` -> `companies.id`;
`ReviewAssignment.review_task_id` -> `review_tasks.id`) is declared as
a plain, typed column with NO Python-side `ForeignKey` object. The
real database-level foreign key constraint is still created directly
via the migration's own `op.create_foreign_key`/`ForeignKeyConstraint`
calls, so Postgres itself still enforces it regardless of what the
ORM model declares -- this is purely about avoiding a Python-level,
import-order-dependent failure, never a weakening of real referential
integrity.

### 4. `review_tasks` itself carries no `tenant_id`

The brief's own §2 table list says "review assignments", not "review
tasks" -- Phase 4's `review_tasks`/`review_decisions_audit` stay
exactly as built, global, un-RLS'd. `ReviewAssignment` (real,
tenant-owned, RLS'd) is the bridge: which specific tenant user a real
review task is assigned to work on. A real review task's tenant, for
visibility purposes, is reached transitively through its dossier's
investigation's own (now real) `tenant_id` -- the §3 API layer's own
query responsibility, not a second `tenant_id` column duplicated onto
every Phase 4 table.

### 5. `audit_logs` is reused as the real source of truth for login
lockout, not a second table

`ledgerlight.api.auth.record_login_attempt`/`check_lockout` read and
write real `audit_logs` rows (`action='login_failed'`/`'login_succeeded'`)
rather than a dedicated `login_attempts` table -- the brief already
requires audit logging of auth events, so counting recent real
failures from the same real table avoids a second, parallel home for
what is fundamentally the same real fact.

## Consequences
- RLS isolation is proven at the DB level directly
  (`tests/test_api_rls.py`), connecting as the real, restricted
  `ledgerlight_app` role -- never asserted only through application
  code that could itself contain the bug it's supposed to prevent.
- Every real auth primitive (password hashing, sessions, CSRF, login
  lockout, API keys) is framework-agnostic Python with no FastAPI
  import -- §3 wires real return values into real HTTP cookies/headers,
  but the business logic itself is independently testable and already
  is (`tests/test_api_auth.py`, `tests/test_api_api_keys.py`).
- The real cost of decision 1: no cross-tenant user identity. Revisit
  only if a real customer need for it is stated.
