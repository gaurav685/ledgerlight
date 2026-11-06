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

Six phases complete, a seventh (Phase 6A, integrated validation and
hardening) in progress. Each phase's own report has the full detail;
this section is a short pointer, not a substitute.

- **Phase 0** — environment, repository foundation, verified legal data
  inventory and seed dataset. `docs/phase-0/phase-0-report.md`.
- **Phase 1** — metadata store, content-addressed object storage, real
  ingestion jobs, PDF/HTML/bhavcopy processing with OCR fallback,
  Dagster orchestration, observability. `docs/phase-1/phase-1-report.md`.
- **Phase 2** — knowledge schema, versioned taxonomy, three event
  classifiers (rules/TF-IDF+LR/DeBERTa-v3 zero-shot NLI), one worked
  structured extractor with evidence verification, entity resolution,
  hybrid BM25+embedding retrieval. `docs/phase-2/phase-2-report.md`.
- **Phase 3** — temporal features and a LightGBM risk model, trained and
  deployed. The real, verified-coverage universe is only 5 companies
  (5 pooled distinct positive events) -- **statistically inconclusive**
  per the brief's own 30-event floor; no model variant beats the
  training-fold base rate. See `docs/modelling/model-card.md`
  (generated, re-verified byte-identical in Phase 6A §12) for the full
  real metrics and explicit no-predictive-skill-claim.
  `docs/phase-3/phase-3-report.md`.
- **Phase 4** — the evidence-verified investigation agent: a
  checkpointed PLAN/GATHER/TIMELINE/DRAFT/VERIFY/REPAIR/FINALISE state
  machine, 7 read-only tools, a full per-claim verifier (citation,
  date, number/unit, name, real local-NLI entailment, banned language,
  contradiction detection), budgets, human review workflow, and an
  adversarial/failure test suite. No LLM is ever called -- the default,
  fully-offline template-rendering path is what every real
  investigation in this project runs, by design, not by missing
  configuration. `docs/phase-4/phase-4-report.md`.
- **Phase 5** — the real `/v1` FastAPI surface with Postgres Row-Level
  Security tenancy, argon2id auth/sessions/CSRF/API keys, a Next.js
  analyst frontend, Docker Compose for the full local stack,
  validated-but-unapplied AWS Terraform, 5 GitHub Actions workflows
  (never run on GitHub -- no remote configured, by policy), and the
  required security test suite. `docs/phase-5/phase-5-report.md`.
- **Phase 6A — integrated validation, hardening, and review (in
  progress).** §1 through §11 of the brief complete: a green,
  single-sequential-pass baseline (408 default + 330 integration
  tests); a real end-to-end pipeline test (ingestion through dossier
  citation chain); a golden-fixture regression suite; backtest
  reproducibility audits; a consolidated pre-review evaluation report;
  a 5-type human review pack (built, not yet reviewed -- that is
  explicitly Phase 6B's job); a real load test, throughput measurement,
  and 5 failure-recovery drills; a full security re-validation
  (`pip-audit` found and fixed 24 real vulnerabilities, including a
  real background-task regression the dependency bump itself exposed);
  real per-filing cost measurement plus a parameterised AWS cost model
  (`docs/ops/cost-per-filing.md`); and a data-source compliance and
  licence review that found one AI-crawler-blocking site (downgraded
  to BLOCKED) and one real, unresolved AGPL-3.0/commercial licensing
  question (`pymupdf`, this project's real PDF-extraction dependency --
  see `docs/compliance/data-sources.md` and
  `docs/release/release-gates.md`). §12 (final documentation) is in
  progress; §13 (clean-install test) through §18 (final report and
  human checkpoint) remain. See `docs/phase-6/progress.md` for the
  real, session-by-session log and `docs/release/release-gates.md` for
  every currently open gap with its real reason.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is fetched
automatically by `uv` via `.python-version`; no system Python install is
required). **`docs/deploy/local-setup-windows.md` is the full, real,
step-by-step guide this project was actually set up and run from** --
read it first on a fresh machine; the quick version below skips the
real memory/Docker caveats it documents.

