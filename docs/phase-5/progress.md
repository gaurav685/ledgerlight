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

## §3 complete (2026-11-01)

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

`scripts/generate_alerts.py` (the real alerts-generation job -- evaluates every
active `alert_rules` row against new events/scores for its watchlist's companies,
creates `Alert` rows, triggers real signed webhook deliveries; idempotent per
(rule, fact)) wired into `ledgerlight.orchestration.definitions` on a 15-minute
Dagster schedule. `scripts/export_openapi.py` exports the live app's real OpenAPI
schema to `docs/api/openapi.json` (37 real paths) -- generated, never hand-written.
`docs/api/usage-guide.md`, `docs/security/threat-model.md`,
`docs/security/controls.md` written, each grounded in real code/test pointers.

Commits: `0cbbc04` (app+auth), `47bb316` (companies), `2ca7df4` (dossiers,
`run_investigation` tenant_id), `203e108` (review), `b5b22b0` (watchlists/alerts),
`1ffd598` (api-keys/webhooks), `6412f24` (admin), `6f9ff75` (documents), `41cf28c`
(alerts job), `b5d378d` (OpenAPI export + docs). **§3 is now fully complete.**

## §4 core pages complete (2026-11-01)

`frontend/`: Next.js 16 + React 19 + TypeScript strict + ESLint, pnpm with a committed
lockfile (corepack installed to a user-writable directory -- no admin rights needed
on this Windows host). `next.config.ts` proxies `/api/*` straight through to the real
FastAPI backend (same origin from the browser's own point of view, so the real
session cookie just works, no CORS configuration anywhere) and sets the same real
security headers (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy,
HSTS) the backend already sets. `lib/api.ts`/`lib/auth.tsx`: the one real HTTP
client (CSRF header from sessionStorage on every mutation, typed `ApiError`) and
real identity state.

Every page in the brief's own list is built, each a Client Component fetching the
real `/v1` API on mount -- never hardcoded demo data: `/login`; `/companies`
(search); `/companies/[id]` (overview, point-in-time `as_of` control, real score +
SHAP table, the permanent model-limitations banner); `/companies/[id]/timeline`
(real event/filing timeline, VERIFIED/CANDIDATE tier badges); `/documents/[id]`
(the real, immutable extracted page text with the cited span highlighted against
it -- a new `GET /v1/documents/{id}/pages/{n}` endpoint built for this, since no
real per-page PDF rendering exists); `/dossiers` + `/dossiers/[id]` (create-
investigation form, list, status polling, 8-section dossier, markdown/JSON export);
`/review` + `/review/[id]` (queue, decision form); `/watchlists` (CRUD, alert
rules, alerts); `/admin` (users/roles, API keys, webhooks, audit log).

**Found and fixed a real, significant security gap** while manually exercising the
real backend through the real frontend proxy (commit `0d5f4bf`): `require_csrf` had
only ever been wired into `/v1/auth/logout`'s own route -- every other
cookie-authenticated mutating endpoint across dossiers/review/watchlists/alerts/
api-keys/webhooks/admin had NO CSRF dependency at all, despite the controls/usage
docs already describing it as universal. Fixed across all 7 routers; 18 existing
tests needed the real csrf_token added to their requests, and 6 new regression
tests (one per router) now prove the missing-header case is rejected, permanently.

Two other real backend gaps found and fixed while building these pages: `ScoreOut`
discarded the real `top_shap_contributors` (`b01d562`); `GET /v1/dossiers/investigations`
(list) was never built despite the brief's own §3 line asking for it (`2ccdb2d`).

Manually verified end to end against the real backend (curl through the real
Next.js dev-server proxy, with a real cookie jar) -- not just unit tests: real
login, real company search/overview/timeline/score against real GENSOL data, a
real investigation run start-to-FINALISE (including real NLI model loading) with a
correctly-cited markdown export, real user/API-key/webhook create-test-revoke
flows, and the CSRF fix proven both ways (403 without the header, success with it).
**The Chrome browser extension was not connected this session, so the actual
rendered DOM/interactivity was never visually verified in a real browser** -- only
the real HTTP contract every page depends on. A follow-up session with the browser
extension connected should do a real visual/interaction pass before this is called
fully done.

Not yet done from §4: a real accessibility audit (labels/semantic HTML used
throughout, but never checked against a real tool); no Playwright e2e yet (§9).

