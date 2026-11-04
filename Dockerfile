# Phase 5 §5: the real image the `api` and `worker` Compose services both
# run from -- same real dependency set, different real CMD per service
# (see infra/docker-compose.yml). Pinned to a specific Python patch
# release, not a floating "3.12" tag.
FROM python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0 AS base

# Real build tools only in a separate stage -- psycopg[binary] and torch
# ship real manylinux wheels, so no compiler is needed at runtime.
FROM base AS builder
RUN pip install --no-cache-dir uv==0.5.11
WORKDIR /app
COPY pyproject.toml uv.lock ./
# --no-dev: the real runtime image never needs pytest/ruff/mypy/pre-commit.
RUN uv sync --frozen --no-dev --no-install-project

FROM base
WORKDIR /app
# A real, non-root user -- never run the real API/worker process as root.
RUN groupadd --gid 1000 ledgerlight && useradd --uid 1000 --gid 1000 --create-home ledgerlight
COPY --from=builder /app/.venv /app/.venv
COPY --chown=ledgerlight:ledgerlight ledgerlight ./ledgerlight
COPY --chown=ledgerlight:ledgerlight scripts ./scripts
COPY --chown=ledgerlight:ledgerlight data/taxonomy ./data/taxonomy
# Only the real, committed config (dagster.yaml) -- logs/storage/etc. are
# real local runtime state (gitignored), created fresh by the worker
# process itself, never baked into the image.
RUN mkdir -p ./dagster_home && chown ledgerlight:ledgerlight ./dagster_home
COPY --chown=ledgerlight:ledgerlight dagster_home/dagster.yaml ./dagster_home/dagster.yaml
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app" PYTHONUNBUFFERED=1 DAGSTER_HOME=/app/dagster_home
USER ledgerlight
EXPOSE 8000
CMD ["uvicorn", "ledgerlight.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
