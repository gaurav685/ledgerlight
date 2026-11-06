# Ledgerlight threat model

Phase 5 §10. Describes the real system as built through §3/§9 --
every mitigation named here is implemented and tested code, not a
plan; `docs/security/controls.md` is the matching control catalog
with file-level pointers.

## Assets

- **Tenant data**: watchlists, alert rules, alerts, API keys,
  webhooks, user accounts, audit logs -- real, per-tenant rows in
  Postgres, isolated by Row-Level Security.
- **Public reference data**: companies, documents, events, scores,
  dossiers -- global, read-only to every tenant, no isolation needed
  (there is nothing tenant-specific in it).
- **Credentials**: user passwords (argon2id hashes), session tokens
  (hashed), API keys (hashed, prefix-indexed), webhook signing
  secrets (Fernet-encrypted at rest).
- **The model/agent pipeline's own integrity**: the risk score, SHAP
  values, and every dossier claim's evidentiary chain back to
  `document_pages.raw_text`.

## Actors and trust boundaries

- **An authenticated tenant user** (cookie or API key) -- trusted
  only within its own tenant and its own role's permission set
  (`docs/security/rbac.md`). Every endpoint enforces this server-side
  (`ledgerlight.api.rbac.require_permission`); the frontend's own
  checks are UX only, never the real boundary.
- **A different tenant** -- the real adversary the whole §2 RLS
  design exists to stop. Modeled and tested directly (every router's
  own test suite proves cross-tenant access 404s, never 403s that
  would confirm existence).
- **An unauthenticated caller** -- gets `401` from every real
  endpoint except `/healthz`.
- **A malicious or compromised webhook endpoint** -- cannot reach
  internal infrastructure (SSRF-blocked) and cannot forge deliveries
  it didn't receive (HMAC-signed).