Commits: `6f9ff75`..`16a0fd5` (page-text endpoint), `b01d562` (shap_contributors
fix), `8cc95ab` (scaffold + first 4 pages), `2ccdb2d` (list_investigations),
`b24f1c0` (dossiers pages), `0d5f4bf` (the CSRF fix), `123713e` (review/watchlists/
admin pages).

## §5 complete (2026-11-04)

`Dockerfile` (real multi-stage build, api/worker share it): uv-synced dependencies in
a builder stage, a real non-root `ledgerlight` user (uid/gid 1000) in the final
stage, Python base image pinned by digest (resolved via a real `docker pull`, never
guessed). **Found and fixed a real, significant gap**: `uv.lock` was stale --
fastapi/uvicorn/argon2-cffi/cryptography (all added to `pyproject.toml` back in §2/§3)
were never in the committed lock file at all, so `uv sync --frozen` inside the image
silently installed nothing for them -- confirmed directly: `python -c "import
ledgerlight.api.app"` failed with `ModuleNotFoundError: No module named 'fastapi'`
inside the built container. Regenerated the lock, rebuilt, confirmed the import
succeeds.

`infra/docker-compose.yml`: real `api`/`worker`/`web` services added alongside the
existing `postgres`/`garage`, all on the same real Compose network, real
service-name DNS (never `127.0.0.1`, which only reaches the host's own loopback from
inside a container).

**Found and fixed a real Next.js architectural bug** while verifying the web
container against a real api container: `next.config.ts`'s own `rewrites()` return
value is frozen into `routes-manifest.json` at `next build` time (confirmed
directly) -- a proxy destination read from `process.env.LEDGERLIGHT_API_ORIGIN`
there would be baked in at image-build time, unable to pick up a different real
value from `docker run -e`/Compose's own per-environment config at container start,
exactly the scenario this deployment needs. Replaced with a real Route Handler
(`frontend/app/api/[...path]/route.ts`) whose function body runs fresh per request;
proven directly -- the same built image, pointed at two differently-named api
containers via `-e` at container start (no rebuild), reached the correct one both
times.

`scripts/dev.ps1`: the real, single PowerShell bring-up command this Windows host
needs -- builds+starts every service, waits for real health checks, applies real
migrations, seeds real TEST tenants, prints every real service's URL.

`scripts/seed_test_tenants.py`: two real TEST tenants, one real user per real role
each, real argon2id-hashed passwords, idempotent (verified directly -- a second run
updates rather than duplicates). Used for a full real end-to-end verification:
login through the real containerized web+api stack with a real seeded
`tenant_admin`, returning a real session cookie + CSRF token + identity.

`.env.example` updated for every new real setting this phase added
(`LEDGERLIGHT_ENVIRONMENT`, `APP_DB_USER`/`PASSWORD`, `SESSION_SECRET_KEY`,
`WEBHOOK_SECRET_ENCRYPTION_KEY`, `COOKIE_SECURE`, `API_ORIGIN`).

**Both Docker images were built AND run** against the real local Postgres/Garage
stack (not just `docker build` succeeding) -- real health checks, a real DB
round-trip, a real cross-container login. Test images/containers removed after
verification; nothing left running beyond the project's own persistent
postgres/garage containers (which crashed along with Docker Desktop itself under
this session's own earlier memory pressure and were restarted -- a real environment
hiccup, not a product bug; confirmed healthy again before proceeding).

406 default + 268 integration tests pass. Commits: `ef2ca9a` (fail-fast weak-secret
check), `ca7be95` (Dockerfile/compose/dev.ps1/seed), `72cdac2` (frontend Dockerfile +
the real runtime-correct proxy fix).

## §6 complete (2026-11-04)

`docs/deploy/aws-architecture.md`: the real AWS architecture -- ECS Fargate for
api/worker/web, RDS Postgres+pgvector (a real parameter group, no custom image),
S3 (replacing the local Garage container -- a real config change, not a code
change, since `ledgerlight.storage.s3_store.ObjectStore` already speaks plain
S3-compatible API), Secrets Manager, ALB+ACM TLS, CloudWatch, private subnets,
least-privilege IAM, rough cost notes, disclosed limitations.

`infra/aws/`: real Terraform modeling every piece of it -- network, security
groups, RDS, S3, Secrets Manager (every secret created EMPTY, populated
out-of-band -- writing a real value via Terraform would just move the plaintext
into `.tfstate`), IAM (least-privilege; `web`'s own task role gets zero AWS
permissions), ECS, ALB.

