# Phase 5 Progress

Read `docs/phase-5/brief.md` first (the complete, verbatim brief), then this file,
before resuming any session. Branch: `phase-5/api-ui-security`, to be created from
Phase 4's completion commit `d1daf12`.

## Sections done

- **§1 (2026-11-01)**: branch `phase-5/api-ui-security` created from Phase 4 HEAD
  `d1daf12`. Green baseline (`docs/phase-5/evidence/preflight-*`): lint/format/typecheck
  clean, 380 default + 179 integration tests passed. Verbatim Phase 3/4 evidence,
  verifier-fix audit, and review-routing audit all in
  `docs/phase-5/evidence/sec01-preflight-verbatim-and-audits.md`.
  **This preflight itself found two more real verifier blind spots** (commit
  `9189752`, before the main evidence-gathering commit `11fd242`): scoping
  `date_in_span` away from metric claims (Phase 4's own fix) removed the only check
  comparing a care_rating claim's `known_at` to anything, and making `timeline_entry`
  blanket-exempt removed any check on its real `document_version_id` -- both would
  have let a wrong-dated claim of either type pass uncaught. Fixed with
  `check_known_at_matches_evidence`/`check_timeline_entry_claim`, regression-tested,
  re-verified against real DHFL data and the full suite. No stop condition
  triggered -- cleared to proceed.

- **§2 (2026-11-01)**: `ledgerlight/api/models.py` -- every real tenant-owned table the
  brief lists; migration `4dad2cd00443` (tables, nullable `investigations.tenant_id`,
  the real non-superuser `ledgerlight_app` role, grants, RLS policies on every
  tenant-owned table). `ledgerlight/api/tenancy.py` (`tenant_scope`, the real
  per-transaction `app.tenant_id` GUC via `set_config`), `auth.py` (argon2id password
  hashing, real Postgres-backed sessions with rotation, CSRF, login lockout via
  `audit_logs`), `api_keys.py`, `rbac.py` (the 4-role permission matrix). 5 real
  DB-level RLS isolation tests (`tests/test_api_rls.py`, connecting as the real
  restricted role) plus 27 more for auth/api_keys/rbac -- every real function
  hand-verified against the real local Postgres stack before being written as a test.
  `docs/security/rbac.md`, `docs/adr/0008-api-auth-tenancy.md`.

  **Two real bugs found and fixed**: (1) a Python-side `ForeignKey("tenants.id")` on
  the existing Phase 4 `Investigation` model broke every real Phase 1-4 entry point
  that does not import `ledgerlight.api.models` (a real `NoReferencedTableError`,
  confirmed running `run_investigation` against real GENSOL/DHFL data) -- fixed by
  dropping the Python-side FK object on every cross-package reference (the real DB-level
  constraint still enforces it); (2) Postgres rejects a real bound parameter inside a
  `SET LOCAL x = $1` statement -- fixed by using `set_config(..., is_local=true)`
  instead, confirmed directly. **§2 is now fully complete.**

## Not yet started

- §3: the API (FastAPI /v1, all endpoints, rate limits, audit logs, alert generation).
- §4: the frontend (Next.js App Router, all pages, security headers, accessibility).
- §5: Docker Compose, config, secrets, seed command.
- §6: production deployment config (AWS architecture doc, Terraform -- not applied).
- §7: CI/CD workflows (validated locally only -- no GitHub remote).
- §8: observability, backup/restore, runbooks.
- §9: security tests (authz matrix, cross-tenant isolation, auth, signed URLs,
  webhooks, rate limiting, input validation, prompt-injection separation, security
  headers, Playwright e2e, optional ZAP baseline).
- §10: documentation (API docs, security docs, frontend/deploy/ops docs, 2 new ADRs,
  release-gates.md update, README update, phase-5-report.md).
- §11: run and verify.
- §12: final commit/backup.
- §13: exit gates.
- §14: final report, `docs/phase-5/phase-5-report.md`.

## §3 in progress (2026-11-01)

Foundations built and tested: `ledgerlight/api/audit.py` (generic append-only audit
writer), `webhooks.py` (Fernet secret encryption, HMAC-SHA256 signing, real SSRF
protection re-checked before every delivery attempt, retries/backoff), `rate_limit.py`
+ migration `780f44fe5dbc` (real Postgres-backed atomic fixed-window counter,
`docs/adr/0010-rate-limiting.md`), `ObjectStore.presigned_get_url` (real boto3
presigned GET), `deps.py` (the real per-request FastAPI dependency chain: app-role DB
session, identity resolution, CSRF, RBAC).

**Found and fixed a real structural bug** while building `deps.py`: `sessions`/
`api_keys` are RLS-protected tables, so resolving a raw token to its row needs the
tenant context set FIRST -- but that context can only be known AFTER finding the row.
Fixed by giving every token a real, non-secret tenant_id routing segment
(`auth.extract_tenant_id_from_session_token`/`api_keys.extract_tenant_id_from_api_key`),
parsed before the real lookup. Proven directly: a real app-role connection with no
context set cannot see a real session/API-key row at all; scoped via the token's own
extracted tenant_id, it resolves correctly.

**§3's full router set is now built and tested, each against the real local Postgres
stack via FastAPI's `TestClient`** (`ledgerlight/api/app.py` -- factory, request-ID
middleware, security headers, the consistent error model):

