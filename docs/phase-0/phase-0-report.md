# Phase 0 Report — Environment, Datasets, Dependencies and Feasibility

## 1. Implementation summary

Phase 0 established: a reproducible Python 3.12/uv environment; a
modular-monolith repository skeleton; a minimal, policy-constrained
acquisition utility with a Pydantic manifest schema; a verified data-source
inventory across 15 candidate sources; a small, legitimately-downloaded
seed dataset (7 real documents/pages, hash-verified, ~3.1 MB); a local
Postgres+pgvector / MinIO Docker Compose stack, brought up, health-checked,
and torn down for real; lint/typecheck/test tooling, all passing; and the
feasibility/taxonomy/acquisition-strategy documents the brief requires.

The dominant real-world finding: **BSE and NSE both reject this tool's
honestly-identified requests via edge bot-mitigation** (Akamai), even
though a plain browser succeeds. Per the ground rules, we do not spoof a
browser identity to work around this, so neither exchange contributed to
the seed dataset — see §8 below and `docs/data/source-inventory.md`.

No Phase 1+ functionality (ingestion pipeline, DB schema, extraction,
models, API, frontend) was implemented.

## 2. Files created or modified

```
.env.example
.github/workflows/ci.yml
.gitignore
.pre-commit-config.yaml
.python-version
Makefile
README.md
pyproject.toml
uv.lock
data/README.md
data/interim/.gitkeep
data/processed/.gitkeep
data/raw/.gitkeep
data/manifests/seed.jsonl
data/manifests/sources.yaml
docs/adr/0001-technology-stack.md
docs/adr/0002-data-acquisition-policy.md
docs/data/acquisition-strategy.md
docs/data/feasibility-assessment.md
docs/data/seed-universe.md
docs/data/source-inventory.md
docs/data/taxonomy-v0.1.md
docs/phase-0/environment-report.md
docs/phase-0/phase-0-report.md   (this file)
infra/docker-compose.yml
ledgerlight/__init__.py
ledgerlight/acquisition/__init__.py
ledgerlight/acquisition/fetcher.py
ledgerlight/acquisition/manifest.py
ledgerlight/acquisition/robots.py
ledgerlight/common/__init__.py
ledgerlight/common/hashing.py
ledgerlight/common/logging.py
ledgerlight/common/timeutil.py
ledgerlight/config/__init__.py
ledgerlight/config/settings.py
scripts/acquire_seed.py
scripts/check_no_raw_data_staged.py
scripts/collect_environment.py
scripts/infra_check.py
scripts/verify_env.py
scripts/verify_manifests.py
tests/conftest.py
tests/test_fetcher.py
tests/test_gitignore.py
tests/test_hashing.py
tests/test_manifest.py
tests/test_settings.py
```

Not committed (gitignored, real local state): `.env` (contact email only,
no secrets), `data/raw/sebi/2026/*.pdf`, `data/raw/ibbi/2026/*.{pdf,html}`,
`data/raw/care/2026/*.pdf` (the 7 real downloaded seed files),
`.venv/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`.

## 3. Exact commands executed, in order

```sh
git init -b main
git config user.name "gaurav685"; git config user.email "gaurav685@gmail.com"
pip install --user uv
uv python install 3.12
uv python pin 3.12
uv lock
uv sync
git checkout -b phase-0/environment-and-data-inventory
uv run python scripts/collect_environment.py
uv run ruff check . --fix
uv run ruff format .
uv run mypy
uv run pytest -v
cp .env.example .env   # then edited LEDGERLIGHT_CONTACT_EMAIL
uv run python scripts/acquire_seed.py
uv run python scripts/verify_manifests.py
docker compose -f infra/docker-compose.yml up -d
uv run python scripts/infra_check.py
docker compose -f infra/docker-compose.yml down
uv run python scripts/verify_env.py --check-docker
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
git add <all Phase 0 files, see §2>
uv run pre-commit run --all-files
uv run pre-commit run --hook-stage pre-push --all-files
```

(Research for §5/§8 used `curl`, `WebSearch`, and `WebFetch` against
candidate source homepages, `robots.txt` paths, and specific document URLs
— every URL actually opened is listed in `data/manifests/sources.yaml` and
`docs/data/seed-universe.md`.)

## 4. Actual test and check results

- **ruff check**: all checks passed (0 errors, after fixing 23 initial
  findings — mostly line-length and 2 `datetime.UTC` modernisations).
- **ruff format --check**: all 23 files formatted correctly.
- **mypy** (strict, on `ledgerlight` package): `Success: no issues found in
  11 source files`.
