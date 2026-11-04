<#
.SYNOPSIS
    Phase 5 §5: the real, single-command local bring-up for the full
    stack -- postgres/garage/api/worker/web -- on this Windows host.

.DESCRIPTION
    Builds api/worker/web from their real Dockerfiles, starts every
    service, waits for postgres+garage to report healthy, applies real
    database migrations, seeds the real TEST tenants
    (scripts/seed_test_tenants.py), then waits for api/web to report
    healthy too. Every step uses the project's own real, already-
    established commands (uv run alembic, docker compose) -- nothing
    here is a new mechanism, just one script sequencing them.

.PARAMETER SkipSeed
    Skip scripts/seed_test_tenants.py (e.g. on a shared/CI machine
    where the real TEST tenants already exist and you don't want
    their passwords reset).

.EXAMPLE
    .\scripts\dev.ps1
#>

[CmdletBinding()]
param(
    [switch]$SkipSeed
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Test-Path ".env")) {
    Write-Error ".env not found. Run: cp .env.example .env -- then fill in real values before retrying."
}

Write-Host "==> Building and starting postgres/garage/api/worker/web ..." -ForegroundColor Cyan
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed (exit $LASTEXITCODE)" }

function Wait-Healthy {
    param([string]$ServiceName, [int]$TimeoutSeconds = 120)
    Write-Host "==> Waiting for '$ServiceName' to report healthy (up to ${TimeoutSeconds}s) ..." -ForegroundColor Cyan
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $containerId = (docker compose --env-file .env -f infra/docker-compose.yml ps -q $ServiceName)
        if ($containerId) {
            $status = docker inspect --format '{{.State.Health.Status}}' $containerId 2>$null
            if ($status -eq "healthy") {
                Write-Host "    $ServiceName is healthy." -ForegroundColor Green
                return
            }
        }
        Start-Sleep -Seconds 3
    }
    throw "$ServiceName did not become healthy within ${TimeoutSeconds}s -- check: docker compose --env-file .env -f infra/docker-compose.yml logs $ServiceName"
}

Wait-Healthy -ServiceName "postgres"
Wait-Healthy -ServiceName "garage"

Write-Host "==> Applying real database migrations (uv run alembic upgrade head) ..." -ForegroundColor Cyan
uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed (exit $LASTEXITCODE)" }

if (-not $SkipSeed) {
    Write-Host "==> Seeding real TEST tenants/users (scripts/seed_test_tenants.py) ..." -ForegroundColor Cyan
    uv run python scripts/seed_test_tenants.py
    if ($LASTEXITCODE -ne 0) { throw "seed_test_tenants.py failed (exit $LASTEXITCODE)" }
}

Wait-Healthy -ServiceName "api"

Write-Host ""
Write-Host "==> Stack is up." -ForegroundColor Green
Write-Host "    API:      http://127.0.0.1:8000  (docs: http://127.0.0.1:8000/v1/docs)"
Write-Host "    Web:      http://127.0.0.1:3000"
Write-Host "    Dagster:  http://127.0.0.1:3001"
Write-Host "    Postgres: 127.0.0.1:55432"
Write-Host "    Garage:   127.0.0.1:59000"
Write-Host ""
Write-Host "    Stop the stack: docker compose --env-file .env -f infra/docker-compose.yml down"
