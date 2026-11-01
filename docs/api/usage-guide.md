# Ledgerlight API -- usage guide

Phase 5 §3/§10. This is a guide to the real, running `/v1` API
(`ledgerlight.api.app.create_app()`); the machine-readable contract
itself is `docs/api/openapi.json`, exported by
`scripts/export_openapi.py` directly from the live app -- never
hand-written, so it can never drift from the real routes/schemas.
Regenerate it with:

```powershell
.venv\Scripts\python scripts\export_openapi.py
```

## Authentication

Two real, independent ways to authenticate, resolved in
`ledgerlight.api.deps._resolve_identity`:

1. **Session cookie** (browser/frontend use). `POST /v1/auth/login`
   with `{tenant_slug, email, password}` sets an httpOnly `ll_session`
   cookie and returns a `csrf_token` in the response body. Every
   subsequent cookie-authenticated **mutating** request (anything but
   a plain `GET`) must carry that token in an `X-CSRF-Token` header,
   or it is rejected with a real `403`.
2. **API key** (service-to-service use). `Authorization: Bearer
   <raw_key>`, from `POST /v1/api-keys` (`tenant_admin` only). No CSRF
   header is required for API-key auth -- a bearer token is never
   auto-attached by a browser, so there is no real CSRF risk to defend
   against for it.

Both token forms carry a real, non-secret `tenant_id` routing prefix
(see `docs/adr/0008-api-auth-tenancy.md`) -- required so the server
can set the real Postgres RLS tenant context *before* it can even
look up the token's own row, since `sessions`/`api_keys` are
themselves RLS-protected tables.

## Point-in-time correctness

Every endpoint under `/v1/companies/{company_id}/...` accepts an
`as_of` query parameter (`YYYY-MM-DD`, defaults to today). It is
never a display filter applied after the fact -- every real query
underneath (`ledgerlight.agent.tools.get_events`/`get_timeline`/
`get_risk_score`) filters on `known_at <= as_of` at the SQL level, so
a historical `as_of` genuinely reconstructs what was knowable at that
date, the same point-in-time discipline this project has enforced
since Phase 1.

## Real roles and permissions

Four roles (`viewer`, `analyst`, `reviewer`, `tenant_admin`); the full
permission matrix is `docs/security/rbac.md`. Two things worth
knowing going in:

- `analyst` can manage its **own** watchlists/alert rules only;
  `tenant_admin` can manage every watchlist in the tenant
  (`MANAGE_OWN_WATCHLISTS` vs `MANAGE_ALL_WATCHLISTS`). A watchlist
  belonging to a tenant-mate (not you) 404s for an `analyst` exactly
  like a genuinely unknown id -- never a `403`, which would itself
  confirm it exists.
- API keys, webhooks, and user/role management are all
  `tenant_admin`-only.

## Endpoint map

```
GET    /healthz                                          liveness only
GET    /readyz                                           real DB round-trip

POST   /v1/auth/login
POST   /v1/auth/logout                                    (CSRF-protected)
GET    /v1/auth/me

GET    /v1/companies/search?q=
GET    /v1/companies/{company_id}
GET    /v1/companies/{company_id}/events?as_of=&event_type_code=
GET    /v1/companies/{company_id}/timeline?as_of=
GET    /v1/companies/{company_id}/scores?as_of=
GET    /v1/companies/{company_id}/credibility?as_of=      always honest insufficient-data

POST   /v1/dossiers/investigations                         real async job (202)
GET    /v1/dossiers/investigations/{id}
GET    /v1/dossiers/investigations/{id}/dossier
GET    /v1/dossiers/investigations/{id}/export?fmt=markdown|json

GET    /v1/review/tasks
GET    /v1/review/tasks/{id}
POST   /v1/review/tasks/{id}/decision                       (reviewer/tenant_admin)

GET    /v1/watchlists                      POST   /v1/watchlists
DELETE /v1/watchlists/{id}
GET    /v1/watchlists/{id}/items           POST   /v1/watchlists/{id}/items
DELETE /v1/watchlists/{id}/items/{item_id}

GET    /v1/alerts/rules                    POST   /v1/alerts/rules
DELETE /v1/alerts/rules/{id}
GET    /v1/alerts                          POST   /v1/alerts/{id}/acknowledge

GET    /v1/api-keys                        POST   /v1/api-keys        (tenant_admin)
DELETE /v1/api-keys/{id}

GET    /v1/webhooks                        POST   /v1/webhooks        (tenant_admin)
DELETE /v1/webhooks/{id}
POST   /v1/webhooks/{id}/test
GET    /v1/webhooks/{id}/deliveries

GET    /v1/admin/users                     POST   /v1/admin/users     (tenant_admin)
PATCH  /v1/admin/users/{id}/role
DELETE /v1/admin/users/{id}
GET    /v1/admin/audit-log

GET    /v1/documents/{document_version_id}/signed-url       <=5 min TTL
```

## Error model

Every failure, from any endpoint, is one real, consistent shape:

```json
{"error": "<category>", "detail": "<message>", "request_id": "<uuid>"}
```

`error` is one of `http_error` (ordinary 4xx), `forbidden` (403, a
real RBAC denial), `rate_limited` (429, carries a real `Retry-After`
header), or `internal_error` (500 -- the real exception is logged
server-side with the same `request_id`, never shown to the caller).
Every response also carries an `X-Request-ID` header, echoing the
request's own id if the caller sent one.

## Rate limiting

Login attempts are rate-limited per client IP
(`ledgerlight.api.rate_limit`, Postgres-backed; see
`docs/adr/0010-rate-limiting.md` for the real multi-instance
limitation this choice carries). A `429` response always carries a
real `Retry-After` header in seconds.
