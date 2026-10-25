# Phase 1 Report — Data Ingestion, Raw Storage and Document Processing

Scope: ingestion, raw storage, document processing, orchestration and
observability only. Event classification/extraction, entity resolution,
chunking/embeddings, features/models, API and frontend are explicitly
**not** part of this phase. Raw evidence for every claim below is saved
under `docs/phase-1/evidence/`.

## 1. Implementation summary

Phase 1 adds, on top of Phase 0's acquisition utility and 237-document
seed corpus:

- A relational metadata store (SQLAlchemy 2.x + Alembic + psycopg3) with
  8 application tables, every timestamp a UTC `timestamptz`, and a
  documented, tested `known_at` evidence rule
  (`docs/data/temporal-semantics.md`).
- A generic, content-addressed object-storage abstraction over Garage
  (`ledgerlight/storage/s3_store.py`) with a persistent bucket/key
  (`scripts/garage_provision.py`) and a proven-idempotent backfill of
  every Phase 0 manifest entry.
- Real ingestion jobs for every `AVAILABLE`/`AVAILABLE_WITH_LIMITS`
  source (NSE bhavcopy, SEBI, IBBI, CARE, 9 company IR sites, manual
  inbox), with hash dedup and full provenance, enforced unschedulable for
  every `BLOCKED`/`REQUIRES_PAYMENT_OR_LICENCE`/`UNCLEAR`/
  `AWAITING_KEY`/`REQUIRES_REGISTRATION` source.
- A real historical backfill extending bhavcopy coverage by a full
  calendar year (2019), plus a concrete survivorship-bias check
  (Jet Airways).
- Document processing: PDF (PyMuPDF, tested OCR-needed heuristic, RapidOCR
  fallback), HTML (BeautifulSoup, no JS execution), bhavcopy CSV/ZIP
  (Pydantic validation + quarantine), all behind tested safety limits
  (file size, page count, per-document timeout, ZIP-bomb/path-traversal
  rejection, content-based MIME sniffing).
- Dagster orchestration (one partitioned asset, 13 per-source ops, an
  inbox sensor, a daily schedule) with its own Postgres database,
  separate from the application schema — every job actually run, with
  real run IDs recorded.
- Observability: structured JSON logs, persisted per-run metrics
  (`ingestion_runs`), a working retry/dead-letter/reprocess mechanism, an
  `ingest-report` CLI, and a fixed error-classification taxonomy.
- 88 tests (80 unit + 6 integration + 2 corpus), all passing, including a
  committed synthetic fixture that proves the OCR path works end-to-end.

**Two real, non-obvious bugs were found and fixed** while building this
(a Dagster/PEP-563 context-annotation incompatibility, and a
dagster-postgres/psycopg3 `NOTIFY` incompatibility — see §9), plus **one
real correctness bug in this codebase's own ingestion code**, found and
fixed before it could do any lasting damage (§6).

## 2. Scope boundaries (explicitly not done)

- No event classification/extraction, entity resolution, chunking,
  embeddings, features, models, API endpoints, or frontend.
- XBRL parsing is deferred, not implemented: `ledgerlight/processing/xbrl.py`
  documents that no real, legitimately-obtainable XBRL files were found
  for this corpus (BSE/NSE XBRL endpoints are `BLOCKED` in
  `data/manifests/sources.yaml`) — never a parser tested only on invented
  data.
- The retry/dead-letter mechanism
  (`ledgerlight.ingestion.retry.run_with_attempt_tracking`) is proven
  correct end-to-end (test + CLI demo, §10), but is **not yet wired
  per-item into the live ingestion jobs** (`run_known_items_job`,
  `run_bhavcopy_range`) — those currently catch and record failures as
  job-level stats only. Dagster's own `RetryPolicy` (max 2 retries) is
  what actually re-executes a failed op; the durable
  `processing_attempts`/`dead_letters` audit trail is available and
  tested but only exercised by the dedicated demo today. Flagged
  honestly rather than claimed as fully wired.

## 3. Files created or modified

89 files changed (9,381 insertions, 402 deletions) — `git diff --cached
--stat` output saved at `docs/phase-1/evidence/` is reproducible via
`git show --stat <commit>` after committing (§12). New top-level areas:

```
ledgerlight/db/              models.py, session.py, temporal.py, migrations/
ledgerlight/storage/         s3_store.py, garage_admin.py
ledgerlight/ingestion/       base.py, upsert.py, retry.py, run_tracking.py,
                              sources_sync.py, nse_bhavcopy.py,
                              nse_bhavcopy_urls.py, known_items.py,
                              known_seed_items.py, date_parsing.py,
                              backfill_from_manifest.py
ledgerlight/processing/      pdf.py, ocr.py, html.py, bhavcopy.py, xbrl.py,
                              limits.py, mime_sniff.py, runner.py,
                              document_processor.py, price_loader.py, batch.py
ledgerlight/orchestration/   definitions.py
scripts/                     dagster_db_setup.py, garage_provision.py,
                              sources_sync.py, store_backfill.py, ingest.py,
                              backfill.py, process.py, reprocess.py,
                              ingest_report.py, run_all_jobs_once.py,
                              dead_letter_demo.py
docs/                        adr/0004, data/temporal-semantics.md,
                              ingestion/architecture.md, ingestion/runbook.md,
                              phase-1/phase-1-report.md, phase-1/evidence/*
tests/                       9 new test files + synthetic PDF fixture
```