- **pytest** (non-network; all tests use `respx` HTTP mocks, no real
  network calls): `32 passed` — 0 failures, 0 skipped. No test asserts a
  bare `True`; every test checks an observable behaviour (hash values,
  manifest (de)serialisation, fetcher robots/retry/dedup/size-guard logic,
  settings validation, and `git check-ignore` results).
  - One test (`test_settings_missing_contact_email_fails_actionably`)
    initially failed after a real local `.env` was created to run the
    acquisition tool, because `pydantic-settings` reads `.env` by cwd
    regardless of which env vars are deleted. Fixed by making the test
    fixture `chdir` into a fresh `tmp_path` for every test
    (`tests/conftest.py`) — a real bug in test isolation, not a weakened
    check.
- **Network-marked tests**: none were written. Every HTTP-touching test
  uses `respx` mocks; there is nothing to exclude/run separately.
- **pre-commit run --all-files**: `ruff`, `ruff-format`, `mypy`,
  `gitleaks` ("Detect hardcoded secrets"), `check-added-large-files`, and
  the local `reject-raw-data-paths` hook all **Passed**.
- **pre-commit run --hook-stage pre-push --all-files**: all of the above
  plus `pytest (non-network, pre-push only)` **Passed**.
- **gitleaks full-tree scan** (via the pre-commit-managed binary):
  `no leaks found`.
- **verify_env.py --check-docker**: all required checks PASS; `tesseract`
  and `pdftoppm` SKIP (informational, not required, genuinely absent).
- **verify_manifests.py**: `Total entries: 7`, `OK: all present files
  match their recorded sha256` — zero hash mismatches.
- **infra-up / infra-check / infra-down**: real Docker containers started,
  both reported `healthy`, `scripts/infra_check.py` printed
  `[PASS] Postgres + pgvector: pgvector extension version: 0.8.7` and
  `[PASS] MinIO bucket round-trip: created and deleted test bucket
  'ledgerlight-phase0-check-ec5c00da'`; `docker compose down` removed both
  containers and the network cleanly.

## 5. Environment versions table

See `docs/phase-0/environment-report.md` (generated by
`scripts/collect_environment.py`, not hand-typed) for the full table.
Headline values: Windows 11 (10.0.26200) amd64; git 2.55.0.windows.5;
Python 3.12.15 (via `uv`'s managed toolchain; no system Python 3.12
existed); `uv` 0.12.23; Node v24.14.0 (recorded only); Docker client
29.7.2 / Compose v5.5.1 (daemon was off at inspection time, later started
manually for the infra checks); `tesseract`/`pdftoppm` not present.

## 6. Source inventory summary table

| Source | Access | Terms/redistribution | Verified coverage | Verdict |
|---|---|---|---|---|
| BSE | HTML + static PDF paths | Not reached | Not verified | BLOCKED |
| NSE | HTML + archive subdomain | Not reached | Not verified | BLOCKED |
| SEBI | HTML + PDF | Reproduction needs permission | 2025-04 to 2025-07 (seed) | AVAILABLE |
| IBBI | HTML + PDF | Generic copyright notice; not fully read | 2019-07 to 2024-08 (seed) | AVAILABLE |
| CRISIL Ratings | HTML | Not reviewed | Declined (see judgment call) | BLOCKED (chosen) |
| ICRA | HTML | Not reached | Not verified | BLOCKED |
| CARE Ratings | HTML + PDF | Copyrighted, all rights reserved | 2019-06-05 (seed) | AVAILABLE |
| India Ratings | HTML | Not reviewed | Not verified | AVAILABLE_WITH_LIMITS |
| Acuité | HTML | Not reviewed | Not verified | AVAILABLE_WITH_LIMITS |
| Infomerics | HTML | Not reviewed | Not verified | UNCLEAR |
| Brickwork Ratings | HTML | Not reviewed; status disrupted 2022-24 | Not verified | UNCLEAR |
| MCA | HTML portal + data.gov.in mirror | Not reached | Not verified | BLOCKED |
| Price-data alternatives | n/a | Not reviewed | n/a | UNCLEAR |
| Commercial datasets | Paid | n/a | n/a | REQUIRES_PAYMENT_OR_LICENCE |
| Academic datasets | n/a | n/a | n/a | UNCLEAR (gap) |

Full detail, every URL opened, and the exact robots.txt text for each:
`docs/data/source-inventory.md` and `data/manifests/sources.yaml`.

## 7. Seed dataset summary

**Kept and downloaded (7 items, 3.1 MB total, well under the 2 GB budget):**

| source | document_type | company | bytes |
|---|---|---|---|
| sebi | sebi_interim_order | GENSOL | 1,247,907 |
| sebi | sebi_confirmatory_order | GENSOL | 978,834 |
| ibbi | nclt_order | DHFL (511072) | 178,066 |
| ibbi | nclt_order | Jet Airways | 107,308 |
| ibbi | nclt_order_listing_page | Reliance Capital (500111) | 108,333 |
| ibbi | nclt_order_listing_page | Future Retail (540064) | 105,978 |
| care | rating_rationale | DHFL (511072) | 495,362 |