No `terraform` binary is installed on this host -- ran the real, official
`hashicorp/terraform:1.9` Docker image directly. `fmt`/`init`/`validate` all ran
clean; `tflint` (also via its own official Docker image, since the brief allowed
it "if feasible") found and this phase fixed one real issue (a deprecated
interpolation-only expression). Full raw output in
`docs/phase-5/evidence/terraform-validate.log`. **`terraform plan`/`apply` were
never run** -- no AWS credentials in this environment, explicitly out of scope;
stated plainly in `infra/aws/README.md`.

`docs/adr/0011-aws-deployment.md` records the real design decisions.

406 default tests still pass (no Python/TS code touched). Commit: `b73343a`.

## §7 complete (2026-11-04)

Replaced the earlier single-job `.github/workflows/ci.yml` with 5 real workflows
(`backend.yml`, `frontend.yml`, `security.yml`, `build.yml`, `deploy.yml`), every one
validated via the real, official `rhysd/actionlint` Docker image (zero findings) and
by running every real job's own commands directly on this machine. `backend.yml`
runs against a real Postgres service container (268 real integration tests pass);
`frontend.yml` added a real, minimal Playwright smoke suite
(`frontend/e2e/smoke.spec.ts`) against a real `next start` build.

**Found and fixed two real, significant issues** while building `security.yml`, not
just describing it: (1) `pip-audit` found 43 vulnerabilities across 5 packages --
bumped `cryptography`/`fastapi` (pulling a real `starlette` bump), re-tested fully,
cut to 24/3; the remainder needs real major-version jumps with undemonstrated
compatibility risk, triaged and documented rather than forced. (2) a real `trivy
image` scan found both Dockerfiles' pinned base images carrying real, already-
Debian-patched CVEs (92 OS findings/9 CRITICAL in the api image, 50/6 CRITICAL in the
web image, plus a real CRITICAL `tar` CVE bundled inside npm itself) -- added a real
`apt-get upgrade` to both Dockerfiles and pinned `npm@11.21.1` in
`frontend/Dockerfile` (`npm@latest` needs a newer node than this image pins -- a real
`EBADENGINE` failure, confirmed directly). Real before/after: api image 92→38 (9→2
CRITICAL); web image 50→33 OS + 13→3 language findings (6→1, 1→0 CRITICAL). Every
remaining CRITICAL in both images is the same real `zlib1g` CVE, `will_not_fix` by
Debian upstream -- genuinely not fixable here. Both rebuilt images re-verified
functional afterward.

`act` was not attempted -- this session hit three real, confirmed host-memory-
pressure failures during Docker builds already (two Docker build kills, one full
Docker Desktop crash requiring a WSL shutdown + restart to recover); running act's
own full GitHub-runner-equivalent containers was a real, avoidable risk of a fourth
crash, not attempted given the brief's own explicit "if feasible" qualifier.

`docs/release/release-gates.md` gained a new standing gate: every one of these 5
workflows is UNVERIFIED on GitHub's own hosted runners until a first real push,
deferred per this project's own standing GIT POLICY (commit locally only, no remote)
until the user explicitly provides a remote URL and confirms the policy override.

406 default + 268 integration tests pass. Commit: `594444d`.

## §8 complete (2026-11-05)

`ledgerlight.common.logging.configure_logging()` -- real Phase 0 structlog-JSON-
to-stdout infrastructure -- was wired into `ledgerlight.api.app.create_app()`, the
first real entry point in this project's history to ever call it (confirmed via
`grep -rln "configure_logging"` returning only the definition file beforehand).
`ledgerlight/api/metrics.py`: a real `/metrics` endpoint (Prometheus exposition
format, `include_in_schema=False`, never routed through the public ALB listener)
with request-count/duration metrics labelled by method/route-template/status --
deliberately never raw path or tenant_id, to avoid unbounded cardinality. `tenant_id`
is bound into structlog's contextvars in `deps.get_identity()`, alongside the
`request_id` `app.py`'s own middleware already binds.

**Two real bugs found and fixed while verifying this end-to-end, not just
building it**: (1) `configure_logging()`'s own processor chain never included
`structlog.contextvars.merge_contextvars` -- every bound `request_id`/`tenant_id`
was silently dropped from every real log line; confirmed directly before and after
the fix. (2) A handler registered for the bare `Exception` class is wired by
Starlette into the OUTERMOST `ServerErrorMiddleware`, above every
`@app.middleware("http")` layer -- so on a real unhandled exception,
`X-Request-ID` and all four security headers were silently missing from the
response (the header-setting middlewares' own post-`call_next` mutations never
ran for this path). Fixed by setting those headers directly inside the one
affected handler; confirmed directly before and after. Also removed
`configure_logging()`'s eager `sys.stdout` capture (now defaults to structlog's
own early-bound reference) after it left a dead file object behind in a
cross-test interaction found while writing the regression tests for the above.

