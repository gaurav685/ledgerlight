# Phase 0 Report — Environment, Datasets, Dependencies and Feasibility

**This report covers Phase 0 plus Correction 1 (2026-10-25).** Correction 1
expanded the seed dataset via company IR sites and a newly-found NSE
price-data path, replaced MinIO with Garage to remove an unpatched CVE,
fixed a real TLS bug, and moved two secret-shaped values out of the
committed Garage config. Original Phase 0 content is preserved below where
still accurate; superseded claims are corrected, not silently dropped.

## 1. Implementation summary

**Phase 0** established a reproducible Python 3.12/uv environment, a
modular-monolith repository skeleton, a minimal policy-constrained
acquisition utility, a verified data-source inventory across 15 candidate
sources, and a small seed dataset (7 documents).

**Correction 1** fixed the three audit findings (seed too small, no git
remote, MinIO CVE) and, in the process of expanding the seed, found a real
working NSE price-data path and a real TLS bug — both documented and
fixed, not hidden:

- **Seed dataset**: grew from 7 to **237 distinct downloaded documents**
  across **15 companies** (9 event companies/cases + a vakrangee
  auditor-resignation set + 7 control companies, after one substitution —
  see §7), via SEBI, IBBI, CARE, 9 company IR sites, and a newly-discovered
  NSE bhavcopy path. Total size **48 MB**, well under the 2 GB budget.
- **`archives.nseindia.com`** — a third NSE subdomain, distinct from the
  BLOCKED `www.nseindia.com` and `nsearchives.nseindia.com` — is reachable
  with our honest, identifying User-Agent and serves real bhavcopy files.
  210 dates (Jan 2017 - Sep 2025) were attempted; 200 succeeded, 10 hit a
  non-trading-day 404 (handled as a normal skip, not an error).
- **A real bug was found and fixed**: `vakrangee.in`'s server sends an
  incomplete TLS certificate chain. The acquisition tool's HTTP client now
  verifies via `truststore` (the OS trust store, which completes the chain
  the same way a browser does) instead of a static certifi bundle — still
  full certificate verification, not a weakened check. See the ADR 0002
  addendum.
- **A real gitleaks finding was fixed properly, not suppressed**: Garage's
  `rpc_secret`/`admin_token` were initially hardcoded in the committed
  `infra/garage/garage.toml`. Both are now supplied via `GARAGE_RPC_SECRET`
  /`GARAGE_ADMIN_TOKEN` environment variables (Garage has supported this
  since v0.8.2), read from the gitignored `.env` — nothing secret-shaped
  is committed.
- **MinIO → Garage**: MinIO's community edition carries CVE-2026-40344
  (auth bypass) with no community-edition fix available anywhere (the fix
  shipped only in the commercial AIStor product). Replaced with Garage
  (`dxflrs/garage:v2.4.1`), confirmed pullable, no known CVE found. See
  `docs/adr/0003-object-storage.md`.