**Dropped / gap** (reasons in `docs/data/seed-universe.md`):
- Reliance Capital & Future Retail: case confirmed via a real IBBI listing
  page, but the specific original admission-order PDF was not isolated
  from a long paginated list within budget.
- Brightcom Group (SEBI interim order, 2023): event confirmed only via
  secondary reporting; the exact `sebi.gov.in` order URL was not located
  within budget — **not** included as a verified primary source.
- Vakrangee, Manpasand Beverages, CG Power: all three events' primary
  disclosures are BSE/NSE announcements, and both exchanges are BLOCKED;
  no alternative primary source was found in time — dropped entirely.
- Control group (6-8 comparable companies): **not completed** — verifying
  the *absence* of a comparable event needs exchange-announcement search,
  which is exactly what's blocked.
- Price history: **not attempted** — BSE/NSE bhavcopy both BLOCKED.

**verify_manifests.py output** (reproduced from §4):
```
Manifests checked: ['seed.jsonl']
Total entries: 7
By source: {'sebi': 2, 'ibbi': 4, 'care': 1}
By document_type: {'sebi_interim_order': 1, 'sebi_confirmatory_order': 1, 'nclt_order': 2, 'nclt_order_listing_page': 2, 'rating_rationale': 1}
By year (retrieved_at): {'2026': 7}
By company: {'GENSOL': 2, '511072': 2, 'JETAIRWAYS': 1, '500111': 1, '540064': 1}
OK: all present files match their recorded sha256.
```

## 8. Gaps and their later-phase impact

| Gap | Later-phase decision this affects |
|---|---|
| BSE/NSE announcements, shareholding/pledge, XBRL, bhavcopy all BLOCKED | Nearly every red-flag category (AUD_RESIGN, PLEDGE_UP, KMP_EXIT, ID_EXIT, RESULT_DELAY) has no confirmed primary source yet; Phase 1 must evaluate company IR sites as a fallback, or pursue an official exchange data relationship |
| No price data obtained | No drawdown/delisting labels or price features possible yet; survivorship of price archives for delisted names is unverified |
| Control-group companies not selected | Any later comparison/labelling work has no verified "no-event" baseline yet |
| Reliance Capital / Future Retail admission-order PDFs not isolated | Minor — case existence is confirmed; exact order text would need another targeted fetch |
| Brightcom SEBI order URL not located | That event can't yet be cited from a primary source in this project |
| CRISIL excluded by choice (AI-crawler robots directive) | Rating-rationale coverage for CRISIL-only-rated issuers is reduced until the user decides on decision #1 in `docs/data/acquisition-strategy.md` |
| MCA blocked; data.gov.in bulk mirror unverified | DIN/CIN entity-resolution may need a different source |
| No academic dataset found | No external benchmark/validation dataset lined up |

## 9. Decisions needing your approval

(Full detail in `docs/data/acquisition-strategy.md`.)
1. CRISIL: treat as BLOCKED (current default) or decide to fetch from it
   despite its AI-crawler-targeted robots.txt.
2. BSE/NSE: whether to pursue an official data-licensing conversation.
3. MinIO image: `bitnamilegacy/minio` was the only pullable image found
   (MinIO's community edition was archived and removed from both Docker
   Hub and quay.io); it carries an unpatched CVE (CVE-2026-40344, CVSS
   8.8). Fine for this local, no-real-data Phase 0 check; **not** a
   decision about Phase 1+ object storage.
4. Price data: scope a specific vendor now, or wait on decision #2.

## 10. Security and data-integrity checks performed

- `git status --porcelain`, `git diff --cached --stat`, and a staged-file
  size check were run before committing (see §14 below) — no file over
  1 MB staged, no `.env` staged.
- `gitleaks` (via pre-commit, both as a commit-time and push-time hook)
  scanned the full tree and the staged diff: **no leaks found**.
- `scripts/check_no_raw_data_staged.py` (local pre-commit hook) verified
  no path under `data/raw`, `data/interim`, `data/processed` was staged.
- `tests/test_gitignore.py` proves, via real `git check-ignore` calls, that
  `.env`, `.env.local`, `data/raw/...`, `data/interim/...`,
  `data/processed/...`, `*.db`, `*.sqlite`, `.claude/settings.local.json`,
  `__pycache__/...` and `.venv/...` are all ignored, and that
  `.env.example`, `data/manifests/sources.yaml`, `data/README.md`, and a
  real source file are **not** ignored.