`scripts/backup.py`: a real `pg_dump -Fc` of the real `ledgerlight` database (via
`docker exec` into the real Postgres container) plus a real object-by-object sync
of the real Garage bucket, every object's sha256 checked against its own
content-addressed key as it's downloaded. Output goes to
`../ledgerlight-backups/` (outside the repo, same convention as this project's
existing git-bundle backups).

`scripts/restore_drill.py`: a REAL restore drill, not simulated -- restores the
latest backup into a fresh, disposable database and a fresh, disposable Garage
bucket, compares real row counts for every one of the real database's 53 tables
(queried from `pg_tables`, never a hardcoded list) against the source, re-verifies
every restored object's sha256, then drops the drill resources. **Actually run**
this phase (`docs/phase-5/evidence/restore-drill.log`): all 53 tables matched
exactly; all 2,626 objects restored and sha256-verified.

`docs/ops/`: 7 real runbooks, each grounded in this project's own actual code
(startup-shutdown, secret-rotation, key-revocation, restore, incident-response,
rate-limit-tuning, webhook-failures). Secret rotation and key-revocation both
surface a real, honestly-disclosed gap found while writing them: the webhook
secret-encryption key has no safe one-step rotation (every existing
`webhooks.secret_encrypted` value is encrypted under the old key -- the runbook
documents the real re-encrypt-then-swap procedure needed); and there is no single
admin action to force-expire a specific user's existing sessions immediately
(membership revocation takes effect on the user's very next request, but the raw
session row otherwise lives until its own 12-hour expiry -- the runbook documents
the direct manual-delete remediation for an urgent case).

406 default + 272 integration tests pass (4 new, all in `tests/test_api_app.py`).
ruff/mypy clean. Commits: `24dba64` (observability), `936a9bd` (backup/restore
drill/runbooks).

**Found and fixed one more real gap against the brief's own verbatim §8 line**
("request counts, latency histograms, error rates, job outcomes"): job outcomes
had no metric at all. Added `ledgerlight_job_outcomes_total` (labelled
job/outcome) to `ledgerlight/api/metrics.py`, incremented around the real
background investigation job in `routers/dossiers.py`; regression-tested via
`/metrics` before/after a real investigation run
(`tests/test_api_dossiers.py`). `scripts/generate_alerts.py` (a separate,
short-lived batch process, not the long-running API process -- a Prometheus
counter there would never be scraped before the process exits) gets a real
structured-JSON job-outcome log line instead. 406 default tests re-confirmed
green after. Commit: `2875029`.

## Not yet started

- §9: security tests (authz matrix, cross-tenant isolation, auth, signed URLs,
  webhooks, rate limiting, input validation, prompt-injection separation, security
  headers, Playwright e2e, optional ZAP baseline).
- §10: remaining documentation (frontend/deploy docs, ADR 0009, release-gates.md
  update, README update, phase-5-report.md). API/security/ops docs are already done
  (above).
- §11: run and verify.
- §12: final commit/backup.
- §13: exit gates.
- §14: final report, `docs/phase-5/phase-5-report.md`.

## §9 in progress (2026-11-05)

`tests/test_authz_matrix.py`: the brief's own required authorisation-matrix test
-- every real permission-gated endpoint (40 of them) × every real role, with the
expected allow/deny derived LIVE from `rbac.ROLE_PERMISSIONS` (never a second,
hand-copied table that could drift from it). Every case targets a real,
nonexistent resource id deliberately -- the point is the permission gate itself
(`Depends(require_permission(...))`, which always runs before any resource
lookup), never full business-logic correctness (already covered elsewhere); a
denied role must get exactly 403, an allowed role falls through to a real 404 for
the made-up id. A second test fails loudly if `rbac.ALL_PERMISSIONS` ever gains a
permission with no matching matrix entry (or documented carve-out).

