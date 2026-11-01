# Ledgerlight security controls catalog

Phase 5 §10. The real control inventory matching
`docs/security/threat-model.md` -- every row names the real
implementing code and its real test coverage; nothing here is
aspirational.

## Identity and access management

| Control | Implementation | Tests |
|---|---|---|
| Password hashing (argon2id) | `ledgerlight.api.auth.hash_password`/`verify_password` | `tests/test_api_auth.py` |
| Server-side sessions, Postgres-backed | `ledgerlight.api.auth.create_session`/`validate_session` | `tests/test_api_auth.py` |
| Session rotation on re-authentication | `ledgerlight.api.auth.rotate_session` | `tests/test_api_auth.py` |
| Session revocation (logout) | `ledgerlight.api.auth.revoke_session` | `tests/test_api_app.py` |
| CSRF protection (cookie-auth mutations) | `ledgerlight.api.deps.require_csrf`, constant-time compare | `tests/test_api_app.py` |
| Login lockout (5 failed attempts / 15 min, per tenant+email) | `ledgerlight.api.auth.check_lockout`/`record_login_attempt` | `tests/test_api_auth.py` |
| API keys: shown once, hashed at rest, prefix-indexed, scoped, revocable, expirable | `ledgerlight.api.api_keys` | `tests/test_api_api_keys.py`, `tests/test_api_api_keys_router.py` |
| RBAC: 4 roles x 13 permissions, enforced server-side on every endpoint | `ledgerlight.api.rbac`, `docs/security/rbac.md` | every `tests/test_api_*.py` file |

## Tenancy isolation

| Control | Implementation | Tests |
|---|---|---|
| Postgres Row-Level Security on every tenant-owned table | migration `4dad2cd00443` | `tests/test_api_rls.py` |
| Non-superuser, non-owner, no-BYPASSRLS app DB role | `ledgerlight_app` (same migration) | `tests/test_api_rls.py` |
| Per-request tenant context (`set_config`, transaction-scoped) | `ledgerlight.api.tenancy.tenant_scope` | every `tests/test_api_*.py` file |
| RLS-bootstrapping-safe identity resolution (token carries its own real tenant_id routing segment) | `ledgerlight.api.auth.extract_tenant_id_from_session_token`, `ledgerlight.api.api_keys.extract_tenant_id_from_api_key`, `ledgerlight.api.deps._resolve_identity` | `tests/test_api_auth.py`, `tests/test_api_api_keys.py` |
| Transitive isolation for tables with no `tenant_id` column (`dossiers`, `claims`, `review_tasks`) | RLS-gated fetch of the owning `Investigation` first | `tests/test_api_dossiers.py`, `tests/test_api_review.py` |
| "Own" vs "all" resource ownership within one tenant | `routers.watchlists.get_owned_watchlist` | `tests/test_api_watchlists_alerts.py` |

## Data protection

| Control | Implementation | Tests |
|---|---|---|
| Webhook secrets encrypted at rest (Fernet) | `ledgerlight.api.webhooks.encrypt_secret`/`decrypt_secret` | `tests/test_api_webhooks.py` |
| Webhook delivery signing (HMAC-SHA256, timestamp-bound) | `ledgerlight.api.webhooks.sign_payload`/`verify_signature` | `tests/test_api_webhooks.py` |
| SSRF protection, re-checked at every delivery attempt | `ledgerlight.api.webhooks.validate_webhook_url` | `tests/test_api_webhooks.py` |
| Signed document links, 5-minute TTL cap, never a public bucket | `ledgerlight.api.documents.issue_signed_url` | `tests/test_api_documents.py` |
| No portfolio/watchlist/credential/tenant data ever sent to an LLM | Phase 4's own ground rules, unchanged in §3 | Phase 4 adversarial test suite |

## API hardening

| Control | Implementation | Tests |
|---|---|---|
| Consistent error model, no leaked stack traces | `ledgerlight.api.app.create_app`'s exception handlers | `tests/test_api_app.py` |
| Request ID on every request/response/log line/audit row | `ledgerlight.api.app`'s request-ID middleware | `tests/test_api_app.py` |
| Security headers (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy) | `ledgerlight.api.app`'s security-headers middleware | manual `curl -I` verification; automated in §9 |
| Rate limiting (per-IP login; general per-scope primitive) | `ledgerlight.api.rate_limit.check_and_increment` | `tests/test_api_rate_limit.py` |
| Input validation (Pydantic schemas on every request body) | `ledgerlight.api.schemas` | every `tests/test_api_*.py` file |
| Append-only audit log covering auth events, key/webhook lifecycle, review decisions, investigation creation, document-link issuance, user/role changes | `ledgerlight.api.audit.write_audit_log` | every `tests/test_api_*.py` file that asserts an audit row |

## Point-in-time and evidentiary integrity (carried from Phase 1-4, exposed via §3)

| Control | Implementation | Tests |
|---|---|---|
| `known_at <= as_of` enforced at the query level, never a display filter | `ledgerlight.agent.tools` (reused directly by `routers.companies`) | Phase 4's own test suite; `tests/test_api_companies.py` |
| Every claim traces to a real evidence span in immutable `document_pages.raw_text` | Phase 4 §2/§5 | Phase 4's own test suite |
| Document/tool content is untrusted data, never an instruction | `ToolEnvelope(untrusted=True)` | Phase 4's adversarial test suite |

## Known limitations (see `docs/security/threat-model.md`'s own "Known, disclosed gaps")

No ZAP baseline scan, no Playwright e2e security suite, no WAF/CAPTCHA
layer yet -- all tracked as not-yet-started §9/§4 work in
`docs/phase-5/progress.md`.