Modified (not new): `.env.example`, `.gitignore`, `Makefile`, `README.md`,
`pyproject.toml`, `uv.lock`, `ledgerlight/common/timeutil.py`,
`ledgerlight/config/settings.py`, `scripts/acquire_seed.py`,
`scripts/infra_check.py`, `tests/conftest.py`, `.pre-commit-config.yaml`.

## 4. Database schema and temporal semantics

8 tables (`sources`, `documents`, `document_versions`, `document_pages`,
`price_bars`, `ingestion_runs`, `processing_attempts`, `dead_letters`),
one Alembic migration (`cef1aa08abb1_initial_ingestion_schema`), applied
cleanly to both the real app database and a throwaway empty database
(§10). `alembic check` reports no drift against the current models.

The `known_at` rule (earliest *trustworthy* evidence of public
availability — `published_at` only from an allowlisted reliable source,
else `snapshot_at`, else `retrieved_at`, never inferring an earlier date
than evidence supports) is implemented once
(`ledgerlight/db/temporal.py::compute_known_at`), documented in full in
`docs/data/temporal-semantics.md`, and covered by 7 unit tests
(`tests/test_temporal.py`).

## 5. Object storage

`ledgerlight/storage/s3_store.py::ObjectStore` — content-addressed keys
(`raw/<sha256[:2]>/<sha256><ext>`), existence check before upload, hash
verification on read-back. A persistent bucket/key
(`ledgerlight-raw`/`ledgerlight-raw-store`) was provisioned once via
`scripts/garage_provision.py`. `scripts/store_backfill.py` was run four
times total across this phase (two early idempotency proofs before
compaction, plus two more after the live ingestion jobs added new
manifest entries): the final two runs show **0 created / 468 already
present** both times — true idempotency, not just "ran without erroring"
(`docs/phase-1/evidence/store-backfill-run3.log`,
`store-backfill-run4-idempotent.log`).

## 6. A real bug found in this phase's own code: missing commits

**Finding:** `ledgerlight/ingestion/upsert.py::upsert_document_version`
only called `session.flush()`, never `session.commit()`. Every live
ingestion job (`run_known_items_job`, `run_bhavcopy_range`) relied on
this function alone to persist new `Document`/`DocumentVersion` rows and
never committed afterward either. A SQLAlchemy `Session`'s context
manager (`with session_factory() as session:`) calls `session.close()`
on exit, which **rolls back** an open transaction rather than committing
it.

**Impact (caught, not hidden):** the first full run of all 15 Dagster
jobs and the first full 2019 backfill (`docs/phase-1/evidence/
dagster-job-runs.log`, `backfill-2019.log`) appeared to succeed — correct
stats were printed, no errors — but every newly-fetched document's
database rows were silently discarded the instant each script exited.
Only `scripts/process.py`'s own data (which does commit explicitly in
`price_loader.load_price_bars` / `document_processor.process_version`)
actually persisted from that first pass. Found by cross-checking a
specific expected row (`BhavCopy_NSE_CM..._20250901...`) against the
database after the run and finding it absent — not assumed working from
the printed stats.

**Fix:** `upsert_document_version` now calls `session.commit()` on every
return path. Re-ran all 15 Dagster jobs and the full 2019 backfill a
second time (`docs/phase-1/evidence/dagster-job-runs-run2-post-commit-fix.log`,
`backfill-2019-run2-post-commit-fix.log`) and confirmed via direct SQL
that `nse_archives` document count went from 200 → 423 and the
2025-09-01 bhavcopy document now exists. `scripts/process.py` was then
re-run over the enlarged corpus (§8).

## 7. Ingestion jobs — real runs, real run IDs

All 15 Dagster jobs (`bhavcopy_job`, `inbox_import_job`, and 13
per-source `*_job`s) were executed via the Dagster Python API
(`DagsterInstance.execute_in_process`) against the real Postgres-backed
instance, **twice** (once before, once after the §6 fix) — every run
succeeded (`success: True`), with run IDs recorded in both
`docs/phase-1/evidence/dagster-job-runs*.log` and the `ingestion_runs`
table (17 rows: 15 from the two job-sweeps' net-new runs plus 2 from the
two `backfill.py` invocations, which also go through
`run_tracking.start_run`/`finish_run`).