**Found a real, previously-undiscovered gap while building this matrix**:
`MANAGE_REVIEW_ASSIGNMENTS` is defined in `rbac.py` and granted to
`tenant_admin`, and the real `review_assignments` table/`ReviewAssignment` model
exist (migration `4dad2cd00443`) -- but no router, endpoint, or script anywhere
in this codebase ever checks this permission or touches that table (confirmed:
`grep -rln "review_assignments"` returns only the model, the permission
constant, and the migration itself). Review-task assignment to a specific
reviewer was apparently planned -- schema and permission both built -- but the
actual feature never was. Documented as a known limitation (both in the test
file and here), not silently worked around; building the missing feature is out
of scope for a security-test pass and is flagged for a future phase.
`MANAGE_ALL_WATCHLISTS` is real and enforced but never as a route-level gate (it
widens an already-allowed request's own visibility, own-only vs. every row in
the tenant) -- a dedicated test
(`test_manage_all_watchlists_widens_visibility_not_access`) proves this directly
instead of forcing it into the gate-shaped matrix.

406 default + 314 integration tests pass (42 new, all in
`tests/test_authz_matrix.py`). ruff/mypy clean.

`tests/test_cross_tenant_idor.py`: real API-level IDOR attempts for the
resource types not already covered by a more specific file (dossiers/
investigations and review tasks already had their own cross-tenant tests) --
watchlists, alert rules, alerts, API keys, webhooks. Tenant B tries 8 real
read/write operations against tenant A's real ids; every one gets a clean 404,
never a 403 (which would itself leak that the id exists). Passed clean on the
first real run -- the RLS/ownership boundary genuinely holds.

`tests/test_security_controls.py`: security headers on a normal (non-error)
response (the existing regression test only covered the unhandled-exception
path), rate-limit 429+Retry-After through the real HTTP login endpoint
(previously only unit-tested directly against `rate_limit.py`), a real
session-fixation probe (an attacker-chosen cookie sent on the login request is
never adopted -- the server always issues a brand-new real token), and a
malformed-body-returns-422-with-no-stack-trace check.

**Found two more real things while writing these**: (1) `auth.rotate_session`
(session rotation, unit-tested since §2) has no real call site anywhere in the
API -- built but never wired into any actual flow; documented as a known gap.
(2) The fixation test's first draft produced a false positive from an httpx
`TestClient` cookie-jar domain-scoping quirk (a manually-set cookie with no
domain and the server's own `Set-Cookie` response coexisted as two distinct
jar entries, so a naive jar-scan read the stale one) -- confirmed via a
standalone debug script that the real `Set-Cookie` header was always a
genuinely fresh token, never a real vulnerability; fixed by reading
`response.cookies` directly instead of the shared jar.

406 default + 47 of these new tests individually confirmed pass against the
real stack (42 authz-matrix + 1 IDOR + 4 security-controls). The other 272
pre-existing integration tests were not re-run as one batch after this round
(real host memory pressure from unrelated running applications on this
machine) -- this round touched zero production code, only new test files, so
the risk is low and they were green earlier this same phase. Commits:
`58273a2` (authz matrix), `013d852` (IDOR + security controls).

`tests/test_api_documents.py` gained a real signed-URL expiry test (an
actually-expired presigned URL is genuinely refused by Garage, not just that
the issued TTL is capped). `tests/test_api_webhooks.py` gained two real
DNS-rebinding tests (the brief's own named SSRF case) -- one against
`validate_webhook_url` directly, one through the full `deliver_webhook` retry
loop, proving re-resolution happens fresh on every attempt.
`tests/test_prompt_injection_separation.py` reuses Phase 4's own adversarial-
document shape through the real API (not just at the agent level): a real
investigation over `<script>`+instruction-injected text completes normally,
no claim or exported line treats it as an unattributed instruction, and a
repo-wide grep confirms the frontend never uses `dangerouslySetInnerHTML`.
406 default + 24 of these new/affected tests individually confirmed pass.
Commit: `29ffcb7`.

## §9 deferred items (2026-11-05): ZAP baseline + Playwright e2e

Both need the full real stack (postgres/garage/api/worker/web) up via `docker
compose`, which means rebuilding the `api`/`web` images from scratch (removed
after §5/§7's own verification -- confirmed via `docker images`, neither
exists locally right now) plus running ZAP's own container and a real
Playwright browser simultaneously. Real free host memory checked at the
decision point: 2.22GB, after this session's own repeated real OOM kills
(even plain `pytest -m integration` runs) from unrelated running applications
(Firefox/Brave/Antigravity IDE) -- not a Docker-caused shortage this time
(`vmmemWSL` itself was only ~185MB). User explicitly chose to defer rather
than risk another crash; decision made via `AskUserQuestion`, not
unilaterally. Revisit once real memory headroom is confirmed better --
`scripts/backup.py` first if anything destructive is risked once resumed.

Every other §9 line item (authz matrix, cross-tenant IDOR, auth, signed
URLs, webhook SSRF/signature, rate limiting, input validation/error model,
prompt-injection separation, security headers) is done and committed.

## §10 complete (2026-11-05)

README phase status corrected (Phase 4 was stale "in progress"/"(once
written)" even though `docs/phase-4/phase-4-report.md` already existed --
fixed while touching this section) and a real Phase 5 status paragraph
added. `docs/release/release-gates.md` gained the brief's two required
standing gates ("GitHub Actions runs verified green after the first push",
tightened onto the existing gap; "Terraform plan reviewed before any apply",
a new gap) plus the ZAP/Playwright e2e deferral as its own named gap.
`docs/adr/0009-frontend.md` (5 real decisions: Client-Component-only pages,
the Route Handler proxy, CSRF-in-sessionStorage, duplicated security
headers, corepack-to-a-user-writable-path). `docs/frontend/architecture.md`
(request path, auth flow, every real page's backend calls, what's
deliberately not built yet). `docs/deploy/local-setup-windows.md`
(first-time setup, distinct from `docs/ops/startup-shutdown.md`'s
day-to-day; 3 real Windows-specific gotchas this project actually hit).
Commits: `183b6f7`, `54b460f`.

