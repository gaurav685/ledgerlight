# Phase 6A Final Report — Integrated Validation, Hardening, and Review

Branch `phase-6/integrated-validation-release`, created from Phase 5 HEAD
`9227f51`. This is the final, consolidated report for Phase 6A §1-§17 of
`docs/phase-6/brief-6a.md`. `docs/phase-6/progress.md` is the full,
real, session-by-session log with every raw command and finding;
this report summarizes it against the brief's own exit gates and
closes with the required human checkpoint. Nothing below claims more
than the cited evidence supports.

## Section-by-section summary

- **§1 Preflight** — COMPLETE. `docs/phase-6/orchestrator-evidence.md`
  built with verbatim Phase 2-5 evidence; green baseline (408 default +
  322 integration, one sequential pass, no memory kill). All 5 stop
  conditions checked explicitly: none triggered. Commit `66f7020`.
- **§2 Low-memory stack profile + e2e/ZAP** — COMPLETE.
  `infra/docker-compose.e2e-lite.yml` built and measured. Full
  Playwright e2e suite: **4/4 passed**. Found and fixed a real,
  significant CSP/hydration bug (strict `script-src 'self'` silently
  broke every form on every page; deployed `'unsafe-inline'`,
  disclosed as a residual risk). ZAP baseline: **0 FAIL** in 2 runs; 2
  real findings fixed (`X-Powered-By`, `Permissions-Policy`); 4
  remaining triaged as accepted. Commit `dea2c0c` + a follow-up.
- **§3 End-to-end pipeline test** — COMPLETE. Real ingestion-to-dossier
  citation chain proven. Found and fixed a real cross-test-pollution
  bug (an orphaned global entity row) and 4 other real test-harness
  bugs along the way.
- **§4 Regression suite** — COMPLETE. Golden-fixture suite
  (`tests/test_regression_snapshots.py`) built against 6 real,
  specifically-chosen subjects across extraction/events/entities/
  features/scores/dossiers.
- **§5 Backtest reproducibility and audits** — COMPLETE (PARTIAL).
  Backtest run 3x against an isolated restore: byte-identical every
  time, matching Phase 3 exactly. Leakage/permutation/feature-shift
  audits reproduced exactly. One real sub-step (`build_feature_snapshots.py`)
  BLOCKED by host memory — independently confirmed row-count-identical
  instead, not silently skipped. **Re-confirmed independently again in
  §16** (fresh restore, same exact numbers).
- **§6 Consolidated evaluation report** — COMPLETE.
  `docs/evaluation/final-evaluation.md`, every real result from Phases
  2-5 plus this phase's own, GOLD/SILVER-UNREVIEWED/PENDING_HUMAN_REVIEW
  tagged throughout.