| source | verdict | enabled | last run |
|---|---|---|---|
| nse_archives | AVAILABLE_WITH_LIMITS | yes | success, 423 docs |
| sebi, ibbi, care | AVAILABLE | yes | success |
| 9 company IR sites | AVAILABLE | yes | success |
| india_ratings, acuite | AVAILABLE_WITH_LIMITS | yes | never run (no seed items queued for these yet — enabled, schedulable, just no backlog) |
| bse, nse, crisil, icra, mca, dhfl_own_site | BLOCKED | **no** | unschedulable (enforced + tested) |
| infomerics, brickwork, price_data_alternatives, academic_datasets | UNCLEAR | **no** | unschedulable |
| commercial_datasets | REQUIRES_PAYMENT_OR_LICENCE | **no** | unschedulable |
| alpha_vantage | AWAITING_KEY | **no** | unschedulable |
| kaggle_nse_datasets | REQUIRES_REGISTRATION | **no** | unschedulable |

Full per-source table: `docs/phase-1/evidence/ingest-report-final.log`.

## 8. Backfill, survivorship check, and processing

**Backfill:** `make backfill START=2019-01-01 END=2019-12-31` — 261
business days attempted, 222 newly fetched, 22 already present (seed
overlap), 17 correctly skipped as non-trading-day 404s, **0 errors**,
measured throughput 0.499 req/s (rate-limited, as configured). Extends
real daily coverage by one full calendar year beyond the original
twice-monthly seed sample.

**Full-range backfill command and estimate:**
`make backfill START=2017-01-01 END=2025-09-30` — not run in full during
this phase (would take hours; see below). Estimated from the measured
rate above: ≈2,250 business days over that ~8.75-year range ÷ 0.499
req/s ≈ 4,500s ≈ **75 minutes minimum**, plus per-file processing time if
`scripts/process.py` is re-run afterward (observed ≈31-44 minutes for
the 211-434 files already processed in this phase) — budget **2-3 hours
end to end** for a genuinely full historical backfill + reprocess.

**Survivorship-bias check (real, not synthetic):** Jet Airways
(`JETAIRWAYS`) traded 244 real sessions in 2019 (price falling from
₹280.80 to ₹245.20 in just the first week of January, consistent with
its known 2019 financial distress) and has **zero** rows in the most
recently ingested bhavcopy (2025-09-01) — it was delisted in 2021.
A pipeline that only ever looked at the current/live bhavcopy would never
see this symbol at all; the historical backfill is what recovers it.
Full query output: `docs/phase-1/evidence/survivorship-check-jetairways.log`.

**Processing:** `scripts/process.py` run over the full corpus three
times, reflecting real corpus growth from the §6 fix and the
`store_backfill` catch-up (§5):

| run | versions_seen | pdf/html pages created | bhavcopy files | price rows upserted | quarantined | errors |
|---|---|---|---|---|---|---|
| 1 (pre-backfill, 237 docs) | 237 | 528 | 211 | 472,343 | 0 | 0 |
| 2 (post-backfill, 434 bhavcopy files) | 464 | +4 | 434 | 490,222 new / 415,268 unchanged | 0 | 0 |
| 3 (post store-backfill catch-up, final) | 468 | +4 | 434 | 58,778 / 846,712 unchanged | 0 | 0 |

Final totals: 443 documents, 468 document_versions, **536 document_pages,
876,101 price_bars rows**, 0 quarantined rows across the entire corpus,
0 processing errors, across all three runs. Full logs:
`docs/phase-1/evidence/process-full-corpus-run1.log`,
`process-full-corpus-run2-post-backfill.log`,
`process-full-corpus-run3-final.log`.

## 9. Document processing internals — two more real bugs found and fixed

**OCR heuristic false-triggers (found via real-corpus probing, fixed
before being trusted):** the naive "low character count ⇒ needs OCR"
rule false-triggered on real graphic-design-heavy annual-report pages
(a cover page: 27 chars / 55 images; a divider page: 23 chars / 271
images — design layouts, not scans). Fixed by adding an upper bound on
image count (`OCR_MAX_IMAGE_COUNT = 3`). **Probing the entire real corpus
found zero genuinely scanned pages** — reported honestly, not hidden:
the OCR code path is instead proven working against a committed
SYNTHETIC fixture (`tests/fixtures/synthetic_scanned_page.pdf`, clearly
labeled as such, generated from scratch — not a real downloaded
document), which RapidOCR reads back with 97.6% mean confidence,
recovering the exact embedded text (`tests/test_ocr_engine.py`).

**Per-document timeout bug:** `run_with_timeout`'s first implementation
used `proc.join(timeout=...)` to detect subprocess completion, which does
not reliably signal promptly — PyMuPDF's native threads can keep the OS
process "alive" long after the Python-level result was already produced.
A real 29-page PDF that finishes in ~3s was observed waiting out an
entire 60s timeout before the parent noticed. Fixed by blocking on
`result_queue.get(timeout=...)` instead (returns the instant a result is
ready, independent of process liveness); `proc.join()`/`.terminate()` now
only run as best-effort cleanup afterward. Confirmed fixed:
`scripts/reprocess.py` on that same real SEBI PDF now completes
instantly and shows `pages_already_present: 29`
(`docs/phase-1/evidence/reprocess-idempotency-demo.log`), proving both
the timeout fix and the determinism guarantee (same `extractor_version`
⇒ no new rows) in one real run.

