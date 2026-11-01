# LEDGERLIGHT — PHASE 5: API, ANALYST INTERFACE, SECURITY AND PRODUCTION READINESS (PART A of B)

Do not start building until Part B arrives. Confirm receipt of Part A and wait. When Part B arrives:
1. Save the full brief (Parts A and B) verbatim to docs/phase-5/brief.md.
2. Create docs/phase-5/progress.md.
3. Commit both, then begin.

You are implementing Phase 5 of Ledgerlight. Phase 4 is complete on branch phase-4/investigation-agent (local commits only), providing:
- the checkpointed investigation agent: 7 read-only tools, claims and dossiers, the offline renderer, the verifier, budgets, review CLI, seeded QC
- agent-eval: 60/60 FINALISED, zero unsupported-claim leakage
Earlier phases provide: ingestion, the knowledge store, entity resolution, retrieval, point-in-time features, outcomes, LightGBM scores with get_score, SHAP, Dagster, Garage, Postgres + pgvector.

Read these before changing anything:
- docs/phase-4/phase-4-report.md and docs/phase-3/phase-3-report.md
- docs/agent/*.md
- docs/modelling/model-card.md and docs/modelling/event-reliability.md
- docs/release/release-gates.md
- docs/adr/*
- the Phase 0 environment report (Node version, Windows host)

Scope: API, frontend, authentication and authorisation, tenancy and RLS, the security controls, Docker Compose, deployment configuration, CI/CD workflows, observability, backup/restore and runbooks. Do NOT do Phase 6 work: full backtest audits, performance and load campaigns, the release, or the final push. Stop at the Phase 5 boundary.

## 0. GROUND RULES

- All earlier ground rules apply:
  - no fabrication
  - honest UA, respect robots.txt and terms
  - no sudo, no secrets or raw data in git
  - never act as the human reviewer
- No mocked API responses presented as real. The UI must call the real API backed by the real database. Test fixtures are clearly labelled.
- Documents and tool output are UNTRUSTED. Render them escaped. Never execute content from filings.
- No portfolios, watchlists, credentials or tenant data are ever sent to an LLM.
- Neutral language and the disclaimers appear throughout the UI and the API docs. Event tiers (VERIFIED/CANDIDATE) and the model limitations, including "statistically inconclusive" where Phase 3 concluded so, are always visible wherever scores or events are shown.
- Account creation: creating TEST users and tenants inside this application, on localhost, with test values, is permitted. Never create accounts on external services.
- Windows host: every run instruction must work from PowerShell. Provide scripts/dev.ps1 (or equivalent) alongside any make targets.
- GIT POLICY: commit locally only. No remote, no push.

## 1. PREFLIGHT: PHASE 3/4 EVIDENCE (stop conditions)

1. Branch phase-5/api-ui-security from the Phase 4 HEAD. Run the full checks and record a green baseline.
2. Print VERBATIM from docs/phase-3/phase-3-report.md:
   - the fold table, with DISTINCT positive events and companies per fold and pooled
   - the metrics tables (models versus the B0 base rate) with intervals
   - calibration choice and reason
   - leakage, permutation, feature-shift and survivorship results
   - the ablation
   - the rating-only and IBBI-only sensitivity results
   - whether any frozen TEST items informed the §1 detector hardening, and the resulting "held-out" status of the test metrics
3. Print VERBATIM from docs/phase-4/phase-4-report.md:
   - one full example dossier (Markdown)
   - the evaluation tables
   - the adversarial test list with results
4. Verifier-fix audit, for the two real verifier bugs:
   - print the code diff and the justification for each
   - show the regression tests that prove a rating claim with a WRONG date still FAILS verification (through whichever check now covers rating dates)
   - show that a timeline_entry with a wrong date or value still FAILS
5. Review routing audit:
   - print review_tasks counts by reason code from the agent-eval run
   - print the number of dossiers relying mainly on CANDIDATE events
6. STOP and report, without starting Phase 5 work, if ANY of the following holds:
   - a wrong-date rating claim or a wrong timeline_entry passes verification
   - dossiers relying mainly on CANDIDATE events did not produce review tasks
   - any Phase 3 leakage check failed
   - frozen TEST items informed hardening but the metrics are still labelled held-out

## 2. TENANCY, AUTH AND RBAC (Alembic migrations)

Tenancy:
- tenants table.
- tenant_id on every tenant-owned table: users, memberships, api_keys, watchlists, watchlist_items, alerts, alert_rules, webhooks, webhook_deliveries, investigations requested via the API, review assignments, audit_logs.
- Public reference data (companies, documents, pages, events, scores, outcomes) is global and read-only to tenants.

Postgres Row-Level Security:
- RLS policies on all tenant-owned tables.
- The application connects as a NON-superuser role without BYPASSRLS.
- The tenant context is set per request with SET LOCAL app.tenant_id inside the transaction.
- Migrations run under a separate owner role.
- Prove isolation with DB-level tests: connect as the app role, set tenant A, and confirm tenant B's rows are invisible and unwritable.

Authentication:
- password hashing with argon2id
- server-side sessions in Postgres, with httpOnly, Secure (configurable for local http) and SameSite cookies
- CSRF protection for cookie-authenticated mutations
- session expiry and rotation
- login rate limiting and lockout/backoff

API keys:
- shown once, stored hashed, with a prefix for lookup
- scopes, expiry, revocation, last-used timestamp

RBAC roles: viewer, analyst, reviewer, tenant_admin.
- Write an explicit permission matrix in docs/security/rbac.md.
- Enforce it server-side on every endpoint.

## 3. API (FastAPI, versioned /v1, OpenAPI)

Endpoints. Every data endpoint accepts as_of where point-in-time applies:
- company search (name, symbol, ISIN) and company overview
- event timelines, with tier, evidence references, event_time and known_at
- point-in-time scores: get_score history, SHAP contributors and model limitations
- management credibility: honestly returns "insufficient data" with the reason (no guidance statements in the corpus)
- dossiers: list, get (Markdown/JSON), create an investigation (async job; returns a job ID and status), export
- review tasks: list, get, decide (reviewer role), with reason codes and the audit
- watchlists: CRUD. Alerts: list and acknowledge. Alert rules: e.g., a new event of type X, or the score percentile crossing a threshold.
- signed document links: authorise first, then issue a presigned Garage/S3 URL with a TTL of 5 minutes or less. Never public buckets.
- webhooks:
  - register (https only), test, list deliveries
  - deliveries signed with HMAC-SHA256 plus a timestamp, with retries and backoff
  - SSRF protection: resolve and block private, loopback, link-local and metadata IPs, re-checked at delivery time
  - webhook secrets encrypted at rest with a key from the environment
- health: /healthz and /readyz

Conventions:
- a consistent error model
- pagination
- input validation (Pydantic)
- request IDs
- no stack traces to clients

Rate limits:
- per user, per API key and per IP, configurable
- implementation choice documented in an ADR: Postgres-backed or in-process for a single instance, with the multi-instance limitation stated
- 429 responses with Retry-After

Audit logs: append-only, recording actor, tenant, action, target, timestamp, request ID and IP. Covers auth events, key creation and revocation, review decisions, investigation creation and document link issuance.

Alerts generation: a Dagster job evaluates alert rules against new events and scores for watchlisted companies, creates alerts per tenant, and triggers webhooks.

# LEDGERLIGHT — PHASE 5 BRIEF (PART B of B)

## 4. FRONTEND (Next.js App Router + TypeScript)

- Check the Node version. Use pnpm with a committed lockfile and pinned versions. TypeScript strict mode, ESLint.
- All data comes from the real /v1 API. No hardcoded demo data in components.

Pages:
- login and logout
- company search
- company overview:
  - identifiers and name history
  - a point-in-time risk view with an as_of date control
  - score history chart, top SHAP contributors
  - a permanent model-limitations banner taken from the model card
- event timeline:
  - tier badges (VERIFIED/CANDIDATE)
  - event_time versus known_at
  - evidence links
- document viewer:
  - opens via a signed URL
  - shows the page text with the cited character span highlighted
  - PDF rendering (pdf.js) where applicable
  - document text rendered escaped
- dossiers: list, detail with clickable citations to evidence, start an investigation with job status, export
- review queue (reviewer role): dossier and claim review with evidence spans, decisions with reason codes, audit visible to tenant_admin
- watchlists and alerts
- tenant admin: users and roles within the tenant, API keys (create, show once, revoke), webhooks

Also:
- Disclaimers on overview, dossier and score views: not investment advice; red flags are signals, not proof of misconduct or default.
- Security headers via the Next.js config or middleware: a strict CSP (no unsafe-inline scripts where avoidable), X-Content-Type-Options, frame-ancestors none, Referrer-Policy, HSTS when served over TLS.
- Basic accessibility: semantic HTML, labels, keyboard navigation.

## 5. DOCKER COMPOSE, CONFIG AND SECRETS

Compose services:
- postgres (pgvector), garage
- api
- worker (Dagster daemon and webserver)
- web

Requirements:
- healthchecks
- localhost-only ports
- non-root containers
- pinned base images
- a single bring-up command, documented for PowerShell

Configuration and secrets:
- Pydantic settings validation on startup, with a fail-fast check for weak or default secrets outside dev mode.
- .env.example is updated; no secrets in images or the repo.
- Document AWS Secrets Manager usage for production.

Seed command: creates TEST tenants and users (two tenants, every role) on localhost, so the isolation and UI tests use real flows.

## 6. PRODUCTION DEPLOYMENT CONFIGURATION (not applied)

- Write docs/deploy/aws-architecture.md. Keep it simple:
  - ECS Fargate (api, web, worker)
  - RDS Postgres with pgvector
  - S3
  - Secrets Manager
  - ALB with ACM TLS
  - CloudWatch logs and metrics
  - private subnets, least-privilege IAM, cost notes
- Add Terraform under infra/aws/. Validate it locally with terraform fmt/validate (and tflint if installable without sudo). Do NOT apply it: no credentials. State this plainly.

## 7. CI/CD (GitHub Actions — validated locally; no remote exists)

Workflows:
- backend: ruff, mypy, pytest with service containers
- frontend: eslint, tsc, unit tests, a Playwright e2e smoke test
- security: pip-audit, pnpm audit, gitleaks, trivy image scan
- build: images
- deploy: a smoke-test job, gated behind AWS credentials and environment approval, disabled until configured

Since there is no GitHub remote:
- validate the workflows with actionlint
- run every job's commands locally and report the results per job
- run them with act if feasible without sudo
- state clearly that GitHub-hosted execution is UNVERIFIED until the final push

## 8. OBSERVABILITY, BACKUP, RUNBOOKS

Observability:
- structured JSON logs with request ID and tenant ID (no secrets, no document text)
- a basic metrics endpoint (Prometheus format): request counts, latency histograms, error rates, job outcomes
- health and readiness checks

Backup and restore:
- pg_dump plus a Garage bucket sync
- PERFORM a restore drill into a fresh local stack, verify row counts and object hashes, and print the results

Runbooks (docs/ops/): startup and shutdown, secret rotation, key revocation, restore, incident response basics, rate-limit tuning, webhook failures.

## 9. SECURITY TESTS (required)

- An authorisation matrix test: every endpoint × every role, expected allow or deny.
- Cross-tenant isolation at both the DB level (RLS) and the API level, including IDOR attempts on watchlists, alerts, dossiers, review tasks, API keys and webhooks.
- Auth:
  - session fixation and rotation
  - CSRF rejection
  - lockout and backoff
  - API key hash-only storage and revocation
  - scope enforcement
- Signed URLs expire, and are refused for unauthorised documents.
- Webhooks:
  - signature verification vector
  - SSRF blocks for private, loopback, metadata and DNS-rebinding cases (re-resolution at send time)
- Rate limiting: 429 and Retry-After.
- Input validation and error-model checks; no stack traces leak.
- Prompt-injection separation: a document containing script or HTML or instruction text renders escaped in the UI. An investigation over it changes no behaviour (reuse the Phase 4 adversarial documents).
- Security headers are present.
- If feasible without sudo, run an OWASP ZAP baseline scan against the local stack and report the findings honestly.

Also:
- Playwright e2e tests against the real stack: log in, search, overview with as_of, timeline, open evidence with the highlighted span, start an investigation, view the dossier, review a task, create a watchlist and receive an alert. Plus a cross-tenant attempt that is denied.
- No placeholder tests.

## 10. DOCUMENTATION

- docs/api/ (the OpenAPI export plus a usage guide)
- docs/security/rbac.md, docs/security/threat-model.md, docs/security/controls.md
- docs/frontend/architecture.md
- docs/deploy/aws-architecture.md and docs/deploy/local-setup-windows.md
- docs/ops/*
- docs/adr/0008-api-auth-tenancy.md and docs/adr/0009-frontend.md
- release-gates.md: add "GitHub Actions runs verified green after the first push" and "Terraform plan reviewed before any apply"
- README phase status
- docs/phase-5/phase-5-report.md
Keep progress.md current across sessions.

## 11. RUN AND VERIFY

Run, recording raw output:
1. backend lint, typecheck and tests
2. frontend lint, tsc and tests
3. Playwright e2e against the compose stack
4. migrations from empty
5. the RLS tests
6. the authorisation matrix
7. the security tests
8. pip-audit, pnpm audit and trivy
9. actionlint, plus per-job local runs
10. terraform fmt/validate
11. the restore drill
12. a ZAP baseline, if run
13. pre-commit run --all-files
14. a full-history gitleaks scan

Also include screenshots or Playwright traces of the key pages, saved under docs/phase-5/evidence/ (small images only).

## 12. COMMIT (LOCAL ONLY) AND BACKUP

Commits:
- "phase-5:" prefixed messages, using the existing identity. Do not change git config.
- ABSOLUTE RESTRICTION: do not add Claude, Claude Code, Anthropic or any AI agent as contributor, collaborator, co-author, GitHub App, bot or repository member. No Co-Authored-By trailer, no "Generated with" line, no AI attribution of any kind.
- Verify with: git log -n 10 --format='%H%n%an <%ae>%n%B---'

No remote, no push.

Backup:
- git bundle create ../ledgerlight-backups/ledgerlight-phase-5.bundle --all
- git bundle verify on it

## 13. EXIT GATES

1. Preflight evidence is printed and no stop condition was triggered.
2. Tenancy plus RLS is enforced with a non-superuser app role, proven at the DB and API levels.
3. Auth, sessions, CSRF, hashed API keys with scopes, and the RBAC matrix are enforced on every endpoint and tested.
4. All §3 endpoints work against real data, with point-in-time correctness. Credibility honestly returns insufficient data.
5. Signed URLs (5 minutes or less), webhooks (HMAC, SSRF-safe), rate limits and audit logs work and are tested.
6. The frontend is functional end to end on real data: tiers, limitations, disclaimers and highlighted evidence spans shown; Playwright passes.
7. Prompt-injection and escaping are proven. Security headers are present.
8. Docker Compose starts everything with one command from PowerShell. Config validation fails fast on weak secrets.
9. Terraform is validated (not applied). The AWS architecture is documented.
10. Workflows are actionlint-clean and every job's commands pass locally. GitHub execution is marked UNVERIFIED.
11. The restore drill passed. Observability and runbooks are in place.
12. All tests and scans pass, or each finding is triaged with a justification. The secret scan is clean. The docs match the implementation.
13. Committed locally with no AI attribution. The bundle is verified. Nothing pushed.

## 14. FINAL REPORT

Print in full, and save to docs/phase-5/phase-5-report.md:
1. Summary
2. Files changed
3. Commands run
4. Raw preflight output (VERBATIM Phase 3/4 sections, the verifier-fix audit, the review routing counts)
5. Raw test and scan results
6. The authorisation matrix results
7. The RLS and cross-tenant results
8. The Playwright results with screenshot paths
9. Dependency and container scan triage
10. actionlint and per-job local results
11. Terraform validate output
12. Restore drill output
13. Security notes and the threat model summary
14. Limitations and defects
15. Decisions needing my approval
16. Git SHAs, identity, the trailer check, and the bundle verify output
17. Exit-gate checklist with evidence

Paste raw command output wherever evidence is cited; summaries alone are not evidence.

Continue across sessions via progress.md until complete or genuinely blocked. Stop after Phase 5. Do not begin Phase 6.