- `routers/health.py` -- `/healthz`, `/readyz`.
- `routers/auth.py` -- login/logout/me, the first router to exercise `deps.py` end to
  end.
- `routers/companies.py` -- search/overview/events/timeline/scores/credibility, all
  delegating to Phase 4's own already-tested `ledgerlight.agent.tools` functions
  rather than re-deriving point-in-time logic. Credibility always honestly reports
  insufficient data (`docs/modelling/guidance.md`'s own documented gap), never a
  fabricated figure.
- `routers/dossiers.py` -- create-investigation as a real async job (`BackgroundTasks`,
  using `Investigation.state`/`final_status` as the job's own status, never a second
  job table), status, dossier retrieval, export (markdown/JSON).
- `routers/review.py` -- review queue list/get/decide, tenant isolation reached
  transitively through each task's dossier's investigation (no `tenant_id` on
  `review_tasks` itself).
- `routers/watchlists.py` / `routers/alerts.py` -- CRUD, with a real "own vs all"
  split inside one tenant (`MANAGE_OWN_WATCHLISTS` vs `MANAGE_ALL_WATCHLISTS`) on top
  of RLS's own tenant-level isolation.
- `routers/api_keys.py` / `routers/webhooks.py` -- create/list/revoke,
  register/test/deliveries, both `tenant_admin`-only.
- `routers/admin.py` -- user/role create/list/change/revoke, the tenant's own audit
  log viewer.
- `ledgerlight/api/documents.py` + `routers/documents.py` -- signed document links,
  real 5-minute TTL cap, audited.

**Five real bugs found and fixed while wiring this up** (each with a regression test):
(1) the RLS-bootstrapping circular dependency (already recorded above, found while
building `deps.py`); (2) `ledgerlight.agent.review.record_decision` commits
internally, which is incompatible with being called inside `get_db`'s own
request-scoped transaction (`InvalidRequestError: Can't operate on closed
transaction`) -- fixed via an independent session, same pattern as `rate_limit.py`;
(3) FastAPI still infers a response body from a `-> None` return annotation unless
`response_model=None` is passed explicitly alongside `status_code=204` -- broke the
WHOLE app at `create_app()` time the instant the first 204 route was added; (4) a
50ms rate-limit test window was genuinely too tight for two separate real DB
round-trips, made flaky, not a product bug -- widened to 1 second; (5)
`run_investigation` never set `tenant_id` on the `Investigation` row it creates,
which would make an API-created investigation permanently invisible to the very
tenant who asked for it under RLS -- added an optional `tenant_id` param, `None` for
every CLI/agent-eval call site (unchanged).

One real test-environment gotcha resolved (not a product bug):
`tests/conftest.py`'s own autouse `_isolate_env` wipes every real `LEDGERLIGHT_*` env
var; every setting except S3 credentials has a class-level default matching the real
local dev value, so `load_settings()` silently kept working through the wipe for
those -- but S3 correctly has no such default, so the documents test needed the real
S3 env vars restored via `monkeypatch.setenv` for its own duration.

Commits: `0cbbc04` (app+auth), `47bb316` (companies), `2ca7df4` (dossiers,
`run_investigation` tenant_id), `203e108` (review), `b5b22b0` (watchlists/alerts),
`1ffd598` (api-keys/webhooks), `6412f24` (admin), `6f9ff75` (documents).

## Not yet started

- §3 remainder: the real Dagster alerts-generation job (evaluate `alert_rules`
  against new events/scores for watchlisted companies, create `Alert` rows, trigger
  webhooks), OpenAPI export, §3's own docs (`docs/security/threat-model.md`,
  `docs/security/controls.md`).
