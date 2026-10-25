.PHONY: setup lint typecheck test verify-env verify-manifests acquire-seed import-local infra-up infra-check infra-down

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
