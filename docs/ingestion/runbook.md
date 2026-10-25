# Ingestion Runbook (Phase 1)

## Prerequisites
- Local infra up: `make infra-up` (Postgres + Garage, see
  `infra/docker-compose.yml`).
- `.env` populated (see `.env.example`); `make verify-env`.
- Application schema migrated: `make db-upgrade`.
- `sources` table synced from `data/manifests/sources.yaml`:
  `make sources-sync`.
- Persistent raw-object bucket/key provisioned (one-time):
  `uv run python scripts/garage_provision.py`.
- Dagster's own database created (one-time):
  `uv run python scripts/dagster_db_setup.py`.

`dagster_home/dagster.yaml` reads `LEDGERLIGHT_POSTGRES_*` from the
**process environment**, not from `.env` directly — every Dagster-facing
Make target (`ingest`, `dagster-dev`) loads `.env` into the shell first
(see the `DAGSTER_ENV` variable in the `Makefile`).

## One-time historical backfill

Phase 0/Correction 1's seed only sampled bhavcopy twice a month. The
Phase 1 backfill fills in every business day for a real range:

```sh
make backfill START=2019-01-01 END=2019-12-31
```

This calls `ledgerlight.ingestion.nse_bhavcopy.run_bhavcopy_range`
directly (bypassing Dagster's per-partition run overhead, which would
dominate for a multi-hundred-day range) and prints measured throughput.
Re-running the same range is a no-op for already-fetched dates (hash
dedup) — safe to re-run after an interruption.

For the full available range (2017-01-01 onward), estimate duration from
the measured per-request rate (`rate_limit_seconds` + network latency);
the 2019 backfill (261 business days) took ~521s (~0.5 req/s) — a full
~9-year range (≈2,250 business days) would take on the order of 2-3
hours. Run it in the background and check `make ingest-report` /
`price_bars` row counts for progress.

## Day-to-day ingestion

Via Dagster (records a real run, retries on failure via `RetryPolicy`):

```sh
make ingest SOURCE=sebi
make ingest SOURCE=nse_archives DATE=2025-09-01
make ingest SOURCE=inbox
```

Or let the schedule/sensor do it: `make dagster-dev` starts the Dagster
webserver (`http://localhost:3000`) with the daily bhavcopy schedule and
inbox sensor both defined and toggleable from the UI.

## Processing

```sh
make process
```

Runs `ledgerlight.processing.batch.run_process_all` over every
`DocumentVersion` on record: PDF/HTML text extraction (with OCR fallback)
and bhavcopy CSV → `price_bars` loading. Idempotent — already-processed
pages/rows are skipped (reported as `pages_already_present` /
`rows_unchanged`), never duplicated.

## Reprocessing

```sh
make reprocess VERSION=<document_version uuid>
```

Forces a single version back through processing — used after fixing a
dead-lettered item, or to prove the determinism guarantee: re-running
with the same `extractor_version` produces byte-identical output
(reported as already-present, not newly created); bumping
`extractor_version` in code and reprocessing creates new rows while the
old `extractor_version`'s rows are left untouched.

## Observability

```sh
make ingest-report
```

Prints per-source status (enabled/last run/last run status/document
count/last run's failure count), dead-letter counts by stage, and
processing-attempt failure counts by error class.

End-to-end proof of the retry → dead-letter → reprocess path:

```sh
uv run python scripts/dead_letter_demo.py
```

## Tests

```sh
make test                 # unit only (default; fast, no external deps)
make test-integration      # requires the Docker stack up
make test-corpus           # requires data/raw/ populated (real downloads)
```

## Troubleshooting

- **`DagsterInvalidDefinitionError: Cannot annotate context parameter...`**
  — see ADR 0004 §1. Don't re-introduce
  `from __future__ import annotations` in `ledgerlight/orchestration/
  definitions.py`, and don't annotate a `context` parameter via the `dg.`
  alias.
- **`psycopg.errors.SyntaxError: syntax error at or near "$1"` from a
  Dagster run** — `dagster_home/dagster.yaml` is missing `scheme:
  postgresql+psycopg2` on a storage block; see ADR 0004 §2.
- **A source won't schedule** (`SourceNotSchedulableError`) — check its
  verdict in `data/manifests/sources.yaml`; only `AVAILABLE` and
  `AVAILABLE_WITH_LIMITS` sources are ever enabled, enforced by
  `ledgerlight.ingestion.base.require_enabled_source` and proven in
  `tests/test_sources_unschedulable.py`.