## 10. Dagster orchestration — two real compatibility bugs found and fixed

Full detail and root cause in `docs/adr/0004-metadata-store-and-orchestration.md`.
Summary:

1. **Context-annotation validation failure.** Dagster's op/asset
   decorators validate the `context` parameter's type by *identity*
   against their own imported context classes, using the raw (unresolved)
   annotation. With `from __future__ import annotations` active, every
   annotation becomes a lazy string, so `context: dg.AssetExecutionContext`
   can never match regardless of alias. Fixed by removing
   `from __future__ import annotations` from `ledgerlight/orchestration/
   definitions.py` specifically and importing the four context classes
   directly.
2. **`dagster-postgres`'s `NOTIFY` call breaks under psycopg3.**
   PostgreSQL's `NOTIFY` only accepts a literal payload, not a bound
   parameter; psycopg2 (what `dagster-postgres` assumes) hides this via
   client-side string interpolation, but SQLAlchemy 2.x now defaults a
   bare `postgresql://` scheme to psycopg3, which binds server-side and
   fails outright. Fixed by setting `scheme: postgresql+psycopg2` on each
   of Dagster's own storage blocks in `dagster_home/dagster.yaml`,
   leaving the application's own engine on psycopg3 untouched.

Dagster's own run/event/schedule storage lives in a separate database
(`ledgerlight_dagster`) from the application schema — verified by
listing databases and confirming disjoint table sets.

## 11. Observability

- Structured JSON logs (`structlog`) carry `run_id`/`source_id`/
  `document_id`/`stage`; no document text or secrets are ever logged
  (spot-checked across every evidence log in this report — only URLs,
  hashes, counts and stats appear).
- `ingestion_runs` now persists real per-run metrics (17 rows, wired via
  `ledgerlight.ingestion.run_tracking` into every known-items job,
  the bhavcopy job, and the batch processor).
- `scripts/ingest_report.py` (`make ingest-report`) — per-source status,
  dead-letter counts by stage, failure-class breakdown. Final run:
  `docs/phase-1/evidence/ingest-report-final.log`.
- Retry/dead-letter/reprocess proven end-to-end both as a pytest
  (`tests/test_retry_dead_letter.py`, 2 tests) and as a standalone CLI
  demo against the real database (`scripts/dead_letter_demo.py`,
  `docs/phase-1/evidence/dead-letter-demo.log`): 3 simulated failures →
  1 `dead_letters` row written on the final attempt → a subsequent
  successful "reprocess" attempt records its own success row without
  touching the dead-letter row.
- Every failure is classified into exactly one of `network`, `http_4xx`,
  `http_5xx`, `parse`, `timeout`, `limit_exceeded`, `validation`
  (`ledgerlight.ingestion.base.classify_exception`); no bare `except` or
  silent swallowing in the ingestion/processing path (all `except
  Exception` sites are commented `# noqa: BLE001 - recorded, not
  swallowed` and append to a stats/errors list that's printed and
  returned non-zero).

## 12. Tests

**Updated after the §17 verification pass.** 99 tests total, all passing:

- **89 unit** (default `pytest` run, no external dependencies) — includes
  7 `known_at` tests, 7 limits tests, 6 mime-sniff tests, 6 OCR-heuristic
  tests, 5 bhavcopy-parsing/quarantine tests, 3 OCR-engine tests (against
  the synthetic fixture), 5 content-identity tests (§17.1), 4 per-document
  timeout tests (§17.2), plus all pre-existing Phase 0 tests.
- **8 integration** (`-m integration`, real Postgres): BLOCKED-source-
  unschedulable (2 tests), unknown-source-raises, retry/dead-letter
  (2 tests), content-identity upsert dedup (§17.1), and the commit-
  visibility regression test (§17.3) — the last one deliberately does
  NOT use the rolled-back-transaction fixture other integration tests
  use, since that pattern cannot catch a missing `commit()` (see §17.3).
- **2 corpus** (`-m corpus`, real `data/raw/`, skip cleanly if absent):
  real-bhavcopy-parses-cleanly, real-corpus-has-zero-scanned-pages.
- No placeholder tests, no `assert True`. Only one committed SYNTHETIC
  fixture (`tests/fixtures/synthetic_scanned_page.pdf`), clearly labeled
  as such in its own docstring and the test file that uses it — never a
  real downloaded document.

```
89 passed, 10 deselected in 12.19s      (default)
8 passed, 91 deselected in 5.17s        (-m integration)
2 passed, 97 deselected in 9.79s        (-m corpus)
```

## 13. §10 verification sequence — commands run and evidence

