# Incident response

Phase 5 §8. A real first-response guide grounded in what this
codebase actually gives an operator to work with -- `docs/security/
threat-model.md` is the design-time document; this is what to DO when
something real goes wrong.

## First, find the request(s)

Every real response carries `X-Request-ID`, and every real log line
from that request carries the same `request_id` field (structured
JSON, `ledgerlight.common.logging`). Start every investigation there:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml logs api | findstr "<the request_id>"
```

An unhandled server error logs as `event: "unhandled_exception"` with
the real traceback inline (`ledgerlight.api.app._unhandled_exception_handler`)
-- the client only ever sees a generic 500, so the real cause is only
ever in this log line, never in anything a reporter can paste back to
you.

## Suspected compromised credential

- **API key**: `DELETE /v1/api-keys/{key_id}` (see `docs/ops/
  key-revocation.md`) -- effective on the key's very next use.
- **User account / session**: revoke the membership
  (`DELETE /v1/admin/users/{user_id}`) AND, for anything urgent, run
  the manual `DELETE FROM sessions WHERE user_id = ...` in
  `docs/ops/key-revocation.md` -- membership revocation alone is
  effective on the next request, but the raw session row otherwise
  lives until its own 12-hour expiry.
- Check `audit_logs` for that tenant for what the credential actually
  did before revocation: `GET /v1/admin/audit-log` (or query the
  table directly) -- every auth event, key/webhook lifecycle change,
  review decision, investigation creation, and document-link issuance
  is written there (`ledgerlight.api.audit.write_audit_log`).

## Suspected cross-tenant data exposure

This would be a Row-Level Security failure -- the single most
load-bearing control in this codebase
(`docs/security/controls.md`'s own tenancy-isolation section;
`tests/test_api_rls.py`). If ever suspected:

1. Do not assume it's isolated to one endpoint -- RLS is set once per
   request in `ledgerlight.api.deps.get_identity`
   (`tenant_scope`) and applies to every query on every tenant-owned
   table for the rest of that request. A real failure here is
   systemic, not per-route.
2. Confirm the `ledgerlight_app` role genuinely has no `BYPASSRLS`
   and is not the table owner (migration `4dad2cd00443`) --
   `tests/test_api_rls.py` already asserts this; re-run it directly
   against the real suspect environment if this is ever in doubt:
   `uv run pytest tests/test_api_rls.py -m integration -v`.
3. Pull the real audit trail for every tenant that might have been
   affected, by request_id and time window, from the structured logs.

## Elevated error rate / latency

`GET /metrics` (`ledgerlight.api.metrics`) exposes
`ledgerlight_http_requests_total{method,route,status_code}` and
`ledgerlight_http_request_duration_seconds{method,route}` -- scrape
this with Prometheus in any real deployment (never expose it past the
ALB -- internal only, `infra/aws/alb.tf`). Labels are by route
TEMPLATE, never raw path, so a spike on one specific endpoint pattern
is visible without per-ID cardinality explosion.

If the elevated rate traces to rate limiting (429s), see
`docs/ops/rate-limit-tuning.md`. If it traces to webhook delivery
failures surfacing as app-level errors, see `docs/ops/
webhook-failures.md`.

## Data correctness incident (wrong score, wrong claim, etc.)

This project's own evidentiary-integrity controls
(`docs/security/controls.md`'s last section) mean every claim traces
to a real, immutable `document_pages.raw_text` span, and every score
carries the model-limitations banner. A reported wrong result is
almost always either (a) a real `as_of`/`known_at` point-in-time
misunderstanding on the reporter's part, or (b) a real upstream data
problem -- not a security incident. Reproduce via the same `as_of`
the reporter used before assuming anything is broken.

## Before declaring resolved

- Confirm the real root cause via logs/metrics/audit trail, not a
  guess.
- Add a regression test if the cause was a code defect -- this
  project's own established pattern throughout Phase 5 (every real
  bug found this phase got one).
- If the incident involved real data, run `scripts/backup.py` once
  things are stable, and consider a `scripts/restore_drill.py` pass
  to confirm the backup is good (`docs/ops/restore.md`).
