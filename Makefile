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

# --- Phase 2: knowledge store, classification, extraction, entity resolution ---

taxonomy-load:
	uv run python scripts/taxonomy_load.py data/taxonomy/taxonomy-v1.0.yaml

bootstrap-companies:
	uv run python scripts/bootstrap_companies.py

link-filings:
	uv run python scripts/link_filings.py

chunk-corpus:
	uv run python scripts/chunk_corpus.py

embed-chunks:
	uv run python scripts/embed_chunks.py

build-bm25-index:
	uv run python scripts/build_bm25_index.py

labels-propose:
	uv run python scripts/labels_propose.py

# usage: make label-review REVIEWER="your name" [LIMIT=20]
label-review:
	uv run python scripts/label_review.py --reviewer "$(REVIEWER)" $(if $(LIMIT),--limit $(LIMIT),)

labels-split:
	uv run python scripts/labels_split.py

train-classifier:
	uv run python scripts/train_classifier.py

evaluate:
	uv run python scripts/evaluate.py

extract:
	uv run python scripts/extract.py

resolve-entities:
	uv run python scripts/resolve_entities.py

retrieval-eval:
	uv run python scripts/retrieval_eval.py

# usage: make review-queue CMD="summary" (or "list", "resolve --id ... --resolution ... --reviewer ...", "dismiss --id ... --reason ... --reviewer ...")
review-queue:
	uv run python scripts/review_queue.py $(CMD)

knowledge-pipeline:
	$(DAGSTER_ENV) uv run dagster job execute -m ledgerlight.orchestration.definitions -j knowledge_pipeline_job
