# ADR 0001: Technology Stack (Phase 0)

## Status
Accepted (Phase 0).

## Context
Phase 0 needed a reproducible Python environment, a minimal acquisition
utility, and local infra (Postgres+pgvector, MinIO), per the brief's
selected stack: Python 3.12 managed with `uv`, Pydantic v2 /
pydantic-settings, httpx + tenacity + structlog, pytest/ruff/mypy, and
Docker Compose for Postgres+pgvector and MinIO.

## What was actually found on this machine (see `docs/phase-0/environment-report.md`)
- Python: only 3.11.5 was pre-installed; no `python3.12` on PATH.
- `uv`: not pre-installed.
- Docker: client present, daemon was not running at environment-inspection
  time (it was manually started during Phase 0 to run the infra checks —
  see `docs/phase-0/phase-0-report.md`).
- Node: v24.14.0 present (recorded only, per instructions — no Node/Next.js
  app scaffolded in Phase 0).

## Decisions and deviations

1. **`uv` was installed user-scoped** via `pip install --user uv`, not a
   system-wide install. This is not a "system package change" in the
   sense the ground rules restrict (no admin rights used, no OS package
   manager touched, fully reversible by deleting the user-site package).
2. **Python 3.12 was obtained via `uv`'s own managed-toolchain feature**
   (`uv python install 3.12`), which downloads an isolated CPython build
   into `uv`'s own cache directory — not a system Python install, not
   registered with the OS, doesn't touch the pre-existing 3.11
   installation. This satisfies "Python 3.12 managed with uv" from the
   brief without any system-wide change.
3. **No deviation was needed for the rest of the stack** — Pydantic v2,
   pydantic-settings, httpx, tenacity, structlog, pytest, ruff, mypy all
   installed and ran exactly as specified; `uv.lock` is committed.
4. **Docker image pins required real research, not the originally
   assumed tags** (see ADR 0003 for the object-storage finding
   specifically — MinIO was later replaced with Garage in Correction 1):
   the brief asked for "pinned tags," and two separate attempts at
   guessing a plausible-looking tag/digest were caught and corrected
   before being used, in favour of tags actually confirmed pullable.
5. **Dev-only dependencies added beyond the original list**: `psycopg[binary]`,
   `boto3` and (Correction 1) `truststore` were added (dev/main groups) because
   `scripts/infra_check.py` needs the first two to actually talk to
   Postgres and the object store, and `truststore` fixes a real TLS chain
   issue — this is "Phase 0
   code actually uses it," not speculative tooling.

## Consequences
- Anyone cloning this repo needs only `uv` on PATH; `uv sync` will fetch
  the pinned Python 3.12 toolchain itself. No separate Python 3.12 install
  instructions are needed for contributors.
- The committed `uv.lock` pins all 42 resolved packages; `uv sync` from a
  clean clone is reproducible (verified in this phase — see
  `docs/phase-0/phase-0-report.md`).
