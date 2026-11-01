# ADR 0010: Rate Limiting (Phase 5 §3)

## Status
Accepted (Phase 5).

## Context
The brief requires real rate limiting per user, per API key, and per
IP, with a real 429 + `Retry-After` response, and explicitly asks for
the implementation choice (Postgres-backed vs. in-process) to be
documented along with whatever real limitation it carries.

## Decision
**Postgres-backed**, via a real, atomic fixed-window counter table
(`rate_limit_counters`, migration `780f44fe5dbc`) and one real UPSERT
(`ledgerlight.api.rate_limit.check_and_increment`).

### Why not in-process (e.g. a plain dict or `token_bucket` library in
memory)

An in-process counter is correct only for a single real process. The
real AWS architecture this project documents
(`docs/deploy/aws-architecture.md`) runs the API on ECS Fargate,
which means more than one real task/instance under normal operation
(for both throughput and availability) -- an in-process counter on
each instance would let a real client get `N × (number of instances)`
requests through before any single instance's own counter trips,
silently defeating the real limit the brief asks for. This is exactly
the "multi-instance limitation" the brief asks to have stated if that
path were chosen instead.

### The real cost of the Postgres-backed choice

Every rate-limited request pays one real extra database round trip
(the UPSERT itself). At very high request rates this adds real load
to the same database every other real query already uses, and real
latency to every rate-limited request. Accepted: this project's real
traffic is not latency-sensitive at that scale, and correctness across
instances matters more here than shaving one round trip.

### Why the counter's own transaction is independent of the request's

`check_and_increment` opens its own, separate connection and commits
immediately -- confirmed directly while building it that calling
`.commit()` on the shared per-request session would have prematurely
committed everything else that request had done so far (the same real
class of bug this project has hit before with a shared, externally-managed
transaction). A rate-limit increment must also count a real attempt
regardless of whether the rest of the request later fails and rolls
back -- otherwise a client could probe indefinitely via requests that
fail for an unrelated reason, never actually tripping the real limit.

## Consequences
- Real, atomic, race-free under concurrent requests (Postgres's own
  `ON CONFLICT DO UPDATE` guarantee) -- proven directly
  (`tests/test_api_rate_limit.py`), not merely assumed.
- `rate_limit_counters` grows by one real row per distinct real key
  (user/API key/IP) ever rate-limited; no automatic cleanup is built
  in Phase 5 -- a real, disclosed, minor operational gap (a stale row
  for a key nobody has used in months costs one small row, not
  unbounded growth, since each key maps to at most one row regardless
  of how many requests it has made).