| Step | Command | Result | Evidence |
|---|---|---|---|
| Lint | `ruff check .` / `ruff format --check .` | pass (1 auto-fix applied) | — |
| Typecheck | `mypy` (49 source files) | pass | — |
| Unit tests | `pytest` | 80 passed | — |
| Integration tests | `pytest -m integration` | 6 passed | — |
| Corpus tests | `pytest -m corpus` | 2 passed | — |
| DB migration, empty | `alembic upgrade head` on a throwaway DB | 9 tables created | `db-upgrade-from-empty.log` |
| DB drift check | `alembic check` | no drift | — |
| Store backfill ×2 (final) | `scripts/store_backfill.py` | 0 created / 468 present, twice | `store-backfill-run3.log`, `run4-idempotent.log` |
| Each ingestion job ×2 | `scripts/run_all_jobs_once.py` | 15/15 success, both times | `dagster-job-runs.log`, `-run2-post-commit-fix.log` |
| Bhavcopy backfill ×2 | `scripts/backfill.py 2019-01-01 2019-12-31` | 222 new / 0 errors, both times | `backfill-2019.log`, `-run2-post-commit-fix.log` |
| Full-corpus process ×3 | `scripts/process.py` | 0 errors, 0 quarantined, all three times | `process-full-corpus-run1.log`, `-run2-post-backfill.log`, `-run3-final.log` |
| Survivorship check | raw SQL (§8) | JETAIRWAYS: 244 rows in 2019, 0 in 2025-09-01 | `survivorship-check-jetairways.log` |
| ingest-report | `scripts/ingest_report.py` | all enabled sources `success` | `ingest-report-final.log` |
| Dead-letter demo | `scripts/dead_letter_demo.py` | 3 fail → dead letter → reprocess success | `dead-letter-demo.log` |
| Reprocess idempotency | `scripts/reprocess.py <version_id>` | 0 new pages, 29 already-present | `reprocess-idempotency-demo.log` |
| pre-commit, all hooks | `pre-commit run --all-files` (+ `--hook-stage pre-push`) | all pass (after fixing the mypy hook's OOM-prone isolated env and a Windows path-resolution issue in two local hooks — see §14) | — |
| gitleaks, full history | `gitleaks detect --source . --log-opts="--all"` | 3 commits scanned, no leaks | `gitleaks-full-history-pre-phase1.log` |

## 14. A real pre-commit configuration bug found and fixed

Running `pre-commit run --all-files` for real (not assumed working)
found two problems:

1. The `mirrors-mypy` hook builds its own fully isolated virtualenv and
   needed every Phase 1 runtime dependency (`sqlalchemy`, `dagster`,
   `pymupdf`, `boto3`, `numpy`, ...) added to `additional_dependencies` to
   resolve imports at all. Installing a second full copy of these
   (`dagster` alone pulls a large dependency tree) alongside everything
   already running triggered an OOM kill of the install process.
   **Fixed** by replacing it with a local hook that runs mypy via this
   project's own already-populated `.venv` instead (matching the existing
   `pytest-fast` local hook's pattern) — no second environment, no
   duplicate installs.
2. That local hook's `entry: uv run mypy` failed with `Executable 'uv'
   not found` — `uv` isn't on this shell's PATH. Fixed by invoking the
   venv's `python.exe` directly (`./.venv/Scripts/python.exe -m mypy`,
   forward slashes — `pre-commit` parses `entry` with POSIX `shlex`
   regardless of OS, so backslashes get eaten as escapes). Applied the
   same fix to the pre-existing `pytest-fast` hook for consistency, since
   it would have hit the identical failure the first time it ran.

## 15. Exit gates

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | Metadata store schema migrated (Alembic), applies cleanly from empty | PASS | §4, §13 |
| 2 | `known_at` rule implemented once, documented, tested | PASS | §4 |
| 3 | Content-addressed object storage, idempotent backfill proven | PASS | §5 |
| 4 | BLOCKED/UNCLEAR/REQUIRES_*/AWAITING_KEY sources impossible to schedule, enforced in code and proven by test | PASS | §7, `tests/test_sources_unschedulable.py` |
| 5 | Real ingestion for every AVAILABLE/AVAILABLE_WITH_LIMITS source, hash dedup, full provenance | PASS | §7 |
| 6 | Bhavcopy backfill extends coverage ≥1 calendar year, measured throughput, survivorship check | PASS | §8 |
| 7 | PDF/HTML/CSV extraction, safety limits tested, OCR fallback actually runs | PASS (OCR proven on synthetic fixture — real corpus has zero genuine scans, reported honestly) | §9 |
| 8 | Deterministic re-processing (same extractor_version ⇒ byte-identical, no new rows) | PASS | §9 |
| 9 | Dagster orchestration: partitions/jobs/schedule/sensor, separate DB, every job run with recorded run IDs, retries, dead-letters | PASS, with one caveat noted in §2 (per-item attempt-tracking not yet wired into live jobs, proven only via dedicated module/demo) | §7, §10, §11 |
| 10 | Observability: structured logs, persisted run metrics, ingest-report CLI, fixed failure taxonomy | PASS | §11 |
| 11 | Tests: unit + integration + corpus, no placeholders, only labeled synthetic fixtures committed | PASS | §12 |

No gate is BLOCKED or FAIL. Gate 7 and gate 9 carry explicit caveats
rather than an unqualified PASS, stated above rather than smoothed over.

## 16. Git and backup status

- Phase 1 is committed across three commits on branch
  `phase-1/ingestion-and-document-processing` (branched from
  `phase-0/environment-and-data-inventory`'s tip): `85fef1e` (main
  implementation), `0e30841` (report finalization), and `d0bc7f7`
  (this verification pass's gap closure) — current tip
  `d0bc7f74fb14e5f3c4ab9b0e3f01a69f452ada16`. All authored by
  `gaurav685 <gaurav685@gmail.com>` — verified via `git log -n 5
  --format='%H%n%an <%ae>%n%B---'` to carry **no AI/Claude/Anthropic
  attribution of any kind** in any of the 5 commits in this repository's
  history.
- No remote added, nothing pushed — per your standing instruction
  (deferred to the end of the whole project). `git branch -a` shows only
  the two local phase branches, no `origin`.
- A local git bundle backup was created at
  `../ledgerlight-backups/ledgerlight-phase-1.bundle` (462,106 bytes,
  outside the repo) containing both phase branches' complete history,
  and verified: `git bundle verify` reports "the bundle records a
  complete history" and lists both branch refs plus `HEAD` at the
  current tip.

## 17. Phase 1 Verification Pass (gap closure)

A follow-up verification pass re-examined the real data Phase 1
produced — count reconciliation, OCR/determinism, incremental/versioning
behaviour, safety limits, the dead-letter cycle, bhavcopy formats, and a
dedicated regression test for the §6 commit bug. **Three more real
defects were found and fixed**, and one real limitation was identified
and deliberately left unfixed (documented, not hidden).

### 17.1 Real bug: spurious DocumentVersion rows from non-deterministic ZIP re-wrapping

**Finding.** Investigating why 15 documents had more than one version
(§3.2 of the verification request) found that **all 11 ZIP-type
multi-version documents had byte-identical inner CSV content across
every version** — confirmed by unzipping and diffing, not assumed. NSE's
server regenerates each ZIP's per-entry timestamp on every request
(observed: `(2023, 8, 21, 17, 32, 16)` vs `(2023, 8, 21, 17, 32, 14)` for
the same trading day, same CRC, same file size, same bytes once
unzipped), so hashing the raw downloaded bytes — correct for content-
addressed storage, since that's genuinely what was received — was also
being used as the *versioning* identity check, creating a new
`DocumentVersion` on every re-fetch of an unchanged trading day even
though nothing had changed.

**Fix.** Added `ledgerlight.ingestion.content_identity`: for a single-
entry ZIP, the dedup-relevant "content identity" hash is computed from
the *inner* entry's bytes, ignoring container metadata; for anything
else, it's the raw bytes unchanged. Added a `content_sha256` column to
`document_versions` (migration `c88219a1fbbb`) and wired
`upsert_document_version` to check by content-identity hash before
deciding a re-fetch is genuinely new content. The existing 15 duplicate
rows were **not deleted** (a destructive operation beyond this
verification's scope — see §18) but `content_sha256` was backfilled for
all 468 existing rows so the duplicates are at least now identifiable.
Proven two ways: `tests/test_content_identity.py` (5 pure-function
tests, including the exact real byte pattern — same inner content,
different ZIP timestamp) and `tests/test_upsert_content_identity.py`
(1 integration test proving `upsert_document_version` returns
`version_was_new=False` for a jittered re-fetch).

**A related but distinct problem was found and deliberately NOT fixed:**
the other 4 multi-version documents (2 IBBI NCLT listing pages,
`pnbhousing_ir`/`suzlon_ir` shareholding pages) are dynamic HTML pages
that embed per-request CSRF tokens and session nonces (`Liferay.authToken
= 'jE6l8JTh'` vs `'scNXdLRy'`; randomized DOM element IDs like
`cigw_quickAccessNav` vs `pcfr_quickAccessNav`) — confirmed by diffing,
not assumed. These will never byte-match across fetches regardless of
container normalization. Generically fixing this would require fragile,
source-specific HTML scrubbing rules; given it affects only 4 auxiliary
index/listing pages (not primary financial documents), it's documented
here as a known limitation rather than patched. See §18.

### 17.2 Real gap: zero test coverage for the per-document timeout

`ledgerlight.processing.runner.run_with_timeout` — the module whose
rewrite fixed a real hang bug (§9) — had no test exercising either its
timeout path or its "completes promptly" path. Added
`tests/test_runner_timeout.py` (4 tests): a fast function returns
correctly; a function that takes real time but stays under the timeout
still returns promptly (the exact regression the original bug was
about); a function exceeding the timeout raises `ProcessingTimeoutError`;
an exception inside the worker is wrapped as `ProcessingFailedError`.

### 17.3 Regression test for the §6 commit bug, with a real fail/pass demonstration

Added `tests/test_commit_visibility_regression.py`. It deliberately does
**not** use the `db_session` fixture other integration tests share
(which wraps each test in a transaction rolled back at teardown) —
that pattern proves application *logic* correctness within one session,
but cannot catch a missing `commit()`, because an uncommitted write
stays visible to a second `Session` bound to the *same* held connection.
This test instead uses two fully independent engines: ingest with
session A, close it, then check visibility from a brand-new session B on
a separate connection — precisely how the real bug manifested.

Demonstrated for real, not just written:
1. With the fix in place: **PASSED**
   (`docs/phase-1/evidence/commit-regression-pass-before-revert.log`).
2. `session.commit()` → `session.flush()` temporarily reverted in
   `ledgerlight/ingestion/upsert.py` (the exact original bug): **FAILED**
   with `assert None is not None` — the document was invisible from the
   new session, reproducing the original defect exactly
   (`docs/phase-1/evidence/commit-regression-FAIL-with-bug-reverted.log`).
3. Fix restored, re-ran: **PASSED** again
   (`docs/phase-1/evidence/commit-regression-pass-after-restore.log`).
   `git diff` confirmed only the intended fix remains afterward.

### 17.4 A real data-leak bug in `scripts/dead_letter_demo.py` itself

**Finding.** The script's own closing comment claimed
`session.rollback()  # this is a demo -- never leaves rows behind` — but
`run_with_attempt_tracking` commits internally on every attempt
(exactly the §6 commit-semantics lesson), so that `rollback()` was a
no-op and every run of this demo left real `processing_attempts` and
`dead_letters` rows in the production-shaped database. Found 8 leaked
`processing_attempts` rows and 2 leaked `dead_letters` rows from two
earlier runs of this exact script.

**Fix.** Replaced the ineffective `rollback()` with explicit `DELETE`s
of the rows the run actually created, and deleted the 10 pre-existing
leaked rows directly. Re-verified: `select count(*) from dead_letters`
and `processing_attempts` both return 0 immediately after a demo run
(`docs/phase-1/evidence/dead-letter-demo-fixed.log`). Also added a
dedicated real-pipeline version of this demo
(`scripts/dead_letter_real_pipeline_demo.py`) that ingests a genuinely
corrupted synthetic PDF through the actual `document_processor
.process_version` path (not an abstract lambda), fails 3 times with a
real `PyMuPDF` error, dead-letters, gets "fixed" with a valid PDF,
reprocesses successfully, and confirms `resolved_at` is set — then
cleans up explicitly
(`docs/phase-1/evidence/dead-letter-real-pipeline-demo.log`). Also added
`resolve_dead_letter_if_any` to `ledgerlight.ingestion.retry` (called
automatically on every successful attempt), since no code previously set
`resolved_at` at all despite the column existing since Phase 1's
original migration.

### 17.5 Count reconciliation, OCR, incremental/versioning, limits, bhavcopy formats — all clean

No further defects found. Full raw output for each of these is in this
turn's transcript and in `docs/phase-1/evidence/`; summarized:

- **Counts**: 443 documents / 468 versions reconciles exactly from
  444 Phase 0 manifest lines (237 distinct content-versions, 220 distinct
  documents) union 530 live-ingestion manifest lines (269 distinct
  content-versions, 265 distinct documents, of which 42 URLs overlap with
  the seed) — 220+223=443 documents, union of 237 and 269 distinct-
  version sets = 468 versions, both matching the database exactly.
- **15 largest PDFs**: PyMuPDF page count vs stored `document_pages`
  rows — 0 mismatches.
- **Versions with 0 pages**: only `application/zip` (434 rows) —
  expected (bhavcopy content goes to `price_bars`, not `document_pages`).
- **`known_at_basis`**: matches the documented reliable-source allowlist
  exactly (`sebi`/`ibbi`/`care`/`nse_archives` use `published_at` when
  parseable, `retrieved_at` otherwise; every other source always uses
  `retrieved_at`).
- **OCR**: 0 real pages flagged `needs_ocr` across all 518 real PDF
  pages (full heuristic output, not just the earlier spot-check) — the
  same 14 low-text pages previously found are confirmed design layouts
  (0-8 images, correctly below `OCR_MAX_IMAGE_COUNT`). A real-document
  functional check (Thermax annual report page 1, clearly labeled as a
  functional check, not a scanned-page claim) correctly OCR'd "44th
  Annual Report 2024-25 THERMAX..." at 98.9% confidence.
- **Determinism**: 10 real PDFs re-extracted, all 10 `text_sha256`
  matches.
- **Incremental**: SEBI job run twice in succession — both runs show
  `fetched_new=0, unchanged=3` (content hadn't changed since an earlier
  run today; a literal "N new → 0 new" transition wasn't available to
  demonstrate since nothing in this source had changed all day, reported
  honestly rather than staged).
- **Safety limits**: all 15 limit/path-traversal/MIME-sniff tests pass;
  configured values printed (200MB file size, 2000 pages, 120s timeout,
  1GB ZIP uncompressed, 10,000 ZIP entries).
- **Bhavcopy formats**: legacy 405 files / 819,112 rows (2017-01-05 to
  2024-07-05), UDiFF 29 files / 86,378 rows (2024-07-22 to 2025-09-22),
  0 quarantined in either format across the full corpus.
- **Survivorship**: 574 symbols present in 2017 (the seed's sparse
  twice-monthly sample) absent from the latest (2025-09-22) bhavcopy —
  e.g. `3IINFOTECH`, `ABGSHIP`, `ADANITRANS` (renamed/delisted/merged
  over the intervening years).

## 18. Decisions needing your approval

1. **The 11 spurious ZIP-jitter DocumentVersion rows (§17.1) were left
   in place**, not deleted — `content_sha256` now identifies them as
   duplicates, and the fix prevents new ones, but the historical rows
   themselves are untouched. If you'd like them merged/cleaned up
   retroactively (repointing any `document_pages`/`price_bars` that
   reference the "extra" version onto the earliest version per document,
   then deleting the rest), say so explicitly — it's a real decision
   with FK implications I didn't want to make unilaterally this late.
2. **The 4 dynamic-HTML-token duplicate versions (§17.1) are not
   fixed** and are unlikely to be fixable generically. If these specific
   pages matter enough to warrant per-site scrubbing rules (strip known
   token/nonce patterns before hashing), that's additional Phase 1.x (or
   Phase 2) scope, not something I built unasked.
