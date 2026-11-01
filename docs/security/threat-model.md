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

- No OWASP ZAP baseline scan has been run yet (§9, planned).
- No Playwright e2e security suite yet (§9, planned) -- the
  authorization-matrix/cross-tenant/CSRF/SSRF proofs above are all
  unit/integration-level (`pytest -m integration`) against the real
  API, not yet driven through a real browser against the real
  frontend (§4, not yet built).
- Rate limiting has no IP-reputation or CAPTCHA layer; it is a real,
  working backstop, not a complete anti-abuse system.
- No WAF or network-layer DDoS protection is modeled -- out of scope
  for a local-dev/self-hosted deployment; `docs/deploy/aws-architecture.md`
  (§6, planned) will note where that would sit in a real AWS deployment.
