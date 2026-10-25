.PHONY: setup lint typecheck test verify-env verify-manifests acquire-seed import-local infra-up infra-check infra-down \
	db-upgrade sources-sync store-backfill ingest backfill process reprocess ingest-report dagster-dev test-integration test-corpus

# Dagster's own instance config (dagster_home/dagster.yaml) interpolates
# LEDGERLIGHT_POSTGRES_* from the process environment, not from .env
# directly -- load it into the shell for every Dagster-touching target.
DAGSTER_ENV = set -a; . ./.env; set +a; export DAGSTER_HOME="$$(pwd)/dagster_home";

setup:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy

test:
	uv run pytest

verify-env:
	uv run python scripts/verify_env.py

verify-manifests:
	uv run python scripts/verify_manifests.py

acquire-seed:
	uv run python scripts/acquire_seed.py

import-local:
	uv run python scripts/import_local.py

infra-up:
	docker compose --env-file .env -f infra/docker-compose.yml up -d

infra-check:
	uv run python scripts/infra_check.py

infra-down:
	docker compose --env-file .env -f infra/docker-compose.yml down

db-upgrade:
	uv run alembic upgrade head

sources-sync:
	uv run python scripts/sources_sync.py

store-backfill:
	uv run python scripts/store_backfill.py

# usage: make ingest SOURCE=sebi [DATE=2025-09-01]
ingest:
	$(DAGSTER_ENV) uv run python scripts/ingest.py $(SOURCE) $(DATE)

# usage: make backfill START=2019-01-01 END=2019-12-31
backfill:
	uv run python scripts/backfill.py $(START) $(END)

process:
	uv run python scripts/process.py

# usage: make reprocess VERSION=<uuid>
reprocess:
	uv run python scripts/reprocess.py $(VERSION)

ingest-report:
	uv run python scripts/ingest_report.py

dagster-dev:
	$(DAGSTER_ENV) uv run dagster dev -m ledgerlight.orchestration.definitions

test-integration:
	uv run pytest -m integration

test-corpus:
	uv run pytest -m corpus
