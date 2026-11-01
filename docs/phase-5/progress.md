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

## Exact next step

§1/§2 are done. Next: §3 (the real FastAPI /v1 API -- company search/overview, event
timelines, point-in-time scores, management credibility, dossiers, review tasks,
watchlists/alerts, signed document links, webhooks, health checks, rate limits, audit
logging, the Dagster alerts-generation job), wiring `ledgerlight.api.auth`/`rbac`/
`tenancy` into real HTTP request handling (cookies, CSRF header, RBAC/scope checks on
every endpoint).

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
