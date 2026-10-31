# Ledgerlight

Evidence-backed corporate-governance red-flag intelligence for Indian listed
companies. Ledgerlight ingests public disclosures (BSE/NSE announcements,
annual reports, shareholding/pledge disclosures, auditor resignations,
earnings-call transcripts, financial results, credit-rating actions, SEBI
orders, IBBI insolvency records, historical prices) and will produce
point-in-time risk scores and citation-verified investigation dossiers.

## Disclaimer

Ledgerlight's outputs are **analytical signals derived from public
disclosures**, not proof of misconduct, not a finding of wrongdoing against
any company or person, and not investment advice. Any "red flag" is a
statistical or disclosure-based signal that warrants further human review,
not a conclusion.

## Phase status

**Phase 0 — environment, datasets, dependencies and feasibility.** This
phase establishes the development environment, repository foundation, and a
verified, legally sourced data inventory and seed dataset. It does **not**
include the ingestion pipeline, database schema, extraction, models, API or
frontend. See `docs/phase-0/phase-0-report.md` for the full Phase 0 report.

**Phase 1 — data ingestion, raw storage and document processing.** This
phase adds the metadata store (SQLAlchemy/Alembic, Postgres), the
content-addressed object storage abstraction, real ingestion jobs for
every AVAILABLE/AVAILABLE_WITH_LIMITS source, PDF/HTML/bhavcopy
processing (with an OCR fallback and a tested safety-limits layer),
Dagster orchestration (partitions/jobs/schedules/sensor/retries), and
observability (structured logs, persisted run metrics, dead-letter
tracking, an `ingest-report` CLI). It does **not** include event
classification/extraction, entity resolution, chunking/embeddings,
features/models, API or frontend. See `docs/phase-1/phase-1-report.md`
for the full Phase 1 report and `docs/ingestion/architecture.md` /
`docs/ingestion/runbook.md` for the pipeline design and day-to-day usage.

**Phase 2 — knowledge store, classification, extraction and entity
resolution.** This phase adds the knowledge schema (companies/filings,
chunks, taxonomy, events/fields, entities/mentions/links/merges, review
queue, labels, model registry), a versioned taxonomy (v1.0) with
boundary-tested rule thresholds, three event classifiers (rules
baseline, TF-IDF+LR, DeBERTa-v3 zero-shot NLI) compared on a real
silver-labelled split, one real worked structured extractor (AUD_RESIGN)
with evidence verification against cited spans, entity resolution
(deterministic identifiers → normalization → fuzzy matching, with
conflict detection and reversible merges), and hybrid retrieval (true
BM25 + a local embedding model + reciprocal rank fusion, point-in-time
filtered). It does **not** include GUIDANCE_MISS detection, features,
risk models/scores, the investigation agent, API endpoints or frontend.
All classification/extraction/entity-resolution/retrieval metrics are
against SILVER labels — gold review is pending human review (see
`docs/phase-2/phase-2-report.md` §13). See
`docs/phase-2/phase-2-report.md` for the full Phase 2 report and
`docs/knowledge/` / `docs/evaluation/phase-2-evaluation.md` for the
schema, taxonomy, extraction, entity-resolution and retrieval design.

**Phase 3 — temporal intelligence and quantitative risk modelling.** In
progress. §1-§2 (preflight, detector hardening, market-wide data
expansion) and §3 (outcome definitions, frozen and hashed) are
complete. §4 (point-in-time features) is complete in full: two real
data-integrity bugs were found and fixed (a stale `company_identifiers`
window bug, and a duplicate-company bug the fix itself reintroduced,
both now self-healing); STRUCTURED price/liquidity, RULE-VERIFIED
rating/auto-link, and SEED-track governance features are built and
spot-verified against real company history (228,678 + 3,241 + 1,406
real `feature_snapshots` rows); financial features were excluded with
real evidence rather than shipped untested. §5 (guidance extraction)
was assessed and limits stated: 0 real management-issued guidance
statements exist anywhere in this project's corpus, so no extraction
machinery was built. Exit gate 4 (point-in-time integrity) is proven:
100% of feature rows with a real input satisfy `max_input_known_at <=
as_of`, 0 violations. **§6-§10 (LightGBM training, walk-forward
evaluation, leakage/survivorship/ablation, scoring and storage, CLI
commands, tests) are now functionally complete.** The real,
verified-coverage universe (companies with both real IBBI and real
CARE Filing coverage) is only 5 companies, giving a pooled distinct
positive-event count of 5 -- **statistically inconclusive** per the
brief's own 30-event floor; no model variant beats the training-fold
base rate. A final LightGBM model is trained and deployed to real
scores via `scripts/train_risk.py` / `scripts/score.py`, but **makes
no predictive-skill claim** -- see `docs/modelling/model-card.md`
(generated) for the full real metrics, intervals, limitations and
ethical considerations. It does **not** yet include the investigation
agent, API endpoints, or frontend. See `docs/phase-3/phase-3-report.md`
for the full report and `docs/modelling/` for outcomes, features,
guidance, data-quality, evaluation-protocol and model-card design docs.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is fetched
automatically by `uv` via `.python-version`; no system Python install is
required).