## §11 in progress (2026-11-05)

Real evidence captured this pass, all under `docs/phase-5/evidence/`:
`pre-commit-all-files.log` (clean), `gitleaks-full-history-phase5.log`
(refreshed -- 171 commits, no leaks), `sec11-backend-lint-typecheck-tests.log`
(ruff/mypy/pytest default -- 408 passed), `sec11-frontend-lint-typecheck.log`
(eslint/tsc clean), `sec11-frontend-build-e2e-smoke.log` (real production
build + 2 real Playwright smoke tests passed), `sec11-migrations-from-empty.log`
(all 11 real migrations applied cleanly to a fresh, empty database, landing
on the same 53 tables the long-lived dev database has),
`sec11-pip-audit.log` (re-run to confirm the §8 `prometheus-client` addition
introduced no new findings -- clean), `sec11-rls-and-authz-matrix.log` (RLS
5 passed fresh; authz-matrix's own fresh re-run was killed by memory
pressure, substituted with its own real 42-passed run from commit `58273a2`
earlier this phase). `sec11-backend-integration-tests.log` documents the
real, honest state of the full-batch integration run (see its own gate in
release-gates.md). actionlint/terraform fmt-validate evidence from §6/§7 is
still valid and unchanged (`docs/phase-5/evidence/github-actions-local-validation.md`,
`terraform-validate.log`) -- nothing in those areas changed this session, so
not re-run. The restore drill's own real evidence is §8's
`restore-drill.log`. Commits: `515a055`, `8304e52`.

**Found and fixed a real local-environment gap** while running the frontend
checks: a bare `pnpm` does not reliably resolve on `PATH` even after
`corepack enable` with no `--install-directory` -- it broke Playwright's own
internal `webServer` spawn specifically. Fixed by materializing real shims
via `corepack enable --install-directory <dir>`; documented in
`docs/deploy/local-setup-windows.md` (including fixing the earlier
first-time-setup snippet, which had the same latent gap).

**Real host memory has been trending down sharply across this §11 pass**
(3.25GB free at the start, down to 0.89GB by the end, from the user's own
other running applications, not this project's own Docker stack) -- 3 more
real kills hit during this pass alone (on top of the ones already recorded
in §8/§9), on top of everything already recorded. Pausing further
Docker/pytest-heavy work here rather than continuing to push against a
worsening resource constraint; flagged to the user directly.

## Exact next step

Screenshots/traces of key pages under `docs/phase-5/evidence/` depend on the
deferred Playwright e2e run against a live backend, so stay deferred with
it (see release-gates.md). Once real memory headroom is confirmed better:
finish §11's remaining re-runs if desired (not strictly required -- the
existing §6/§7/§8 evidence for actionlint/terraform/restore-drill is still
valid), then move to §12 (final commit -- already effectively continuous
this phase; §12 is really about confirming the backup bundle is refreshed)
§13 (exit-gate checklist) and §14 (final report).

Revisit the §4 accessibility/browser-verification gap above if the Chrome
extension becomes available.

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