```sh
uv sync                # create .venv and install locked dependencies
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
cp .env.example .env   # edit values as needed; .env is gitignored
# Required before `infra-up`: generate local-only secrets (object store,
# session cookies, webhook-secret encryption -- .env.example lists every
# real required variable; LEDGERLIGHT_ENVIRONMENT=development fails fast
# on any default/weak secret value, so these must be real random values)
echo "LEDGERLIGHT_GARAGE_RPC_SECRET=$(openssl rand -hex 32)" >> .env
echo "LEDGERLIGHT_GARAGE_ADMIN_TOKEN=$(openssl rand -hex 16)" >> .env
echo "LEDGERLIGHT_SESSION_SECRET_KEY=$(openssl rand -hex 32)" >> .env
# Must be a real Fernet key (url-safe base64, 32 bytes), not arbitrary hex:
echo "LEDGERLIGHT_WEBHOOK_SECRET_ENCRYPTION_KEY=$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" >> .env
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
| `uv run uvicorn ledgerlight.api.app:create_app --factory --reload` | Run the real API locally |
| `cd frontend && pnpm dev` | Run the real Next.js analyst frontend locally |
| `uv run python scripts/investigate.py --company COMPANY_ID --as-of YYYY-MM-DD` | Run one real investigation end to end (Phase 4) |
| `uv run python scripts/measure_cost_per_filing.py` | Real per-filing cost measurement (Phase 6A §10, `docs/ops/cost-per-filing.md`) |
| `uv run python scripts/generate_data_dictionary.py` | Regenerate `docs/data-dictionary.md` from the live model metadata |

`make` wraps every script above plus every later phase's own targets --
read the `Makefile` directly for the full, current list rather than
trusting a hand-maintained enumeration here to stay in sync; as of
Phase 6A it includes the Phase 2 knowledge-pipeline targets
(`taxonomy-load` through `knowledge-pipeline`, see
`docs/phase-2/phase-2-report.md`), the Phase 3 modelling targets
(`outcomes-taxonomy-load` through `model-card`, see
`docs/phase-3/phase-3-report.md`), and the Phase 6A human-review-pack
targets (`field-review`, `entity-pair-review`, `retrieval-review`,
`outcome-evidence-review`, `build-dossier-review-sample`,
`dossier-review-blind`, `review-progress`, `test-regression`,
`test-pyramid` -- see `docs/phase-6/human-review-guide.md`).

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
- **CRISIL, ICRA, MCA, and (added Phase 6A §11) Thermax IR are also
  BLOCKED** — CRISIL/Thermax because their robots.txt explicitly names
  AI-crawler user agents (this tool is operated by an AI agent); ICRA
  for a browser-fingerprinting challenge; MCA for an unconditional
  Access Denied. See `docs/compliance/data-sources.md` for the full,
  dated re-check and the exact reason for each.
- **`pymupdf` (this project's real PDF-extraction dependency) is
  dual-licensed GNU AGPL-3.0 / Artifex commercial — unresolved.** Does
  not block research/internal use; blocks any commercial/SaaS launch
  of the PDF-extraction functionality until resolved. See
  `docs/compliance/data-sources.md` and
  `docs/release/release-gates.md`.

## Repository layout

```
ledgerlight/         acquisition, ingestion, processing, knowledge,
                      modelling, agent, api, orchestration, db,
                      storage, review_pack, config, common
scripts/              one real CLI entry point per pipeline stage --
                      acquisition/ingestion/processing (Phase 0-1),
                      knowledge/modelling (Phase 2-3), agent/review
                      (Phase 4, 6A), API/ops (Phase 5-6A)
frontend/             Next.js analyst app (dossiers, companies,
                      watchlists, alerts, review, tenant admin)
docs/                 adr/, data/, knowledge/, evaluation/, agent/,
                      api/, frontend/, deploy/, security/, ops/,
                      compliance/, release/, modelling/,
                      architecture.md (hand-written), data-dictionary.md
                      (generated from live model metadata), phase-0/
                      through phase-6/ (one real per-phase report +
                      progress log each)
data/                 raw/ interim/ processed/ inbox/ (all gitignored)
                      + manifests/ (committed -- metadata only)
infra/                docker-compose.yml (Postgres+pgvector, Garage
                      S3-compatible storage), aws/ (validated,
                      unapplied Terraform)
tests/                unit + integration + corpus + security + e2e
                      tests (network/integration/corpus marked and
                      excluded by default -- see pyproject.toml)
```
