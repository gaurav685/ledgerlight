# GitHub Actions workflows -- local validation (Phase 5 §7)

Every workflow under `.github/workflows/` validated the only way
possible without a remote (`git remote -v` is empty -- see
`docs/release/release-gates.md`'s own new gate for why). **None of
these have ever run on GitHub's own hosted runners** -- state marked
UNVERIFIED until a first real push.

## actionlint

Ran against all 5 workflow files via the real, official
`rhysd/actionlint` Docker image (no `actionlint` binary installed on
this host):

```sh
docker run --rm -v "<repo>:/repo" --workdir /repo rhysd/actionlint:latest -color
```

**Result: zero findings, exit code 0**, against `backend.yml`,
`frontend.yml`, `security.yml`, `build.yml`, `deploy.yml`.

## backend.yml -- per-job real command results

| Step | Command | Result |
|---|---|---|
| Lint | `uv run ruff check . && uv run ruff format --check .` | Pass (307 files already formatted) |
| Typecheck | `uv run mypy` | Pass (150 source files, strict) |
| Migrate | `uv run alembic upgrade head` | Pass (idempotent, re-verified multiple times this session) |
| Test (non-integration) | `uv run pytest` | 406 passed |
| Test (integration) | `uv run pytest -m integration` | 268 passed, against the real local Postgres service (the same real container the workflow's own service-container config models) |

## frontend.yml -- per-job real command results

| Step | Command | Result |
|---|---|---|
| Lint | `pnpm lint` | Pass (0 findings) |
| Typecheck | `pnpm typecheck` (`tsc --noEmit`) | Pass (0 errors) |
| Build | `pnpm build` | Pass -- real production build, 13 real routes |
| Playwright smoke | `pnpm test:e2e` | 2 passed (login page renders its real form fields; real security headers present) -- against a real `next start` server, no backend involved |

## security.yml -- per-job real command results

| Job | Command | Result |
|---|---|---|
| `python-deps` | `pip-audit` against the real locked dependency set | 24 known vulnerabilities in 3 packages, triaged -- see `docs/phase-5/evidence/dependency-triage.md` and the raw `pip-audit.log` in this same directory. This phase's own fastapi/cryptography bump (`ca7be95`-era lock regen, this commit) already cut this from 43/5 to 24/3. |
| `frontend-deps` | `pnpm audit --audit-level=high` | 1 moderate finding (`minimatch`, dev-tooling-only, confirmed never in the real production dependency tree) -- triaged, see the same doc. `--audit-level=high` itself would pass clean (moderate is below that threshold). |
| `secrets-scan` | real `gitleaks` full commit-history scan (via the official `zricethezav/gitleaks` Docker image, mirroring what `gitleaks-action` runs) | **156 commits scanned, 0 leaks found** -- raw output in `gitleaks-full-history-phase5.log` in this same directory. |
| `container-scan` | real `docker build` for both images, then `trivy image` against each | **Real, significant findings, fixed in this phase.** Both `Dockerfile`s had real, already-patched Debian security updates not yet baked into their pinned base images; `frontend/Dockerfile`'s base also carried a real CRITICAL `tar` CVE bundled inside npm itself. Added a real `apt-get upgrade` step to both, plus a pinned `npm@11.21.1` in `frontend/Dockerfile` (`npm@latest` needs node `>=24.15.0`, one patch above this image's pin -- confirmed directly via a real `EBADENGINE` failure). Real before/after: api image 92->38 OS findings (9->2 CRITICAL); web image 50->33 OS + 13->3 language-package findings (6->1, 1->0 CRITICAL). Every remaining CRITICAL in both images is the same real `zlib1g` CVE, `will_not_fix` by Debian upstream -- genuinely not fixable here. Both rebuilt images re-verified functional (`python -c "import ledgerlight.api.app"`; a real `/login` page load). Full detail in `dependency-triage.md`; raw scan output in `trivy-api-image.log`/`trivy-web-image.log`. |

## build.yml -- per-job real command results

Both `docker build` invocations (root `Dockerfile` for `ledgerlight-api`,
`frontend/Dockerfile` for `ledgerlight-web`) were run directly on this
host multiple times throughout Phase 5 §5/§6/§7 -- every one
succeeded, confirmed by also running the real built containers (see
§5's own progress.md entry: a real cross-container login through the
real containerized web+api stack). `build.yml` itself was never run
through `docker/build-push-action` specifically (that requires a real
GitHub Actions runner environment), but the underlying real `docker
build` command it wraps is proven working.

## deploy.yml

Deliberately never run -- it is a disabled placeholder gated behind a
real `AWS_ACCESS_KEY_ID` repository secret that does not exist in this
environment (no AWS account -- see `infra/aws/README.md`). Its own
`check-credentials-configured` job logic was reviewed by hand; it
correctly short-circuits (`has_credentials=false`, a `::warning::`
annotation, the `deploy-smoke-test` job's `if:` condition never
satisfied) when the secret is absent, which is the real, current
state.