- **A malicious document** -- ingested content (filings, orders) is
  real external, untrusted text. It is rendered escaped everywhere
  and never executed, interpreted as an instruction, or given special
  trust by the investigation agent (Phase 4's own ground rule, carried
  into §3's dossier/document-viewer endpoints unchanged).

## Threats and mitigations

| Threat | Mitigation | Where |
|---|---|---|
| Tenant A reads/writes Tenant B's rows | Postgres RLS on every tenant-owned table, enforced for the restricted `ledgerlight_app` role (no BYPASSRLS) | migration `4dad2cd00443`; `tests/test_api_rls.py` |
| A review task / dossier / investigation leaks across tenants via a table with no `tenant_id` column of its own | RLS-gated fetch of the owning `Investigation` FIRST, before trusting its id to query `Dossier`/`Claim`/`ReviewTask` | `routers/dossiers.py`, `routers/review.py` |
| Stolen session cookie replayed after logout | Server-side session revocation (`sessions.revoked_at`); rotation on privilege-sensitive events creates a new token, kills the old one | `ledgerlight.api.auth.revoke_session`/`rotate_session` |
| CSRF on a cookie-authenticated mutation | `X-CSRF-Token` required and checked with constant-time comparison; never required for bearer-token (API key) auth, which carries no real CSRF risk | `ledgerlight.api.deps.require_csrf` |
| Credential-stuffing / brute-force login | Per-(tenant, email) lockout after 5 failed attempts in 15 minutes; per-IP rate limiting on `/v1/auth/login` | `ledgerlight.api.auth.check_lockout`; `ledgerlight.api.rate_limit` |
| A stolen API key used after revocation | `revoked_at`/`expires_at` checked on every real verification; never cached | `ledgerlight.api.api_keys.verify_api_key` |
| SSRF via a registered webhook URL (incl. cloud metadata endpoints) | Real DNS resolution + block of private/loopback/link-local/multicast/reserved/unspecified addresses, re-checked immediately before **every** delivery attempt (never only at registration) -- closes the DNS-rebinding window a registration-time-only check would leave open | `ledgerlight.api.webhooks.validate_webhook_url`/`deliver_webhook` |
| A forged webhook delivery claimed as genuine | HMAC-SHA256 over `{timestamp}.{payload}`, verified with `hmac.compare_digest` | `ledgerlight.api.webhooks.sign_payload`/`verify_signature` |
| A signed document link shared/leaked | Presigned GET URL capped at 5 minutes server-side (never trusting boto3's own larger default ceiling); never a public bucket | `ledgerlight.api.documents.issue_signed_url` |
| A malicious document's content treated as an instruction by the investigation agent | Documents are UNTRUSTED DATA by the agent's own ground rules (Phase 4); every tool's output is wrapped in `ToolEnvelope(untrusted=True)`; the frontend renders evidence text escaped | `ledgerlight.agent.tools.ToolEnvelope`; §4 frontend (planned) |
| A wrong-dated or fabricated claim reaching a finalised dossier | The real verifier (`ledgerlight.agent.verifier`) checks every claim's evidence span and known_at against its source before FINALISE; routes to NEEDS_REVIEW otherwise | Phase 4 §5; `docs/phase-5/evidence/sec01-preflight-verbatim-and-audits.md` |
| An endpoint leaking a real stack trace or internal detail on error | A single, consistent error model; the catch-all 500 handler logs server-side (with request_id) and returns only a generic message | `ledgerlight.api.app.create_app`'s exception handlers |
| A client flooding the API | Per-scope rate limiting via `ledgerlight.api.rate_limit`, real `429` + `Retry-After`. **Known limitation**: Postgres-backed, correct across multiple API instances, but adds one real DB round-trip per limited call -- see `docs/adr/0010-rate-limiting.md` |
| Clickjacking / MIME-sniffing / referrer leakage | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, a restrictive `Content-Security-Policy` on every response | `ledgerlight.api.app`'s security-headers middleware |

## Known, disclosed gaps (not yet mitigated -- tracked for later phases)

- Rate limiting has no IP-reputation or CAPTCHA layer; it is a real,
  working backstop, not a complete anti-abuse system.
- No WAF or network-layer DDoS protection is modeled -- out of scope
  for a local-dev/self-hosted deployment; `docs/deploy/aws-architecture.md`
  notes where that would sit in a real AWS deployment.

## Residual risks (Phase 6A §9)

- **Frontend CSP `script-src` includes `'unsafe-inline'`.** A real,
  significant bug was found while building the first real
  interactive Playwright e2e test (Phase 6A §2): a strict
  `script-src 'self'` with no exception blocks Next.js's own required
  inline hydration scripts outright, so React never hydrated on any
  page in any real CSP-enforcing browser -- confirmed directly (every
  form, login included, silently fell back to a native, unintercepted
  HTML GET submission with real credentials in the URL). The
  documented Next.js per-request-nonce fix was implemented and tested
  directly; it did not work in this exact Next.js 16.4.3 App Router
  setup (the CSP header correctly carried a nonce, but Next's own
  inline scripts never received the matching `nonce` attribute,
  confirmed by inspecting the raw response HTML). The real,
  pragmatic fix deployed instead is `'unsafe-inline'` with no nonce
  source present. **Residual risk**: any future XSS injection point
  elsewhere in this app could execute an injected inline script under
  this policy. Mitigating factors already in place: no
  `dangerouslySetInnerHTML` anywhere in this codebase (confirmed by
  `tests/test_prompt_injection_separation.py`'s own repo-wide check,
  re-confirmed this phase), and no raw HTML from any ingested
  document is ever rendered as markup, only as auto-escaped JSX text.
  Full writeup: `docs/phase-6/evidence/sec02-csp-hydration-bug.md`.
  Getting the strict, nonce-based policy actually working is real,
  disclosed future work (`docs/release/release-gates.md`).

- **Deployed Docker images lag their own fixed dependencies.**
  `pip-audit` found 24 real vulnerabilities across `cryptography`,
  `fastapi`, and `starlette` in this phase's own re-validation.
  `cryptography`/`fastapi` were bumped straightforwardly; `starlette`
  needed a deeper investigation -- `fastapi`'s own dependency range
  caps it below `0.51.0` (no 0.x fix exists for several of these CVEs,
  only from `starlette` 1.0.1 onward), so `fastapi` itself had to be
  bumped to its latest release (0.162.0, the first compatible with
  `starlette` 1.x) to get a real fix. `pytest` was bumped similarly.
  All three bumps were verified safe: the full default suite (408
  tests) and the full integration suite (330 tests, run in
  memory-safe batches) both pass clean after each bump, including a
  real regression this bump exposed and fixed (see the next entry).
  `pip-audit --local` now reports **0 known vulnerabilities**. **The
  residual risk**: the real running Docker images
  (`ledgerlight-phase0-api`, `ledgerlight-phase0-web`) were built
  *before* this dependency bump, so a fresh `trivy image` scan against
  them still shows the old, vulnerable `cryptography`/`starlette`
  versions (`docs/phase-6/evidence/sec09-trivy-api-before-rebuild.log`)
  -- the fix exists in `pyproject.toml`/`uv.lock` but has not yet been
  baked into a rebuilt image. Rebuilding both images was attempted
  twice and killed both times by this host's own real, severe memory
  pressure (same documented pattern as Phase 6A §2's CSP-fix rebuild
  struggles) -- marked **BLOCKED**, not silently skipped; rebuilding
  and re-scanning is the immediate next step once host memory allows.

- **Found and fixed a real, previously-undiscovered bug while
  verifying the dependency bump above**: `POST /v1/dossiers/
  investigations` creates a real `Investigation` row, then schedules a
  `BackgroundTasks` callback that opens its own separate session to
  resume and run it. The endpoint only `flush()`ed the row, relying on
  `get_db`'s own post-`yield` commit happening before Starlette runs
  queued background tasks -- true on the old `starlette` 0.48.0, but
  the relative order flipped on the upgraded version, so the
  background task's own fresh session could no longer find the row
  ("`resume_investigation_id` does not exist"), reproducibly failing
  every real investigation created through the API. Fixed with an
  explicit `db.commit()` before scheduling the task -- correct and
  robust regardless of framework internals, not a reliance on
  undocumented ordering. Confirmed: fails on the old dependency set
  with the fix removed is moot (the bug only manifests with the new
  ordering); confirmed fixed and passing (4/4) on the upgraded set
  with the fix applied, and the full default+integration suites stay
  green. Full writeup: `docs/phase-6/progress.md` §9.

- **Real, currently un-patchable OS-package findings** (both images,
  `trivy image --severity HIGH,CRITICAL`): `util-linux`/`ncurses`/
  `perl-base` CVEs with no Debian fix yet (`status: affected` or
  `fix_deferred` -- nothing this project can do beyond waiting for an
  upstream patch and rebuilding when one ships); `zlib1g`
  CVE-2023-45853 (CRITICAL, `status: will_not_fix` by Debian upstream)
  -- the same finding already disclosed in Phase 5, unchanged. The
  `web` image additionally carries a real, currently-unpatched
  `undici` CVE set (3 HIGH, fixed in `undici` 6.29.1+) -- `undici`
  here is Node.js's own bundled global-fetch implementation, not an
  npm dependency this project installs, so fixing it requires a newer
  Node.js base-image tag, not a `pnpm` bump; tracked alongside the
  rebuild above.

- **`pnpm audit`: 1 real, accepted, dev-only finding.** `minimatch`
  (moderate, DoS via glob-amplification) via `eslint-config-next`'s
  own transitive chain -- a lint-time tool dependency, never shipped
  to a real user, and already at the newest version resolvable within
  the current `eslint`/`typescript-eslint` constraint set. Same
  finding and disposition as Phase 5's own triage, re-confirmed
  unchanged this phase.