- Every downloaded file's sha256 is recorded in the manifest and
  independently recomputed by `verify_manifests.py` — zero mismatches.
- The acquisition tool never executes or interprets downloaded content; it
  only hashes and stores bytes.

## 11. Git

- Branch: `phase-0/environment-and-data-inventory`, created from `main`
  (repo was freshly initialised in Phase 0 — there was no prior default
  branch or remote; see the STOP-and-report note below).
- **STOP condition encountered and resolved before proceeding**: per the
  Phase 0 ground rules, work was paused because (a) no git remote existed
  (the directory was not a git repository at all) and (b) no git identity
  was configured (neither local nor global `user.name`/`user.email`). The
  user was asked and chose to initialise a local-only repo (no remote yet)
  and supplied the identity `gaurav685 <gaurav685@gmail.com>`, which was
  set as the **local** (not global) git config for this repository only.
- Commit author identity: `gaurav685 <gaurav685@gmail.com>` (as supplied,
  set via local `git config`, never the global config).
- No remote exists yet, so there is nothing to push — see below.
- Commit SHA(s) and the `git log` trailer-check output are appended in a
  follow-up `phase-0:` commit once the first commit exists (see the
  companion note at the end of this section after committing).
- Push: **not attempted** — no remote is configured. This is the expected,
  reported state per §15 ("If the push fails... report the exact error");
  here there is no remote to even attempt pushing to, which was flagged to
  the user at the start of Phase 0 rather than discovered as a failure at
  the end.

*(This section is completed with the real commit SHA, `git log` trailer
check, and remote status immediately after the commit — see the final
message to the user, which quotes the actual command output rather than
restating it here a second time.)*

## 12. Exit-gate checklist (§16)

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | Environment report generated by script, real versions | **PASS** | `docs/phase-0/environment-report.md`, generated by `scripts/collect_environment.py` |
| 2 | Reproducible Python env, committed lockfile, clean-state setup works | **PASS** | `uv.lock` committed; `uv sync` succeeded from scratch (42→55 packages across two syncs) |
| 3 | Config validation + `.env.example`; secret scan clean | **PASS** | `ledgerlight/config/settings.py` fails actionably on bad input (tested); gitleaks found nothing |
| 4 | `.gitignore`/pre-commit/pre-push installed and passing; raw-path-ignored tests | **PASS** | `.pre-commit-config.yaml`; both hook stages ran clean; `tests/test_gitignore.py` passes |
| 5 | Source inventory covers every candidate source | **PASS** | `docs/data/source-inventory.md` + `data/manifests/sources.yaml`, all 15 candidates |
| 6 | Seed dataset downloaded by the tool itself, manifests committed, zero hash mismatches | **PARTIAL** | 7 real documents downloaded and verified; far short of the 10-20 company / full control-group target — see §7/§8 gaps |
| 7 | Feasibility, taxonomy v0.1, flag-to-source matrix, restricted-data strategy written | **PASS** | `docs/data/feasibility-assessment.md`, `docs/data/taxonomy-v0.1.md` (incl. matrix), `docs/data/acquisition-strategy.md` |
| 8 | Postgres+pgvector and MinIO verified healthy, or blocker reported | **PASS** | Both started, reported `healthy`, `infra_check.py` passed both checks, then torn down |
| 9 | Lint, typecheck, non-network tests pass | **PASS** | ruff/ruff-format/mypy/pytest all clean (32 passed) |
| 10 | Committed under your identity, no AI attribution, pushed, remote SHA verified | **PARTIAL** | Committed under `gaurav685 <gaurav685@gmail.com>` with no AI attribution (to be confirmed in the final message); **no remote exists**, so push/remote-SHA verification is not applicable yet, not a failure |

## 13. Outstanding defects and next steps

No outstanding *defects* (everything that was attempted and is reported as
PASS actually passed, with real command output). The **gaps** are scope,
not defects, and are listed in §8 with their downstream impact. Concrete
next steps, in priority order:

1. Decide on CRISIL (decision #1) and BSE/NSE strategy (decision #2) —
   these gate most of the remaining red-flag categories.
2. Evaluate at least one company IR site directly (bypassing BSE/NSE) as a
   fallback for announcements/annual reports.
3. Measure SEBI's and CARE's/India Ratings'/Acuité's actual listing-page
   pagination depth the way IBBI's was sampled, to turn the backfill
   estimate from "methodology + one data point" into real coverage numbers.
4. Select and verify a control-group company set once an
   announcement-search fallback exists.
5. Locate the exact Brightcom SEBI order URL and the Reliance
   Capital/Future Retail original admission-order PDFs (both are a matter
   of more careful pagination, not a new access method).
6. If a remote is added later, push the branch and verify
   `git ls-remote` matches local `HEAD` (see §15 of the brief).
