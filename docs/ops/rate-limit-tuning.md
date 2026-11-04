# Rate-limit tuning

Phase 5 §8. The real rate-limiting primitive
(`ledgerlight.api.rate_limit.check_and_increment`,
`docs/adr/0010-rate-limiting.md`) and where it is actually wired in
today.

## What's real today

Only one real call site exists: `POST /v1/auth/login`
(`ledgerlight/api/routers/auth.py`), per client IP:

```python
LOGIN_RATE_LIMIT_PER_WINDOW = 10
LOGIN_RATE_LIMIT_WINDOW = dt.timedelta(minutes=1)
```

Separately, `ledgerlight.api.auth.check_lockout` enforces a real
per-(tenant, email) lockout -- 5 failed attempts within 15 minutes
(`LOGIN_LOCKOUT_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_WINDOW`), tracked via
`audit_logs`, independent of the IP-based limit above. Both exist
together on purpose: the IP limit stops one source hammering many
accounts; the lockout stops one account being hammered from many
sources.

A rate-limited request gets a real 429 with a real `Retry-After`
header (`ledgerlight.api.rate_limit.RateLimitExceeded`, handled in
`ledgerlight.api.app`'s own exception handler) -- never a silent drop.

## How to retune

Both constants above are plain module-level values, not environment
variables -- change them in code, test, redeploy. There is
deliberately no runtime-configurable rate limit yet; if ops needs to
retune without a deploy, that is real future work, not something to
work around by editing the database directly.

`check_and_increment` itself is scope-agnostic (`key` is any string
the caller builds), so adding a new real limit anywhere else in the
API is: pick a `key` pattern (e.g. `f"api_key:{key_id}"`,
`f"user:{user_id}:some-action"`), pick a `limit`/`window`, call it
inside the route before doing anything else. See `docs/adr/
0010-rate-limiting.md` for why this is Postgres-backed (atomic across
multiple real API process instances) rather than in-process, and the
real latency cost that choice carries (one extra DB round-trip per
checked request).

## Diagnosing "legitimate users getting 429'd"

1. Check `GET /metrics` for the real `status_code="429"` series on
   `ledgerlight_http_requests_total` -- confirms real volume and which
   route.
2. For login specifically: a shared corporate NAT/proxy can put many
   real users behind one IP, hitting the per-IP limit from legitimate
   traffic. The current limit (10/minute/IP) does not distinguish
   this from a real credential-stuffing attempt -- raising
   `LOGIN_RATE_LIMIT_PER_WINDOW` is the direct fix if this is
   confirmed, at the real cost of a slower brake on an actual attack
   from that same IP.
3. Check `rate_limit_counters` directly for the specific key in
   question to see its real current count/window:
   ```sql
   SELECT * FROM rate_limit_counters WHERE key = 'login_ip:<the real ip>';
   ```

## Diagnosing "limit not stopping an actual attack"

Lower `LOGIN_RATE_LIMIT_PER_WINDOW` and/or
`LOGIN_LOCKOUT_MAX_ATTEMPTS`/shrink `LOGIN_LOCKOUT_WINDOW`. Check
`audit_logs` for the real pattern of failed-login events first
(tenant/email/IP/timing) before guessing at new values.
