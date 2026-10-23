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

## Setup

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is fetched
automatically by `uv` via `.python-version`; no system Python install is
required).

```sh
uv sync                # create .venv and install locked dependencies
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
cp .env.example .env   # edit values as needed; .env is gitignored
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
| `docker compose -f infra/docker-compose.yml up -d` | Start local Postgres+pgvector / MinIO |
| `uv run python scripts/infra_check.py` | Verify infra health (pgvector extension, MinIO bucket) |
| `docker compose -f infra/docker-compose.yml down` | Stop local infra |

A `Makefile` wraps these as `make setup|lint|typecheck|test|verify-env|verify-manifests|acquire-seed|infra-up|infra-check|infra-down`.

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
- See `docs/data/source-inventory.md` for the per-source access and
  redistribution findings, and `docs/adr/0002-data-acquisition-policy.md`
  for the policy rationale.

## Repository layout

```
ledgerlight/        Python package (config, acquisition, common)
scripts/             verify_env, verify_manifests, acquire_seed, infra_check
docs/                adr/, data/, phase-0/
data/                raw/ interim/ processed/ (gitignored) + manifests/ (committed)
infra/               docker-compose.yml (Postgres+pgvector, MinIO)
tests/               unit tests (network tests marked and excluded by default)
```
