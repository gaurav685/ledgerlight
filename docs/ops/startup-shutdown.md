# Startup / shutdown

Phase 5 §8. Covers the one real local stack this project runs
(`infra/docker-compose.yml`: `postgres`, `garage`, `api`, `worker`,
`web`). No production stack is actually deployed -- `infra/aws/` is
validated Terraform only (see `docs/deploy/aws-architecture.md`); this
runbook is written against what is real today and will extend to AWS
once that becomes real.

## Startup

```powershell
cp .env.example .env   # first time only -- then fill in real values
.\scripts\dev.ps1
```

`scripts/dev.ps1` builds and starts every service, waits for
`postgres`/`garage` to report healthy, runs `uv run alembic upgrade
head`, seeds the real TEST tenants (`scripts/seed_test_tenants.py` --
skip with `-SkipSeed` on a shared machine), then waits for `api` to
report healthy. Prints every real service URL on success.

Manual equivalent, step by step, if `dev.ps1` itself is what's broken:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
docker compose --env-file .env -f infra/docker-compose.yml ps        # watch for "healthy"
uv run alembic upgrade head
uv run python scripts/seed_test_tenants.py   # optional
```

## Shutdown

```powershell
docker compose --env-file .env -f infra/docker-compose.yml down
```

Add `-v` only if you intend to discard the real local `postgres`/
`garage` volumes (all real local data). Never run this with `-v`
without first running `scripts/backup.py` (see
`docs/ops/restore.md`) if the data matters.

## Health checks

- `GET /healthz` -- the API process is up (no DB round-trip).
- `GET /readyz` -- the API can reach Postgres as the real
  `ledgerlight_app` role.
- `GET /metrics` -- real Prometheus exposition text
  (`ledgerlight.api.metrics`); never routed through the public ALB
  listener in any real deployment (`infra/aws/alb.tf`'s own path rule)
  -- internal-network-only, same as the brief's requirement.
- `docker compose ... ps` -- each service's own container-level health
  check (Postgres: `pg_isready`; Garage: its own status RPC).

## Logs

Every real log line is structured JSON on stdout
(`ledgerlight.common.logging.configure_logging`, wired into
`ledgerlight.api.app.create_app`), carrying `request_id` on every
request and `tenant_id` once identity is resolved:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml logs -f api
```

A specific request's full log trail: grep for its `X-Request-ID`
response header value across the `api`/`worker` logs.