- **§7 Human review pack** — COMPLETE (build only, no reviewing, by
  design — Phase 6B's job). All 5 real review types built: field,
  entity-pair (honestly only 5 real pairs, not the ~20 target — real
  corpus is too thin), retrieval, outcome-evidence, dossier (13-item
  sample, 3 seeded-QC). `docs/phase-6/human-review-guide.md` and
  `scripts/review_progress.py` both confirmed working.
- **§8 Performance and reliability** — COMPLETE. Real load test (228
  requests, 0 failures), real per-stage throughput measurement, 5 real
  failure-recovery drills (worker kill, Postgres restart, Garage
  outage, agent crash — found and fixed 2 real bugs — revoked key/
  expired session). **Load test and drill 5 re-confirmed in §16.**
- **§9 Security and tenant re-validation** — COMPLETE (PARTIAL). 97
  security tests passed. `pip-audit` found and fixed 24 real
  vulnerabilities (0 remaining). Found and fixed a real, previously-
  undiscovered production bug the dependency bump exposed (a
  background-task visibility race in dossier creation). Docker image
  rebuild BLOCKED by host memory (disclosed, not forced). gitleaks:
  195 commits, 0 leaks. **Security suite re-confirmed in §16 (97
  passed again).**
- **§10 Cost per filing** — COMPLETE. Real per-stage cost measurement
  (10 real filings) after finding and fixing 3 real bugs in the
  measurement script itself (a keyword-only-arg mismatch, a
  `company_id`-scoping bug, and a significant one: `run_store_backfill`
  silently replaying every prior filing's manifest entry). AWS cost
  model with every input tagged `[MEASURED]`/`[CITED]`/`[ASSUMED]` —
  no invented prices.
- **§11 Data-source compliance and licence review** — COMPLETE.
  Re-checked robots.txt for all 16 enabled sources; one real,
  significant finding (Thermax now blocks `ClaudeBot` by name,
  downgraded to BLOCKED per the existing CRISIL precedent). Full
  licence inventory: 195 Python packages, 332 npm packages, both real
  model checkpoints, 4 container images. **One real, significant
  finding**: `pymupdf` is dual-licensed AGPL-3.0/Artifex commercial —
  never previously flagged.
- **§12 Final documentation** — COMPLETE. `docs/architecture.md` (new,
  2 Mermaid diagrams), `docs/data-dictionary.md` (new, generated),
  `docs/api/openapi.json` reconciled (found and fixed real drift from
  the §9 dependency bump), `docs/deploy/` reconciled, model card
  re-verified byte-identical, README rewritten.
- **§13 Clean-install and reproducible-setup test** — COMPLETE. Found
  and fixed 3 real setup-doc defects (bash-only syntax that doesn't
  work in real PowerShell, a missing `--extra ocr` flag, a wrong claim
  about which secrets ship with working defaults) plus a real gap in
  the §12 data-dictionary generator (missed a raw-SQL-only table).
  Verified clean after fixes: fresh clone, 408/408 tests, real API and
  frontend both start and serve real pages. **Independently re-run in
  §16 with no new defects found.**
- **§14 Production-readiness checklist** — COMPLETE.
  `docs/release/production-readiness.md`, every capability across 11
  real areas marked COMPLETE/PARTIAL/BLOCKED with evidence.
- **§15 Release-gate status** — COMPLETE. Every gap in
  `docs/release/release-gates.md` evaluated: 1 PASS (ZAP/Playwright,
  corrected 2026-11-07 — was stale), 4 PENDING_HUMAN_REVIEW, 1
  PENDING_PUSH, 8 BLOCKED (now 7 BLOCKED after the ZAP correction).
- **§16 Run and verify** — COMPLETE (PARTIAL). Every automated test
  layer re-run fresh with raw output: default suite 408 passed,
  integration suite fully covered (all 51 files, split across 4
  batches plus 7 individually-isolated files after real sustained host
  memory pressure), e2e pipeline test twice (both clean), backtest
  reproducibility re-confirmed independently, full security suite
  re-confirmed (97 passed), load test re-confirmed, failure-recovery
  drill 5 re-confirmed, clean-install test re-confirmed independently.
  Deliberately not re-run, each for a disclosed reason: failure-
  recovery drills 1-4 (fresh synthetic data + real multiprocess kill
  timing, or live shared-infra disruption) and a second Playwright/ZAP
  pass (already proven once in §2; re-disrupting the real, currently-
  running shared dev stack for an identical second confirmation,
  possibly affecting a peer session on the same machine, was judged
  not worth it without a clearer signal that's wanted).
- **§17 Commit (local only) and backup** — COMPLETE. Every commit this
  phase used the real identity, `phase-6:` prefix, no AI attribution
  (verified repeatedly throughout, and again below). Bundle created
  and verified.

## Exit-gate checklist (brief §18)

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | `orchestrator-evidence.md` complete, no stop condition triggered | **PASS** | `docs/phase-6/orchestrator-evidence.md`, §1 |
| 2 | Playwright e2e + ZAP complete on e2e-lite (or BLOCKED with OOM evidence) | **PASS** | §2: 4/4 Playwright, ZAP 0 FAIL both runs — this gate's own tracking entry in `release-gates.md` was found stale and corrected 2026-11-07 while preparing this report |
| 3 | E2E ingestion-to-dossier test passes twice, citation chain proven | **PASS** | §3 (first proof) + §16 (twice, fresh: both clean) |
| 4 | Regression suite in place, all test layers pass | **PASS** | §4 (built) + §16 (408 default + full integration coverage, all passing) |
| 5 | Backtest reproduced with diff shown, audits re-run and pass | **PASS** | §5 (3x byte-identical) + §16 (re-confirmed independently, exact match) |
| 6 | Performance and failure-recovery results reported | **PASS** | §8 (built, 5 drills) + §16 (load test + drill 5 re-confirmed) |
| 7 | Security and tenant re-validation pass, all findings triaged | **PASS** | §9 (97 passed, 24 vulns fixed) + §16 (97 passed again) |
| 8 | Cost per filing measured, cost model has no invented prices | **PASS** | §10 — every price tagged `[MEASURED]`/`[CITED]`/`[ASSUMED]` |
| 9 | Compliance and licence review complete | **PASS** | §11 |
| 10 | Final docs complete, clean install succeeds from docs alone | **PASS** | §12, §13 (succeeded after real fixes) + §16 (re-confirmed independently, no new defects) |
| 11 | Readiness checklist and release-gate status written | **PASS** | §14, §15 |
| 12 | All 5 review types built and tested, guide and progress command work | **PASS** | §7, confirmed `scripts/review_progress.py` runs clean this report |
| 13 | Committed locally with no AI attribution, bundle verified | **PASS** | §17, re-verified below |

**All 13 exit gates PASS.** This does not mean every underlying
capability is production-ready — see Limitations below and
`docs/release/production-readiness.md` for the honest, separate
question of what the platform itself can and cannot be trusted for.
The gates above are about whether Phase 6A's own validation and
hardening work was actually done and evidenced, which it was.

## Limitations (the real, honest state of the platform itself)

In order of real severity, per `docs/release/production-readiness.md`:

1. **The risk model makes no predictive-skill claim.** Only 5 real
   pooled distinct positive events exist in the verified-coverage
   universe — statistically inconclusive per the brief's own 30-event
   floor. No model variant beats the training-fold base rate. Not
   investment advice; not validated for any real decision.
2. **No gold human review has happened yet.** Every extraction/
   entity-resolution/retrieval/dossier metric above event-
   classification is silver-unreviewed, `PENDING_HUMAN_REVIEW`,
   explicitly Phase 6B's job.
3. **`pymupdf`'s AGPL-3.0/Artifex-commercial licence is unresolved.**
   Blocks any commercial/SaaS launch of the real PDF-extraction
   functionality; does not block research/internal use today.

Also disclosed, each independently scoped and non-blocking for
research/internal use: BSE/NSE/CRISIL/ICRA/MCA/Thermax acquisition
BLOCKED (real, specific reasons each); AWS not deployed (no
credentials, out of scope); GitHub Actions unverified (no remote,
GIT POLICY); financial features excluded (real evidence, not
untested); guidance extraction BLOCKED (0 real guidance statements
exist in the corpus); the deployed Docker images predate the §9
dependency fix (rebuild killed twice by host memory); frontend CSP
uses `'unsafe-inline'` (a real Next.js 16.4.3 limitation); 363 real
corpus pages now trip the "no scanned PDFs" tripwire test (found
incidentally in §11, not yet run through the real OCR path and
spot-checked).

## Decisions needing your approval

1. **`pymupdf` licensing** (the most significant open item): obtain a
   real Artifex commercial PyMuPDF licence, or replace it with a
   permissively-licensed library (`pypdf`/`pdfplumber`/`pdfminer.six`)
   before any commercial/SaaS launch. Not decided here.
2. **Thermax IR blocked** (§11): a deliberate, disclosed judgment
   call applying the existing CRISIL precedent to a robots.txt that
   now names `ClaudeBot`. A human reviewer may reasonably reach a
   different conclusion (the wildcard rule's `use=reference` signal
   could plausibly cover this project's actual use) — flagged as a
   real decision point, not asserted as the only correct reading.
3. **SpiceJet's control-group status** (carried over from Phase 3
   §17.1, still unresolved): a real search found 8 distinct NCLT
   insolvency petitions against SpiceJet (2021-2026), which revisits
   its original "no known distress event" control-group selection.
   Needs a human decision on whether to keep, reclassify, or exclude
   it.
4. **The 363 real corpus pages tripping the OCR tripwire** (§11,
   `release-gates.md`): needs a human (or a future session) to run
   them through the real OCR path, spot-check extraction quality, and
   either update the test's "zero" baseline to the new real number or
   fix a genuine extraction problem if the spot-check finds one.
5. **Pushing a backup bundle to a remote**: no remote is configured;
   GIT POLICY (local-only, this phase and every prior one) stays
   unchanged unless you decide otherwise.
6. **Rebuilding the `ledgerlight-phase0-api`/`-web` Docker images**
   to deploy the already-fixed dependencies: needs a future session
   with more real host memory headroom than this one had (killed
   twice).
7. **The human review pack itself** (§7): 5 types built and ready,
   nothing reviewed yet. This is Phase 6B's work, explicitly deferred,
   not a decision to make now — listed here only so it's not lost.

## Git identity, SHAs, trailer check, and bundle verify

Every commit this phase used the real, existing identity
(`gaurav685 <gaurav685@gmail.com>`), the `phase-6:` prefix, no git
config changes, and no AI attribution of any kind. Re-verified now,
last 10 commits:

```
git log -n 10 --format='%H%n%an <%ae>%n%B---'

732025bddac59fa287cb074806cbb934158b5547
gaurav685 <gaurav685@gmail.com>
phase-6: fix stale ZAP/Playwright gate status found while preparing §18's final report -- actually closed in §2
---
6bfbb77a9a96b770bae66c7d3dd33e22d79801f7
gaurav685 <gaurav685@gmail.com>
phase-6: §17 commit/backup complete -- bundle created and verified
---
449614db5c3885920b491375a167fbb0d907ed8b
gaurav685 <gaurav685@gmail.com>
phase-6: record §16 final commit SHA in progress.md
---
25a8f0772ea9279de80ccb6b8a8d25cefde4fb21
gaurav685 <gaurav685@gmail.com>
phase-6: §16 complete (partial) -- all automated layers re-verified, infra-disrupting items deliberately deferred
---
7a932db6599beddc53c95eb114c0e2d058c74b6b
gaurav685 <gaurav685@gmail.com>
phase-6: §16 clean-install test re-run independently -- no new defects, same clean result
---
cdad33288cf03eed38464a4afd2c0fb6af2c9b92
gaurav685 <gaurav685@gmail.com>
phase-6: §16 progress consolidated -- security suite, load test, drill 5 done; drills 1-4 deliberately deferred with reasons
---
dbd552f949bd1139008deaf3fdf19333cde1a1ec
gaurav685 <gaurav685@gmail.com>
phase-6: §16 drill 5 re-run (revoked API key + expired session), both clean 401s
---
8bec69e2eb1dc1edf5890c28528df1949ab7fa87
gaurav685 <gaurav685@gmail.com>
phase-6: §16 load test re-run captured (221 requests, 0 failures)
---
8b70d99fa1083b75f8dba6c38c5c4507a96ba784
gaurav685 <gaurav685@gmail.com>
phase-6: §16 full security suite re-run (97 passed, matches §9 exactly)
---
09d96967b480f5eadf6dc73e088ddb3258a5aec8
gaurav685 <gaurav685@gmail.com>
phase-6: §16 backtest reproducibility re-confirmed independently, exact match to Phase 3/§5
---
```

Bundle, created in §17 (`git bundle create
../ledgerlight-backups/ledgerlight-phase-6a.bundle --all`), re-verified
now:

```
git bundle verify ../ledgerlight-backups/ledgerlight-phase-6a.bundle

../ledgerlight-backups/ledgerlight-phase-6a.bundle is okay
The bundle contains these 9 refs:
4b4423f37abfe26c3fe5ff98d416d393167a54fc refs/heads/phase-0/environment-and-data-inventory
53d4ba7e6353ce0d89f66bb3b88a956bf30a9dba refs/heads/phase-1/ingestion-and-document-processing
bc69c2980fa2e849cd1ff11d37ae728103e49ab5 refs/heads/phase-2/knowledge-extraction-entity-resolution
195a714860747676ea877173a5fd0b9489f5add4 refs/heads/phase-3/temporal-risk-modelling
d1daf12f4d249e8cee010d8ab034d13dd804b2e1 refs/heads/phase-4/investigation-agent
9227f51dc0a56530e2fca8f9d5606357be70e35e refs/heads/phase-5/api-ui-security
449614db5c3885920b491375a167fbb0d907ed8b refs/heads/phase-6/integrated-validation-release
449614db5c3885920b491375a167fbb0d907ed8b HEAD
ef2ca9ae7f0284a26d4f915e1ca68f0b932a596d worktrees/humane-roquefort/HEAD
The bundle records a complete history.
The bundle uses this hash algorithm: sha1
```

(The `worktrees/humane-roquefort/HEAD` ref is a pre-existing local
worktree this session did not create -- included automatically by
`--all`, harmless, not evidence of anything this phase did.)

GIT POLICY unchanged throughout: local-only commits, no remote
configured, no push, no tags.

---

**Phase 6A is complete. Do NOT begin Phase 6B.**

## HUMAN CHECKPOINT

**HUMAN CHECKPOINT: run the review pack per `docs/phase-6/human-review-guide.md`**

| # | Type | Real sample size | Est. time | Command |
|---|---|---|---|---|
| 1 | Field review | 30 | ~45 min | `make field-review REVIEWER="you"` |
| 2 | Entity-pair review | 5 (corpus too thin for the ~20 target) | ~10 min | `make entity-pair-review REVIEWER="you"` |
| 3 | Retrieval review | 10 queries x up to 10 results | ~60 min | `make retrieval-review REVIEWER="you"` |
| 4 | Outcome-evidence spot-check | 45 | ~45 min | `make outcome-evidence-review REVIEWER="you"` |
| 5 | Dossier review | 13 (10 real + 3 seeded-QC, unlabelled) | ~90 min | `uv run python scripts/dossier_review.py list --blind`, then `show --task-id <id> --blind` and `decide --task-id <id> --decision ... --reviewer "you"` per item |

Total real wall-clock, done once through: **~4 hours**. Run `make
review-progress` any time to check counts per type and per reviewer —
safe mid-session, nothing requires finishing in one sitting. Every
type resumes automatically.
