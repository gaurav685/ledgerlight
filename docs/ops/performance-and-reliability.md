# Performance and Reliability (Phase 6A §8)

## Host specification

AMD Ryzen 7 6800H (8 cores / 16 logical processors), ~15.2GB total
RAM, Windows 11 Home 64-bit, Docker Desktop (WSL2 backend). This
host's free memory has been repeatedly, genuinely unstable throughout
this phase's own work (from the user's other applications, not this
project's stack) -- every test below was run at small scale with that
constraint in mind, consistent with the brief's own "within host
limits" framing.

## API load test

Tool: `locust` (added as a dev dependency this phase), via
`loadtest/locustfile.py` -- 5 concurrent simulated users, one real
shared login (not per-user, to respect the real 10/minute login rate
limit), hitting the real key read endpoints: company search, company
detail, company events, company timeline, company score, watchlists,
alerts. 60-second run, real local stack (`docker compose`).

```
uv run locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 \
    --users 5 --spawn-rate 1 --run-time 60s --headless \
    --csv docs/phase-6/evidence/sec08-loadtest
```

Raw output: `docs/phase-6/evidence/sec08-loadtest-run.log`;
`docs/phase-6/evidence/sec08-loadtest_stats.csv` and
`sec08-loadtest_stats_history.csv` for the full locust CSV export.

**Result (228 requests, 0 failures):**

| endpoint | p50 (ms) | p95 (ms) | p99 (ms) | requests |
|---|---|---|---|---|
| `/v1/companies/search` | 24 | 35 | 40 | 35 |
| `/v1/companies/{id}` | 19 | 33 | 41 | 54 |
| `/v1/companies/{id}/events` | 21 | 30 | 32 | 31 |
| `/v1/companies/{id}/scores` | 20 | 37 | 93 | 32 |
| `/v1/companies/{id}/timeline` | 24 | 39 | 43 | 39 |
| `/v1/watchlists` | 18 | 41 | 59 | 21 |
| `/v1/alerts` | 23 | 32 | 120 | 15 |
| **aggregated** | **21** | **37** | **93** | **228** |

Error rate: **0%** (0/228). Aggregate throughput: **3.87 req/s** at 5
concurrent users (real, not extrapolated -- this is a small-scale test
by design, not a production capacity claim).

**Two real findings while building this test** (both fixed in the
test, neither a bug in the API):
- `/v1/companies/{id}/scores` correctly 404s when no real score exists
  at or before the requested `as_of` -- the test's first attempt used
  a date before the sample company's only real score and got a 100%
  failure rate on that endpoint until the date was corrected. Documented,
  intentional API behavior (`ledgerlight/api/routers/companies.py`'s
  own `get_company_score`), not a defect.
- `/v1/watchlists` and `/v1/alerts` correctly 403 for the `viewer` role
  (it genuinely lacks `MANAGE_OWN_WATCHLISTS`, by design -- see
  `ledgerlight/api/rbac.py`'s `ROLE_PERMISSIONS`). Fixed by logging in
  as `analyst` instead.
- The real login endpoint (`POST /v1/auth/login`) took 1118ms on a
  cold run and 153ms on a warm one -- real bcrypt password-hashing
  cost, not a bug; read endpoints are 15-93ms by comparison.

## Ingestion and processing throughput

`scripts/measure_processing_throughput.py` -- real measurement, two
parts:

1. **PDF page extraction**, timed directly against 20 real,
   already-downloaded PDFs from `data/raw/` (no DB writes, so no
   idempotent-skip distortion): **209 real pages in 2.39s** →
   **501.9 documents/minute, 5244.7 pages/minute**.
2. **Full per-stage pipeline**, timed against 5 fresh real synthetic
   documents through the real `import-local` → `store-backfill` →
   page-extraction → chunking chain:

| stage | documents | wall time | documents/minute |
|---|---|---|---|
| import-local | 5 | 0.14s | 2142.9 |
| storage (backfill) | 5 | 0.55s | 548.4 |
| page extraction | 5 | 25.59s | **11.7** |
| chunking | 5 | 0.12s | 2400.0 |

Raw output: `docs/phase-6/evidence/sec08-throughput.log`.

**Real finding, disclosed**: page extraction in the full pipeline
(~5.1s/document) is far slower than the same stage measured standalone
against real PDFs (0.12s/document average in part 1). The standalone
measurement calls `extract_pdf_pages` directly and repeatedly in one
process (model/library state already warm after the first call);
`process_version` inside the full pipeline appears to pay a real,
one-time initialization cost on a cold path. Not root-caused further
here -- flagged as a real, measured observation for whoever tunes this
path next, not papered over.

## Agent runtime (from agent-eval)

From the real 60-investigation `agent-eval` run
(`docs/phase-4/phase-4-report.md` §6, reproduced verbatim in
`docs/phase-6/orchestrator-evidence.md`):

```
Runtime seconds: p50=0.08 p95=9.05
Tool calls: p50=5.0 p95=5.0
LLM tokens: p50=0.0 p95=0.0
Cost USD: p50=0.0000 p95=0.0000
```

LLM tokens/cost are genuinely 0 because this project's agent uses the
offline template renderer (`docs/modelling/model-card.md`'s own
documented "Intended use"), not a live LLM call -- not a measurement
gap.

## Failure-recovery drills

See `docs/ops/failure-recovery-drills.md` for all 5 drills (worker
kill mid-ingestion, Postgres restart during traffic, Garage
unavailable, agent crash mid-run, expired session/revoked API key),
each with real before/after evidence.