3. **Retry/dead-letter attempt-tracking is still not wired per-item
   into the live ingestion jobs** (`run_known_items_job`,
   `run_bhavcopy_range`) — proven correct via dedicated tests/demos, but
   production ingestion runs still only record job-level stats, not a
   `processing_attempts` row per item. Wiring it in would mean every
   SEBI/IBBI/bhavcopy fetch gets its own attempt-tracked row; flagging
   before doing it since it changes the volume/shape of that table.
4. **The pre-commit `mypy`/`pytest-fast` hooks now hardcode
   `./.venv/Scripts/python.exe`** (Windows-specific), fixed this session
   after the original `uv run ...` entries failed with `uv` not on PATH
   in the verification shell. If this project ever needs to run `pre-
   commit` on a non-Windows machine, this will need revisiting.

## 19. Updated exit gates (re-marked after the verification pass)

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | Metadata store schema migrated (Alembic), applies cleanly from empty | PASS | §4, §13; migration `c88219a1fbbb` also applied cleanly |
| 2 | `known_at` rule implemented once, documented, tested | PASS | §4, §17.5 |
| 3 | Content-addressed object storage, idempotent backfill proven | PASS | §5 |
| 4 | BLOCKED/UNCLEAR/REQUIRES_*/AWAITING_KEY sources impossible to schedule, enforced in code and proven by test | PASS | §7, `tests/test_sources_unschedulable.py` |
| 5 | Real ingestion for every AVAILABLE/AVAILABLE_WITH_LIMITS source, hash dedup, full provenance | PASS, with a real dedup defect found and fixed this pass (§17.1) | §7, §17.1 |
| 6 | Bhavcopy backfill extends coverage ≥1 calendar year, measured throughput, survivorship check | PASS | §8, §17.5 |
| 7 | PDF/HTML/CSV extraction, safety limits tested, OCR fallback actually runs | PASS (OCR proven on synthetic fixture and a real-document functional check — real corpus has zero genuine scans, reported honestly both times) | §9, §17.5 |
| 8 | Deterministic re-processing (same extractor_version ⇒ byte-identical, no new rows) | PASS | §9, §17.5 (10/10 real PDFs re-verified) |
| 9 | Dagster orchestration: partitions/jobs/schedule/sensor, separate DB, every job run with recorded run IDs, retries, dead-letters | PASS, with the same caveat as before (§18.3) — per-item attempt-tracking proven but not wired into live jobs | §7, §10, §11 |
| 10 | Observability: structured logs, persisted run metrics, ingest-report CLI, fixed failure taxonomy | PASS; `ingest-report` now also shows resolved/unresolved dead-letter counts (§17.4) | §11, §17.4 |
| 11 | Tests: unit + integration + corpus, no placeholders, only labeled synthetic fixtures committed | PASS; grew from 88 to 99 tests closing two real coverage gaps (timeout, commit-visibility) | §12, §17.2, §17.3 |

No gate is BLOCKED or FAIL. Four items are explicitly flagged for your
decision (§18) rather than resolved unilaterally.

---

**Stop after Phase 1 verification. Phase 2 has not been started.**
