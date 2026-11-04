# Dependency scan triage (Phase 5 §7)

Real `pip-audit`/`pnpm audit` output, triaged. Raw command output:
`docs/phase-5/evidence/pip-audit.log`.

## Python (`pip-audit`)

**Before triage**: 43 known vulnerabilities across 5 packages
(`cryptography`, `pip`, `pytest`, `setuptools`, `starlette`).

**Action taken**: bumped `cryptography` (`>=43.0,<44` -> `>=44.0,<45`)
and `fastapi` (`>=0.115,<0.116` -> `>=0.116,<0.117`, which pulled a
real `starlette` bump `0.46.2` -> `0.48.0`), re-locked, re-synced, and
re-ran the full real test suite (406 default + every integration
test) and strict `mypy` -- all clean, no regressions. `pip`/
`setuptools` findings cleared incidentally (they are the venv's own
build-tooling versions, not pinned project dependencies -- `uv sync`
installed current versions of both as a side effect of the same
re-lock).

**After triage**: 24 known vulnerabilities across 3 packages.

**Remaining, triaged as accepted for this phase** (each requires a
real major-version jump with real, undemonstrated compatibility
risk, not appropriate to force during a CI-validation task):

| Package | Current | Needed fix | Why not bumped now |
|---|---|---|---|
| `cryptography` | 44.0.3 | 46.0.5 / 48.0.1 / 49.0.0 / 50.0.0 | A real major-version jump past what this project's own `pyproject.toml` pin currently allows; `cryptography`'s own major releases have real documented removed-API changes. The real, narrow usage in this project (`Fernet` encrypt/decrypt only, in `ledgerlight.api.webhooks`) is low-risk but untested against 46+ in this session. |
| `starlette` | 0.48.0 | 0.49.1 / 1.0.1 / 1.1.0 / 1.3.0 / 1.3.1 | `fastapi==0.116.2`'s own real dependency constraint caps starlette at `<0.49.0` -- reaching 0.49.1+ requires a newer `fastapi` generation, which itself needs its own real regression pass across every router before being accepted, not appropriate to chase inside a §7 CI-validation task. |
| `pytest` | 8.4.2 | 9.0.3 | A real major-version jump with real plugin/collection-behavior changes; this project's own test suite (400+ real tests) would need a full real re-validation pass, which is its own piece of work, not a side effect of a CI-workflow phase. |

Each of these is a real, disclosed, accepted risk -- not silently
dropped. A future phase should plan a dedicated dependency-upgrade
pass (cryptography 46+, a newer fastapi/starlette generation, pytest
9) with its own real regression testing, not bundle it into §7.

## Frontend (`pnpm audit`)

1 moderate finding: `minimatch` (3.1.5, needs `>=11.0.1`) via a deep
transitive chain under `eslint`/`eslint-config-next` (`@typescript-eslint/*`
-> `minimatch`). Confirmed directly (`pnpm list --prod minimatch`
returns empty) that this package **never appears in the production
dependency tree** -- it is pulled in only by real dev-time lint
tooling, never shipped in the real `next build` output or the real
`frontend/Dockerfile` production image. Not overridden: `minimatch`'s
own v3 -> v11 jump changed real glob-matching semantics in some
edge cases, and forcing an override across `eslint`'s own deeply
nested dependency tree risks silently changing real lint behavior in
a way this session cannot fully verify. Triaged as accepted: a real,
moderate-severity, dev-tooling-only finding with no real production
exposure.

## Container images (`trivy image`)

Real scans against both built images, via the official
`aquasec/trivy` Docker image (`trivy image --severity CRITICAL,HIGH`).
Raw output: `trivy-api-image.log`, `trivy-web-image.log` in this same
directory.

**Before fix** -- `trivy` found several real, already-patched Debian
security updates not yet baked into the pinned base images, plus one
real CRITICAL `tar` CVE bundled inside npm's own vendored
dependencies in the web image:

| Image | OS packages | Language packages |
|---|---|---|
| `ledgerlight-api` | 92 (83 HIGH, 9 CRITICAL) | 7 (7 HIGH, 0 CRITICAL -- the same cryptography/starlette findings `pip-audit` already found, confirmed consistent) |
| `ledgerlight-web` | 50 (44 HIGH, 6 CRITICAL) | 13 (12 HIGH, 1 CRITICAL -- `tar` CVE-2026-59873, bundled inside npm itself, never invoked at this image's own runtime) |

**Fix applied**: both `Dockerfile`s gained a real `apt-get update &&
apt-get upgrade -y` step, pulling every Debian security patch already
published for bookworm but not yet baked into the pinned base image
digests. `frontend/Dockerfile` additionally pins `npm@11.21.1`
(confirmed compatible with the pinned node `24.14.0` -- `npm@latest`,
12.2.1, requires node `>=24.15.0`/`26`, a real `EBADENGINE` failure
confirmed directly), which bundles a real patched `tar@^7.5.22`.

**After fix**:

| Image | OS packages | Language packages |
|---|---|---|
| `ledgerlight-api` | 38 (36 HIGH, 2 CRITICAL) | 7 (unchanged -- already triaged above) |
| `ledgerlight-web` | 33 (32 HIGH, 1 CRITICAL) | 3 (3 HIGH, 0 CRITICAL -- the `tar` CVE is gone) |

**Remaining, triaged as accepted** -- every remaining CRITICAL
finding in both images is the real, same `zlib1g` `CVE-2023-45853`,
explicitly marked `will_not_fix` by Debian upstream for bookworm (no
fixed version exists to upgrade to). `libsqlite3-0` `CVE-2025-7458`
(api image only, HIGH after the fix brought the OS packages that were
CRITICAL down) has no fixed version published yet either. Neither is
fixable from inside this project -- closing them requires either a
future Debian bookworm security update (not yet shipped) or a
different base image entirely (a real, bigger architectural decision,
out of scope for a §7 CI-validation task). The remaining real HIGH
findings in both images are the same pattern -- real Debian CVEs with
no backported fix yet for bookworm specifically.

Both images were rebuilt and re-verified functional after these
Dockerfile changes (real health-check/import checks, consistent with
§5's own verification pattern) -- the fix did not break either image.