- §4: the frontend (Next.js App Router, all pages, security headers, accessibility).
- §5: Docker Compose, config, secrets, seed command.
- §6: production deployment config (AWS architecture doc, Terraform -- not applied).
- §7: CI/CD workflows (validated locally only -- no GitHub remote).
- §8: observability, backup/restore, runbooks.
- §9: security tests (authz matrix, cross-tenant isolation, auth, signed URLs,
  webhooks, rate limiting, input validation, prompt-injection separation, security
  headers, Playwright e2e, optional ZAP baseline).
- §10: remaining documentation (API docs, frontend/deploy/ops docs, ADR 0009, Sec3's
  own threat-model/controls docs, release-gates.md update, README update,
  phase-5-report.md).
- §11: run and verify.
- §12: final commit/backup.
- §13: exit gates.
- §14: final report, `docs/phase-5/phase-5-report.md`.

## Exact next step

Build the real Dagster alerts-generation job in `ledgerlight.orchestration`, then
OpenAPI export + §3's own remaining docs, closing out §3 fully before moving to §4
(frontend).

## Pending items carried over from the end of Phase 4 (not part of this brief, flagged
so they are not lost)

- User asked to push the Phase 4 backup bundle to a git remote -- no remote is
  configured (`git remote -v` empty); asked user for the remote URL, not yet answered.
  This brief's own GIT POLICY is "commit locally only, no remote, no push" -- same as
  every prior phase -- so this stays parked unless/until the user gives a URL and
  confirms the override explicitly.
- User asked to "check SpiceJet's control-group decision" -- the real, still-open
  human decision from Phase 3 report §17.1 (8 real NCLT petitions found against
  SpiceJet 2021-2026, calling its original "no known distress" Phase 0 role into
  question). Not yet resolved; options from that section:
  1. Keep SpiceJet with the current disclosed caveat.
  2. Reclassify it.
  3. Drop it from evaluation entirely (would not change the pooled positive-event
     count, since its events are already censored out, but would change the universe's
     company count and B1's rule-based predictions in several folds).
  This is a human decision, not something to resolve unilaterally; flagged here to
  surface again once Phase 5's own work reaches a natural pause point, or sooner if
  the user asks.

## Open defects / known limitations (carried forward from Phase 4, relevant to Phase 5)

- 69 of 127 real `event_fields` rows (`order_document`) have a genuinely zero-length
  evidence span -- correctly fails citation_resolves; relevant to Phase 5's event
  timeline/evidence-link UI (a real event may legitimately have no highlightable span).
- The Phase 3 risk model is statistically inconclusive; every Phase 5 score view must
  keep the model-limitations banner, per the brief's own §4 requirement.
- No EVENT-CANDIDATE event type meets the Phase 3 reliability bar; Phase 5's event
  timeline must keep showing VERIFIED/CANDIDATE tier badges.
- Human review of real dossiers has never happened (deferred to Phase 6,
  `docs/release/release-gates.md`) -- Phase 5's review-queue UI exists so this CAN
  happen, but doing the actual review is still out of scope here too.
- SpiceJet's control-group status (see above) -- unresolved, human decision pending.