- **Git remote/push**: per your explicit instruction mid-session ("skip
  the github push in all the phases, I'll ask you to push in the end when
  the project is complete"), remote configuration and pushing are
  deliberately deferred in this and all future phases, not attempted and
  not reported as a failure. Commits remain local only.

No Phase 1+ functionality (ingestion pipeline, DB schema, extraction,
models, API, frontend) was implemented.

## 2. Files created or modified (Correction 1)

```
M  .env.example
M  .gitignore
M  .pre-commit-config.yaml
A  docs/adr/0003-object-storage.md
M  docs/adr/0001-technology-stack.md
M  docs/adr/0002-data-acquisition-policy.md
M  docs/data/acquisition-strategy.md
M  docs/data/feasibility-assessment.md
A  docs/data/manual-download-checklist.md
M  docs/data/seed-universe.md
M  docs/data/source-inventory.md
M  infra/docker-compose.yml
A  infra/garage/garage.toml
M  ledgerlight/acquisition/fetcher.py
A  ledgerlight/acquisition/import_local.py
M  ledgerlight/acquisition/manifest.py
M  ledgerlight/config/settings.py
M  Makefile
M  pyproject.toml
M  README.md
M  scripts/acquire_seed.py
A  scripts/import_local.py
M  scripts/infra_check.py
M  tests/test_fetcher.py
A  tests/test_import_local.py
M  tests/test_manifest.py
M  uv.lock
M  data/manifests/seed.jsonl
M  data/manifests/sources.yaml
```

(Original Phase 0 file tree — `ledgerlight/common/*`, `ledgerlight/config/__init__.py`,
`scripts/verify_env.py`, `scripts/verify_manifests.py`,
`scripts/collect_environment.py`, `scripts/check_no_raw_data_staged.py`,
`tests/conftest.py`, `tests/test_hashing.py`, `tests/test_gitignore.py`,
`tests/test_settings.py`, `docs/phase-0/environment-report.md`, CI
workflow, etc. — is unchanged and omitted here; see the original commit.)

Not committed (gitignored, real local state): `.env` (now also holds
generated `LEDGERLIGHT_GARAGE_RPC_SECRET`/`LEDGERLIGHT_GARAGE_ADMIN_TOKEN`),
237 real downloaded files under `data/raw/{sebi,ibbi,care,nse_archives,
vakrangee_ir,jetairways_ir,brightcom_ir,lichousing_ir,pnbhousing_ir,
spicejet_ir,dmart_ir,thermax_ir,suzlon_ir,mastek_ir}/`, `.venv/`,
`.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `.claude/` (harness
state — newly gitignored this round, previously only its
`settings.local.json` was).

## 3. Exact commands executed, in order (Correction 1)

```sh
git log -n 10 --format='%H %an <%ae>'; git remote -v; git branch -a   # §A.1
# INTENDED_IDENTITY: keep-current (no change); REPO_URL: deferred per user instruction
pip install --user uv   # (already installed from Phase 0)
curl ... archives.nseindia.com, nsearchives.nseindia.com, beta.bseindia.com, ...   # §B1 retest
# §B2 company IR site research: WebSearch + curl per company (see sources.yaml)
# §B5.1 manifest schema change:
#   edited ledgerlight/acquisition/manifest.py (+retrieval_method field)
#   migrated data/manifests/seed.jsonl to add retrieval_method="automated_fetch"
# §B5.2 import-local:
#   wrote ledgerlight/acquisition/import_local.py, scripts/import_local.py, tests/test_import_local.py
# §B5.3: wrote docs/data/manual-download-checklist.md
# §B7 price-data evaluation: grep -i PRICE_API_KEY .env .env.example (no match); WebSearch Alpha Vantage/Kaggle terms
docker image pull attempts: quay.io/minio/minio (401), minio/minio (removed), bitnamilegacy/minio (works but CVE)
docker pull dxflrs/garage:v2.4.1   # §C
trivy image --severity CRITICAL,HIGH dxflrs/garage:v2.4.1
# wrote infra/garage/garage.toml, updated infra/docker-compose.yml, docs/adr/0003-object-storage.md
docker compose --env-file .env -f infra/docker-compose.yml up -d
docker exec <garage> /garage status / layout assign / layout apply / key create / bucket create / bucket allow
uv run python scripts/infra_check.py
docker compose --env-file .env -f infra/docker-compose.yml down
uv add truststore
# edited ledgerlight/acquisition/fetcher.py (truststore-based TLS verify; HTTPStatusError for non-2xx)
uv run ruff check . --fix && uv run ruff format . && uv run mypy && uv run pytest -q
uv run python scripts/acquire_seed.py   # run 1: 7 fetched dup / 212 new / 10 not-found / 3 TLS errors (vakrangee)
uv run python scripts/acquire_seed.py   # run 2 (after truststore fix): 18 new / 202 dup / 10 not-found / 0 errors
uv run python scripts/verify_manifests.py
git add -A
uv run pre-commit run --all-files        # caught: mypy missing truststore stub dep; gitleaks flagged garage.toml secrets
# fixed both: added truststore to mypy hook's additional_dependencies;
# moved rpc_secret/admin_token from garage.toml into GARAGE_RPC_SECRET/GARAGE_ADMIN_TOKEN env vars
openssl rand -hex 32 / -hex 16   # generated real local secrets into .env (gitignored)
docker compose --env-file .env -f infra/docker-compose.yml up -d / down   # re-verified with env-var secrets
git add -A
uv run pre-commit run --all-files
uv run pre-commit run --hook-stage pre-push --all-files
uv run pre-commit run gitleaks --all-files --verbose
git status --porcelain; git diff --cached --numstat
git commit -m "phase-0: expand seed via company disclosures and harden storage image"
```

## 4. Actual test and check results

- **ruff check / ruff format --check**: all checks passed.
- **mypy** (strict): `Success: no issues found in 12 source files`.
- **pytest**: `43 passed` (32 from Phase 0 + 6 new manifest/fetcher tests
  for `retrieval_method` and the 404-not-written-to-disk behaviour + 5 new
  `test_import_local.py` tests). 0 failures, 0 skipped, no bare-`True`
  assertions.
- **acquire_seed.py, run 1** (before the TLS fix):
  `{'fetched': 212, 'skipped_duplicate': 5, 'blocked': 0, 'not_found': 10, 'errors': 3}`
  — the 3 errors were all `vakrangee_ir` SSL failures, diagnosed as a
  real server-side incomplete-chain issue, not a transient blip.
- **acquire_seed.py, run 2** (after switching to `truststore`):
  `{'fetched': 18, 'skipped_duplicate': 202, 'blocked': 0, 'not_found': 10, 'errors': 0}`
  — all three Vakrangee documents now succeed; **0 errors**.
- **import_local.py dry run** (no inbox): `Imported: 0 / Skipped: 0 / Rejected: 0`.
- **import_local.py test run** (one file + matching provenance row):
  `Imported: 1 (sample-report.pdf) / Skipped: 0 / Rejected: 0`; the
  no-provenance-row rejection path is covered by
  `tests/test_import_local.py::test_file_without_provenance_row_is_rejected`,
  not re-demonstrated live (it would require leaving an orphan file,
  which the real run cleans up).
- **verify_env.py --check-docker**: all required checks PASS;
  `tesseract`/`pdftoppm` SKIP (informational, genuinely absent).
- **verify_manifests.py** (final, after both acquire_seed runs):
  ```
  Total entries: 444
  By source: {'sebi': 8, 'ibbi': 12, 'care': 3, 'jetairways_ir': 2, 'brightcom_ir': 2,
  'lichousing_ir': 2, 'pnbhousing_ir': 2, 'spicejet_ir': 2, 'dmart_ir': 2, 'thermax_ir': 2,
  'suzlon_ir': 2, 'mastek_ir': 2, 'nse_archives': 400, 'vakrangee_ir': 3}
  OK: all present files match their recorded sha256.
  ```
  (444 counts every duplicate-skip bookkeeping entry too, per spec "record
  the skip"; **237 distinct files** actually exist on disk — confirmed by
  counting distinct `local_path` values, not estimated.)
- **infra-up / infra-check / infra-down**, run twice (once mid-correction
  with a fresh volume to prove the Garage layout-bootstrap path, once
  final after the secret-env-var fix): both times
  `[PASS] Postgres + pgvector: pgvector extension version: 0.8.7` and
  `[PASS] S3 (Garage) bucket round-trip: created, wrote/read/deleted an
  object in, and deleted bucket '...' via boto3`; containers torn down
  cleanly both times.
- **trivy image scan** (`dxflrs/garage:v2.4.1`, v0.76.1 installed
  user-locally, no sudo): 0 CRITICAL/HIGH findings reported — but because
  the image is a single-layer scratch build (no OS, no package manifest),
  trivy had nothing to scan, not "scanned and found clean." Documented
  honestly in ADR 0003, not oversold.
- **pre-commit run --all-files**: Passed — but only after two real fixes
  mid-session (mypy hook missing `truststore` in
  `additional_dependencies`; gitleaks correctly flagging the
  then-hardcoded Garage secrets). Neither fix weakened the check; both
  addressed the actual root cause.
- **pre-commit run --hook-stage pre-push --all-files**: all hooks
  including `pytest (non-network, pre-push only)` Passed.
- **Standalone gitleaks full-tree scan**: `no leaks found`.
- **git status --porcelain / git diff --cached --numstat**: clean —
  no `.env`, no `data/raw/*`, no `data/inbox/*` staged; largest staged
  file is `data/manifests/seed.jsonl` at 451 lines (well under 1 MB).

## 5. Environment versions table

Unchanged from Phase 0 — see `docs/phase-0/environment-report.md`. New
tool this round: `trivy` v0.76.1 (installed user-locally from the official
GitHub release zip, no sudo, no package manager).

## 6. Source inventory summary table

| Source | Access | Terms/redistribution | Verified coverage | Verdict |
|---|---|---|---|---|
| BSE (all subdomains) | HTML + static PDF paths | Not reached | Not verified | **BLOCKED** (retested 2026-10-25, unchanged) |
| NSE (`www.`/`nsearchives.`) | HTML + archives | Not reached | Not verified | **BLOCKED** (retested, now blocked even harder on `nsearchives.`) |
| **NSE bhavcopy (`archives.nseindia.com`)** | Direct static file paths | n/a (no HTML pages reachable, only files) | **2016 - 2025, 200 real files downloaded** | **AVAILABLE_WITH_LIMITS** (new finding) |
| SEBI | HTML + PDF | Reproduction needs permission | 2025-04 to 2025-07 + Sep-2019 CG Power doc | AVAILABLE |
| IBBI | HTML + PDF | Generic copyright notice | 2019-07 to 2024-08 | AVAILABLE |
| CRISIL Ratings | HTML | Not reviewed | Declined (judgment call, unchanged) | BLOCKED (chosen) |
| ICRA | HTML | Not reached | Not verified | BLOCKED |
| CARE Ratings | HTML + PDF | Copyrighted | 2019-06-05 | AVAILABLE |
| India Ratings / Acuité | HTML | Not reviewed | Not verified | AVAILABLE_WITH_LIMITS |
| Infomerics / Brickwork | HTML | Not reviewed | Not verified | UNCLEAR |
| MCA | HTML + data.gov.in mirror | Not reached | Not verified | BLOCKED |
| Alpha Vantage | REST, API key | Not reviewed in depth | n/a (no key) | **AWAITING_KEY** |
| Kaggle NSE/BSE datasets | Account required | CC0 per publisher tags | n/a (not downloaded) | **REQUIRES_REGISTRATION** |
| Commercial datasets | Paid | n/a | n/a | REQUIRES_PAYMENT_OR_LICENCE |
| Academic datasets | n/a | n/a | n/a | UNCLEAR (gap) |
| **9 company IR sites** (Vakrangee, Jet Airways, Brightcom + 6 controls that worked) | HTML + PDF, own domains | Not reviewed per-site | Real documents downloaded from each | **AVAILABLE** |
| DHFL's own site | HTML | n/a | n/a | **BLOCKED** (own robots.txt: `Disallow: /`) |
| Reliance Capital / Gensol own IR sites | HTML | n/a | n/a | **BLOCKED** (connection failure both) |

Full detail: `docs/data/source-inventory.md`, `data/manifests/sources.yaml`.

## 7. Seed dataset summary

**15 companies represented** (target: ≥12 — met):
GENSOL, DHFL (511072), Jet Airways, Reliance Capital (500111), Future
Retail (540064), Brightcom (BCG), CG Power (CGPOWER), Vakrangee — plus 7
controls: LIC Housing Finance, PNB Housing Finance, SpiceJet, Avenue
Supermarts/DMart, Thermax, Suzlon Energy, Mastek.

**237 distinct documents** (target: ≥150 — met), 48 MB total (target: <2 GB
— met), zero hash mismatches.

**Flag-coverage target, honest shortfall report**:
- AUD_RESIGN: **met** (Vakrangee auditor resignation letter + company
  update + Reg 30 intimation, all three from vakrangee.in).
- KMP_EXIT or ID_EXIT: **not met**. No KMP or independent-director exit
  disclosure was found/downloaded in this round — none of the reachable
  IR sites' discovered documents happened to be this document type, and
  no exchange-announcement search (still BLOCKED) was available to find
  one. Open gap for Phase 1/2.
- RATING_ACT: **met** (CARE rationale on DHFL).
- PLEDGE_UP (shareholding patterns): **met** (8 shareholding-pattern
  documents: Jet Airways, SpiceJet, LIC Housing, PNB Housing, Mastek, +
  others) — though mostly *current*, not pre-event, patterns; see
  `docs/data/manual-download-checklist.md` items 2/4/6/7/9/13/14 for the
  specific pre-event patterns still missing.
- AUDIT_QUAL (annual reports/results): **met** (Brightcom FY2018-19,
  Thermax 44th annual report).

**Dropped/gap, updated from Phase 0**:
- Manpasand Beverages: still dropped — retested, no primary source found
  on its own site either.
- Brightcom's exact SEBI interim-order PDF, Reliance Capital's/Future
  Retail's exact admission orders: still not isolated (pagination gaps,
  unchanged from Phase 0).
- See `docs/data/manual-download-checklist.md` (14 items) for the
  complete, prioritised remaining-gap list.

Full detail and the Vakrangee TLS-bug narrative: `docs/data/seed-universe.md`.

## 8. Gaps and their later-phase impact

| Gap | Later-phase decision this affects |
|---|---|
| KMP_EXIT/ID_EXIT: no example document found | Needed before Phase 2 taxonomy work can validate this category end-to-end |
| BSE/NSE announcements, shareholding, XBRL still BLOCKED (price data resolved) | AUD_RESIGN/KMP_EXIT/ID_EXIT/RESULT_DELAY/pre-event PLEDGE_UP still need a non-exchange source for companies whose IR site doesn't cover them |
| Control-group "no event" not actively verified (no exchange search available) | Any later labelling work should treat the control set as "no event found," not "proven absent" |
| Reliance Capital / Future Retail / Brightcom exact order/PDF gaps | Unchanged from Phase 0 — a pagination/search-depth problem, not a new access method |
| CRISIL excluded by choice | Unchanged — your decision #1 in `docs/data/acquisition-strategy.md` |
| MCA blocked; data.gov.in unverified | Unchanged |
| Pre-2016 NSE bhavcopy coverage via `archives.nseindia.com` unconfirmed | A 1999 spot-check was blocked; Phase 1 should find the right path/convention for 2010-2015 if needed |
| Row-level price-data parsing not done | File-level survivorship is confirmed; per-symbol row presence inside each CSV is an unparsed, bounded Phase 1 task |

## 9. Decisions needing your approval

(Full detail in `docs/data/acquisition-strategy.md`.)
1. CRISIL: unchanged from Phase 0.
2. BSE/NSE announcements/shareholding/XBRL (not price data, now
   resolved): whether to pursue official data licensing, given IR sites
   work for some companies but not all.
3. Object storage for Phase 1+: Garage resolves the Phase 0 CVE issue;
   still your call whether Phase 1+ keeps it.
4. Whether to act on any of the 14 `docs/data/manual-download-checklist.md`
   items yourself via `data/inbox/` + `scripts/import_local.py`.

## 10. Security and data-integrity checks performed

- All Phase 0 checks (§10 original), re-run and still passing.
- **A real secret-scan finding was acted on, not suppressed**: gitleaks
  flagged `infra/garage/garage.toml`'s hardcoded `rpc_secret`/`admin_token`
  as `generic-api-key`. Fixed by moving both to `GARAGE_RPC_SECRET`/
  `GARAGE_ADMIN_TOKEN` environment variables (natively supported by
  Garage since v0.8.2), sourced from the gitignored `.env`. Re-ran
  gitleaks after the fix: clean.
- **A real TLS verification issue was fixed, not bypassed**: see §1/§4 —
  `truststore` (OS trust store) replaces the certifi bundle; certificate
  verification remains fully enabled.
- `.claude/` (previously only `.claude/settings.local.json`) is now
  entirely gitignored, after a stray harness-internal file
  (`.claude/scheduled_tasks.lock`) was noticed in `git status`.
- Every one of the 237 real downloaded files' sha256 is recorded and
  independently recomputed by `verify_manifests.py` — zero mismatches,
  confirmed after both acquire_seed runs.

## 11. Git

- Branch: `phase-0/environment-and-data-inventory` (unchanged).
- Identity: `gaurav685 <gaurav685@gmail.com>` — §A.1 printed the current
  identity/log/remote/branch (see raw output below); INTENDED_IDENTITY
  was `keep-current`, so no re-authoring was needed or performed.
- **Remote/push: deliberately deferred.** You said mid-session: "skip the
  github push in all the phases, ill ask you to push in the end when the
  project is complete." No `git remote add`, no push was attempted this
  round or will be in future phases, per that instruction — this is not
  a failure, it is the correct behaviour given what you asked for.
- Commit message: `"phase-0: expand seed via company disclosures and
  harden storage image"`, no AI co-author/attribution trailer.
- Raw `git log`/status output: see the final message to the user, quoted
  from the actual commands rather than restated here.

## 12. Exit-gate checklist (§G of the correction brief)

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | Commits under intended identity, no AI trailer | **PASS** | `gaurav685 <gaurav685@gmail.com>`, raw `git log` confirms no trailer |
| 2 | Branch pushed, remote SHA matches | **DEFERRED** | Per your explicit instruction to skip push in all phases until you ask at project completion — not a failure |
| 3 | Seed meets B4 targets or shortfall reported; verify-manifests 0 mismatches | **PASS (with reported shortfall)** | 15 companies (≥12 ✓), 237 documents (≥150 ✓), 48MB (<2GB ✓), 0 mismatches ✓; KMP_EXIT/ID_EXIT evidence **not met**, reported in §7 |
| 4 | import-local implemented+tested; checklist ≤40 items | **PASS** | 5 tests in `test_import_local.py`; dry-run and test-run both demonstrated live; checklist has 14 items |
| 5 | Price-data verdict recorded; any data licence-compliant | **PASS** | `archives.nseindia.com` (AVAILABLE_WITH_LIMITS, used), Alpha Vantage (AWAITING_KEY, not used), Kaggle (REQUIRES_REGISTRATION, not used) |
| 6 | Storage image has no known unpatched critical CVE; ADR 0003 written; infra-check passes via S3 API | **PASS** | Garage, no CVE found (with the scan-limitation caveat documented); `docs/adr/0003-object-storage.md`; infra-check passed twice via boto3 |
| 7 | All checks pass; docs/report reflect reality; gates 1-10 re-marked | **PASS** | This document; see §4 for the two real issues found and fixed mid-session (mypy dep, gitleaks secret) |

(Original Phase 0 gates 1, 2, 4, 5, 7-9 remain **PASS**, unchanged and not
re-litigated here; gates 6 and 10 are superseded by rows 3 and 1/6 above
respectively.)

## 13. Outstanding defects and next steps

No outstanding defects — the two real issues found this round (mypy
dependency gap, gitleaks secret finding) were both fixed, not deferred.
Gaps (scope, not defects) are in §8. Next steps, in priority order:

1. Decide on CRISIL and BSE/NSE licensing (unchanged asks).
2. Find a KMP_EXIT or ID_EXIT example document — the one explicit target
   miss this round.
3. Parse the 200 downloaded bhavcopy CSVs for row-level survivorship of
   the four CIRP companies' symbols (file-level survivorship is already
   confirmed).
4. Work through `docs/data/manual-download-checklist.md` (14 items) if
   you want tighter pre-event PLEDGE_UP coverage.
5. When you're ready to push: provide a repo URL and I'll add the remote
   and push then (per your instruction to defer this until you ask).