```sh
uv sync                # create .venv and install locked dependencies
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
cp .env.example .env   # edit values as needed; .env is gitignored
# Required before `infra-up`: generate local-only secrets for the object store
echo "LEDGERLIGHT_GARAGE_RPC_SECRET=$(openssl rand -hex 32)" >> .env
echo "LEDGERLIGHT_GARAGE_ADMIN_TOKEN=$(openssl rand -hex 16)" >> .env
```

## Commands

All commands are exposed as `uv run <script>` entry points (see
`pyproject.toml` / `scripts/`):

| Command | Purpose |
|---|---|
| `uv sync` | Install locked dependencies (setup) |
| `uv run ruff check . && uv run ruff format --check .` | Lint |
| `uv run mypy` | Typecheck (strict, on `ledgerlight` package) |
| `uv run pytest` | Run non-network unit tests |
| `uv run pytest -m network` | Run network-marked tests (requires internet) |
| `uv run python scripts/verify_env.py` | Verify local environment |
| `uv run python scripts/verify_manifests.py` | Validate data manifests against files on disk |
| `uv run python scripts/acquire_seed.py` | Re-run the Phase 0 seed-dataset acquisition |
| `uv run python scripts/import_local.py` | Import manually-downloaded documents from `data/inbox/` (see `docs/data/manual-download-checklist.md`) |
| `docker compose --env-file .env -f infra/docker-compose.yml up -d` | Start local Postgres+pgvector / Garage (S3-compatible) — `--env-file .env` is required: Compose otherwise looks for `.env` next to the compose file, not at the repo root |
| `uv run python scripts/infra_check.py` | Verify infra health (pgvector extension, S3 bucket round-trip) |
| `docker compose --env-file .env -f infra/docker-compose.yml down` | Stop local infra |
| `uv run alembic upgrade head` | Apply database migrations |
| `uv run python scripts/sources_sync.py` | Sync `sources` table from `data/manifests/sources.yaml` |
| `uv run python scripts/store_backfill.py` | Idempotently load all Phase 0 manifest entries into object storage |
| `uv run python scripts/ingest.py SOURCE_ID [DATE]` | Run one source's Dagster ingestion job |
| `uv run python scripts/backfill.py START END` | Historical bhavcopy backfill over a date range |
| `uv run python scripts/process.py` | Extract PDF/HTML text and load bhavcopy CSVs into `price_bars` |
| `uv run python scripts/reprocess.py VERSION_ID` | Force reprocessing of one document version |
| `uv run python scripts/ingest_report.py` | Per-source health / dead-letter / failure-class report |
| `uv run dagster dev -m ledgerlight.orchestration.definitions` | Dagster webserver (needs `DAGSTER_HOME`, see `docs/ingestion/runbook.md`) |

A `Makefile` wraps these as `make setup|lint|typecheck|test|verify-env|verify-manifests|acquire-seed|infra-up|infra-check|infra-down|db-upgrade|sources-sync|store-backfill|ingest|backfill|process|reprocess|ingest-report|dagster-dev|test-integration|test-corpus`, plus the Phase 2 targets `taxonomy-load|bootstrap-companies|link-filings|chunk-corpus|embed-chunks|build-bm25-index|labels-propose|label-review|labels-split|train-classifier|evaluate|extract|resolve-entities|retrieval-eval|review-queue|knowledge-pipeline` (see `docs/phase-2/phase-2-report.md`), plus the Phase 3 targets `outcomes-taxonomy-load|freeze-eval-data|select-classifiers|backfill-universe|outcomes-build|features-build|outcomes-and-features-build|point-in-time-proof|train-risk|backtest|leakage-check|ablation|score|model-card` (see `docs/phase-3/phase-3-report.md`).

## Data policy

- Nothing under `data/raw`, `data/interim` or `data/processed` is committed
  to this repository. These are gitignored and may contain documents whose
  redistribution rights are unclear or restricted.
- `data/manifests/*.jsonl` (metadata only — URLs, hashes, timestamps,
  licence notes — never document content) **is** committed, so provenance
  is reproducible without redistributing third-party content.
- Every acquisition respects the source's `robots.txt`, uses an identifying
  User-Agent, rate-limits per host, and never bypasses access controls
  (no CAPTCHA solving, no stealth automation, no credential sharing).
- A small number of documents that are only available on BSE/NSE (both
  BLOCKED for this tool — see below) can be added manually: drop the file
  in `data/inbox/` with a `data/inbox/provenance.csv` row, then run
  `scripts/import_local.py`. See
  `docs/data/manual-download-checklist.md` for exactly which documents
  this applies to (kept intentionally short).
- See `docs/data/source-inventory.md` for the per-source access and
  redistribution findings, and `docs/adr/0002-data-acquisition-policy.md`
  for the policy rationale. BSE and NSE's main sites are BLOCKED for this
  tool by edge bot-mitigation (not by robots.txt) — but NSE's bhavcopy
  price archive is reachable via a separate, unblocked subdomain; see
  `docs/data/source-inventory.md`.

## Repository layout

```
ledgerlight/        Python package (config, acquisition, common)
scripts/             verify_env, verify_manifests, acquire_seed, import_local, infra_check
docs/                adr/, data/, knowledge/, evaluation/, phase-0/, phase-1/, phase-2/
data/                raw/ interim/ processed/ inbox/ (all gitignored) + manifests/ (committed)
infra/               docker-compose.yml (Postgres+pgvector, Garage S3-compatible storage)
tests/               unit tests (network tests marked and excluded by default)
```
