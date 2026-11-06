# Local setup on Windows

Phase 5 §10. First-time machine setup for this project on Windows --
once this is done, day-to-day startup/shutdown is `docs/ops/
startup-shutdown.md`. Every step below is the real path this project
was actually set up and run on throughout Phase 0-5, not a generic
"it should work" guide.

## Prerequisites

- **Docker Desktop**, with WSL2 backend. Real memory note: this
  project's own real local stack (Postgres + Garage, plus the `api`/
  `worker`/`web` images when built) needs real headroom beyond
  whatever else is running. This session repeatedly hit real
  `vmmemWSL`-driven OOM kills during Docker builds under memory
  pressure; the real, confirmed fix each time was:
  ```powershell
  wsl --shutdown
  ```
  followed by restarting Docker Desktop and this project's own
  persistent containers:
  ```powershell
  docker start ledgerlight-phase0-postgres-1 ledgerlight-phase0-garage-1
  ```
- **Python 3.12+** and **uv**. This project's own `uv` was installed
  as a real pip package into the system Python (`pip install uv`),
  NOT the standalone curl installer -- confirmed via `pip show uv`
  succeeding while a bare `uv` on `PATH` does not. Every real command
  in this repo is therefore invoked as `python -m uv run ...`, never
  a bare `uv ...` -- scripts and docs follow that same convention.
- **Node.js** (matching `frontend/Dockerfile`'s own pinned version)
  and **corepack** (ships with Node). On a machine with no admin
  rights available (this project's own real dev host), install
  corepack's shims to a user-writable directory rather than the
  default global path, so `pnpm` needs no elevation -- see ADR 0009
  decision 5. `frontend/package.json`'s own `packageManager` field
  pins the real `pnpm` version; `corepack use pnpm@<that version>`
  (or simply running `pnpm` once corepack is enabled) fetches it.
- **PowerShell** (the primary shell this project's own scripts
  target -- `scripts/dev.ps1`).

## First-time setup

```powershell
git clone <this repo>
cd "ledger light"
cp .env.example .env
# Fill in LEDGERLIGHT_CONTACT_EMAIL -- required. Most other values
# already have a real, dev-only default that works as-is, EXCEPT
# LEDGERLIGHT_GARAGE_RPC_SECRET / LEDGERLIGHT_GARAGE_ADMIN_TOKEN, which
# ship blank and MUST be set -- docker-compose.yml's own `:?` checks
# refuse to start Garage without them (confirmed directly -- a real,
# previously-undocumented gap this phase's clean-install test found;
# that `:?` error message itself suggests `openssl`, not available in
# a plain PowerShell prompt with no WSL/Git-Bash on PATH):
python -m uv run python -c "import secrets; print(secrets.token_hex(32))"
# run it twice; paste one result as LEDGERLIGHT_GARAGE_RPC_SECRET and
# the other as LEDGERLIGHT_GARAGE_ADMIN_TOKEN in .env
```

```powershell
python -m uv sync --extra ocr
```
`--extra ocr` is required every time -- a plain `uv sync` silently
uninstalls `rapidocr-onnxruntime`/`opencv-python`/`pyclipper`/`shapely`
from the venv, which this project's own real OCR path needs (confirmed
directly: `tests/test_ocr_engine.py` skips instead of running without
it).

```powershell
New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\corepack-shims" | Out-Null
corepack enable --install-directory "$env:LOCALAPPDATA\corepack-shims"
$env:PATH = "$env:LOCALAPPDATA\corepack-shims;$env:PATH"   # add to your real profile to persist
cd frontend
pnpm install
cd ..
```
A bare `corepack enable` (no `--install-directory`) does not reliably
put a real, resolvable `pnpm` on `PATH` in every shell -- see the
real gotcha below.

## Bringing up the full stack

```powershell
.\scripts\dev.ps1
```
Builds and starts `postgres`/`garage`/`api`/`worker`/`web`, waits for
real health checks, runs real migrations, seeds the real TEST
tenants. See `docs/ops/startup-shutdown.md` for the manual
step-by-step equivalent and for day-to-day operation (shutdown,
health checks, logs).

## Provisioning object storage (first run only)

```powershell
python -m uv run python scripts/garage_provision.py
```
Idempotent -- running it again when `LEDGERLIGHT_S3_ACCESS_KEY_ID` is
already in `.env` is a real no-op (Garage cannot print an existing
key's secret again).

## Running tests

```powershell
python -m uv run --extra ocr pytest -q                   # default suite
python -m uv run --extra ocr pytest -q -m integration     # needs the real local stack up
```

## Known Windows-specific gotchas (all confirmed directly this project)

- **Path translation in Git Bash**: a command starting with a single
  `/` (e.g. `docker exec <container> /garage status`) gets silently
  rewritten to a Windows path by Git Bash's own POSIX-path emulation,
  producing a confusing "no such file or directory" naming a
  `C:\Program Files\Git\...` path. Fix: prefix the command with
  `MSYS_NO_PATHCONV=1`.
- **`trivy image` needs the Docker socket mounted explicitly** --
  `-v /var/run/docker.sock:/var/run/docker.sock` -- to reach locally
  built images at all; without it, it fails over to registry/
  containerd/podman lookups and errors out. Also mount a persistent
  named volume for its vulnerability DB cache (`-v
  trivy-cache:/root/.cache/trivy`) -- the real download is large and
  slow on a constrained connection, and otherwise re-downloads on
  every single scan.
- **`node:*-bookworm-slim` already ships a real `node` user at uid/gid
  1000** -- `frontend/Dockerfile` reuses it rather than creating a
  second identity at the same uid/gid, which fails
  (`groupadd: GID '1000' already exists`).
- **A bare `pnpm` may not resolve at all**, even after `corepack
  enable` -- confirmed directly: `corepack pnpm <cmd>` always works,
  but a plain `pnpm <cmd>` can fail with `command not found` in a
  shell that never got corepack's own shims on its `PATH`. This
  matters for anything that itself spawns a bare `pnpm` as a *child*
  process and can't be prefixed externally -- e.g. Playwright's own
  `webServer` config runs `pnpm start` internally, and that spawn
  failed with `'pnpm' is not recognized...` even though `corepack
  pnpm test:e2e` was the very command running it. Fix: materialize
  real shims onto a real directory and put that directory on `PATH`
  for the session:
  ```powershell
  corepack enable --install-directory "$env:LOCALAPPDATA\corepack-shims"
  $env:PATH = "$env:LOCALAPPDATA\corepack-shims;$env:PATH"
  ```
  (the `--install-directory` target must already exist -- `corepack
  enable` does not create it).
