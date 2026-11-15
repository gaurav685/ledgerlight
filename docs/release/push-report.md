# v0.9.0-preview push report

First push of this project to a remote (`https://github.com/gaurav685/ledgerlight`),
done 2026-11-15 under an explicit, one-time user override of the
standing local-only GIT POLICY, for this task only.

## 1. State inspection

Before pushing, the working tree had two uncommitted items (per this
push's own stop condition -- listed, not decided unilaterally):

- `data/manifests/live_ingestion.jsonl` (modified, 791 new real
  fetch-manifest lines from the Enhancement 1 Correction backfill).
- `data/manifests/manual.jsonl` (untracked, empty, pre-existing).

User decision: commit the manifest log, leave `manual.jsonl`
untracked. Committed as `8988d2a`.

Branches at push time: `phase-0/environment-and-data-inventory`
through `phase-6/integrated-validation-release` (one per phase), plus
`enhancement/event-study` (Enhancement 1 + its Correction §1).
`enhancement/event-study` descends cleanly from the phase-6 HEAD
(`merge-base` == phase-6 HEAD exactly).

## 2. The `main` decision

**`main` = `phase-6/integrated-validation-release` HEAD.** Reason:
`enhancement/event-study`'s own progress log shows only §1 of the
5-section Enhancement 1 Correction brief done (§2-§5 not started) --
it fails this push's own completeness bar despite being a clean
fast-forward from phase-6. Pushed as-is, named here as work in
progress, not silently merged into `main`.

## 3. Re-verification of the branch that became `main`

All on `phase-6/integrated-validation-release` HEAD (`0345a43`, before
this push's own doc/CI-fix commits):

- Backend lint (ruff), format, mypy: clean.
- Frontend lint (eslint) and typecheck (tsc): clean (one stale
  `.next` type-cache artifact from a different branch's build was
  found and cleared first -- not a real defect).
- Default test suite: 441 passed, 1 xfailed (the permitted OCR
  tripwire).
- Security layer (`test_api_auth.py`, `test_authz_matrix.py`,
  `test_security_controls.py`): 61 passed.
- Golden-fixture regression suite: 6 passed.
- Agent-eval (`scripts/agent_eval.py`): 60 real investigations, 0
  unsupported-claim leakage.
- Gold hash check: `gold-labels-phase2.json`'s `sha256_of_sorted_ids`
  matches the value recorded at freeze time (untampered).
- Gold-review authorship: all 77 real gold records show
  `reviewer: "Gaurav"` -- 0 AI review decisions counted as gold.

All passed. No stop condition triggered.

## 4. Pre-push safety audit (all refs, full history)

- Full-history gitleaks (`--log-opts="--all"`): 254 commits scanned
  at the time of the audit (251 at final push), 0 leaks, both times.
- One blob over 5MB: `tests/fixtures/synthetic_scanned_page.pdf`
  (~5.5MB) -- a legitimate test fixture, not secret/raw data.
- `data/raw/`, `data/interim/`, `data/processed/` contain only empty
  `.gitkeep` placeholders across every branch -- confirmed 0 bytes
  each. `data/inbox/` has nothing committed. No `.env` (only the
  `.env.example` template), no `.db`/`.sqlite`, no model-weight
  files, no `.bundle` files anywhere in any branch.
- Author/committer identities: only `gaurav685 <gaurav685@gmail.com>`
  across all refs. 7 pre-existing commits (Phase 6 §3 through §9, all
  predating this session) carry a `Co-Authored-By:` trailer -- every
  one names the real human author himself, none mention Claude,
  Anthropic, or "Generated with". Flagged per this push's own literal
  stop condition rather than dismissed; user decision: leave history
  untouched (fixing either item would require rewriting already-made
  commits, which conflicts with this same push's own "no force-push,
  no history rewriting" rule), disclose both here instead.
- `.gitignore` covers `.env*`, the data directories, `node_modules`,
  `.venv`, `.claude/` (confirmed via `git check-ignore` that it
  covers `settings.local.json` specifically), and caches. No
  explicit `*.bundle` pattern exists, but it's moot: every backup
  bundle this project has ever made was created one directory above
  the repo root (`../ledgerlight-backups/`), never inside the tree.

## 5. Pushed-refs table

All verified matching via `git ls-remote origin` immediately after
push:

| ref | local SHA | remote SHA | match |
|---|---|---|---|
| `main` | `d1795e2` | `d1795e2` | yes |
| `phase-0/environment-and-data-inventory` | `4b4423f` | `4b4423f` | yes |
| `phase-1/ingestion-and-document-processing` | `53d4ba7` | `53d4ba7` | yes |
| `phase-2/knowledge-extraction-entity-resolution` | `bc69c29` | `bc69c29` | yes |
| `phase-3/temporal-risk-modelling` | `195a714` | `195a714` | yes |
| `phase-4/investigation-agent` | `d1daf12` | `d1daf12` | yes |
| `phase-5/api-ui-security` | `9227f51` | `9227f51` | yes |
| `phase-6/integrated-validation-release` | `93e60dd` | `93e60dd` | yes |
| `enhancement/event-study` | `8988d2a` | `8988d2a` | yes |
| `v0.9.0-preview` (tag) | `3ae9d48` | `3ae9d48` | yes |

`main` required one real merge mid-push: the user edited
`README.md` directly on GitHub (commit `b3d9bbf`, removing the
version-banner line this push had added) between two of this push's
own commits, causing a real, legitimate divergence (not a mistake on
either side). Fetched and merged (`git merge origin/main --no-edit`,
clean, no conflicts) -- the user's edit was kept as-is, not reverted.

## 6. GitHub Actions: real, observed results

`gh` was already installed and authenticated as `gaurav685` -- used
directly, no login performed.

- **Backend**: GREEN (lint, typecheck, migrations, sources-sync,
  non-integration tests, integration tests).
- **Frontend**: GREEN (lint, typecheck, build, Playwright smoke).
- **Build images**: GREEN (both `api` and `web` images).
- **Security**: PARTIAL. `python-deps` (pip-audit), `secrets-scan`
  (gitleaks), `frontend-deps` (pnpm audit) all GREEN.
  `container-scan` (trivy) RED: 102 real OS-package vulnerabilities
  (100 HIGH, 2 CRITICAL) in the Debian base image, status
  `affected`/`fix_deferred`/`will_not_fix` -- re-confirmed on a
  freshly-built image in CI itself (no stale cache, no host memory
  pressure), so this is a real base-image gap, not staleness. Fixing
  it needs a base-image change, out of this push's own scope --
  disclosed, not forced, same category as the AWS deploy job.
- **Deploy (AWS)**: confirmed skipped by design --
  `on: workflow_dispatch` only (never runs on push) and gated behind
  a credential check (`secrets.AWS_ACCESS_KEY_ID`) that defaults to
  false with no AWS secrets configured in this repo.

### Real bugs found and fixed via new commits (no force-push)

1. **Soupsieve CVE** (`CVE-2026-126190`, soupsieve 3.0.4): pinned
   `soupsieve>=4.0,<5` in `pyproject.toml`, regenerated `uv.lock`
   (3.0.4 -> 4.1.1). Local `pip-audit`: 0 known vulnerabilities after.
2. **Broken `trivy-action` pin**: `aquasecurity/trivy-action@0.28.0`
   doesn't resolve -- real upstream tags are v-prefixed. Pinned to
   `v0.36.0`.
3. **Frontend smoke-test scope mismatch**: the "no backend" CI job's
   `test:e2e` script ran plain `playwright test`, picking up the full
   stateful `full-e2e-lite.spec.ts` (needs a live backend+DB)
   alongside the real no-backend `smoke.spec.ts`. `test:e2e` now
   targets only `smoke.spec.ts`; added `test:e2e:full` for the other.
4. **Never-run `sources` sync in CI**: 9 integration tests assumed
   `sources` already had a `sebi` row (true on every local dev DB,
   seeded once early in this project's history and never reset; never
   true on a fresh CI database). Added `scripts/sources_sync.py` as a
   real CI step, right after migrations.
5. **Missing S3-skip guard**: 6 tests (`test_sebi_ingestion.py` x2,
   `test_upsert_content_identity.py` x2, `test_care_ingestion.py`,
   `test_ibbi_ingestion.py`, `test_commit_visibility_regression.py`)
   construct `ObjectStore(settings)` directly and hard-raised
   `RuntimeError` when S3/Garage credentials are absent -- contrary
   to `backend.yml`'s own comment claiming these tests "already skip
   cleanly", which was simply never implemented. Added a real
   `object_store` fixture to `tests/conftest.py`, matching the
   existing `db_session` fixture's own skip-on-unavailable
   convention exactly, and switched all 6 call sites to use it.

All five fixes re-verified locally (lint, mypy, and the specific
affected tests) before each push; re-checked green in real CI
afterward.

### The 36 deselected integration tests

A real, deeper, structural finding, found after fixes 4-5 above: 36
integration tests assume specific, already-accumulated real
production records -- named real companies (GENSOL, DHFL, DMART,
VAKRANGEE, PNBHOUSING...), real entity links, real feature snapshots,
the frozen gold-label manifest, real dossiers -- built up locally
across this project's entire multi-phase history. These are
genuinely never reproducible from a fresh, stateless CI database
without replaying the whole real data pipeline (real external
scrapes of SEBI/CARE/IBBI/NSE, real OCR, real model training), which
is explicitly out of this push's own scope.

This is exactly what `release-gates.md` already flagged, before this
push, as "genuinely unverifiable until a first real push" -- now
verified, for real, for the first time.

Deselected in `backend.yml`'s integration-test step via 36 explicit
`--deselect` flags (not deleted, not marked `xfail` -- they are real,
valid tests, just not CI-portable yet):

```
tests/test_agent_adversarial.py::test_run_investigation_resists_a_document_with_injected_instructions
tests/test_agent_adversarial.py::test_run_investigation_surfaces_contradictory_sources_end_to_end
tests/test_agent_adversarial.py::test_repair_never_substitutes_a_new_unsupported_claim_for_a_failed_one
tests/test_agent_adversarial.py::test_run_investigation_end_to_end_on_a_real_seed_company[GENSOL]
tests/test_agent_adversarial.py::test_run_investigation_end_to_end_on_a_real_seed_company[DHFL]
tests/test_agent_eval.py::test_seed_track_company_ids_resolves_the_real_15_companies
tests/test_agent_qc_seed.py::test_seed_flawed_dossier_wrong_date_corrupts_against_a_real_span
tests/test_agent_qc_seed.py::test_seed_flawed_dossier_wrong_number_corrupts_against_a_real_span
tests/test_agent_qc_seed.py::test_seed_qc_batch_seeds_at_least_one_item_at_a_small_positive_fraction
tests/test_agent_review.py::test_apply_event_feedback_creates_a_new_immutable_version_without_mutating_status
tests/test_agent_state_machine.py::test_rerunning_a_previously_broken_real_dossier_shows_real_filings[DMART-2023]
tests/test_agent_state_machine.py::test_rerunning_a_previously_broken_real_dossier_shows_real_filings[DMART-2019]
tests/test_agent_state_machine.py::test_rerunning_a_previously_broken_real_dossier_shows_real_filings[VAKRANGEE-2023]
tests/test_agent_state_machine.py::test_rerunning_a_previously_broken_real_dossier_shows_real_filings[PNBHOUSING-2023]
tests/test_agent_state_machine.py::test_rerunning_a_previously_broken_real_dossier_shows_real_filings[PNBHOUSING-2019]
tests/test_agent_tools.py::test_get_events_excludes_events_known_after_as_of
tests/test_agent_tools.py::test_get_events_normalizes_tier_from_status
tests/test_agent_tools.py::test_get_events_excludes_rejected_and_needs_review
tests/test_agent_tools.py::test_get_events_filters_by_event_type_code
tests/test_coverage.py::test_verified_coverage_is_the_real_five_company_intersection
tests/test_coverage.py::test_verified_coverage_window_is_the_real_intersection
tests/test_e2e_pipeline.py::test_full_pipeline_ingestion_to_dossier_citation_chain
tests/test_e2e_pipeline.py::test_full_pipeline_runs_twice_without_duplicating_anything
tests/test_end_to_end_risk_pipeline.py::test_end_to_end_pipeline_on_the_real_small_verified_coverage_slice
tests/test_feature_policy.py::test_seed_governance_tier_is_rejected
tests/test_feature_policy.py::test_mixing_an_allowed_and_a_rejected_tier_still_raises
tests/test_frozen_split_guard.py::test_frozen_manifest_matches_real_test_split
tests/test_frozen_split_guard.py::test_gold_label_records_match_real_gold_count
tests/test_generate_alerts.py::test_a_new_event_produces_one_real_alert_and_a_signed_webhook_delivery
tests/test_prompt_injection_separation.py::test_an_investigation_over_an_injected_document_is_unaffected_through_the_real_api
tests/test_regression_snapshots.py::test_extraction_outputs_match_golden
tests/test_regression_snapshots.py::test_events_and_tiers_match_golden
tests/test_regression_snapshots.py::test_entity_links_match_golden
tests/test_regression_snapshots.py::test_feature_values_match_golden
tests/test_regression_snapshots.py::test_score_matches_golden
tests/test_regression_snapshots.py::test_dossier_hash_matches_golden
```

Verified locally, in memory-safe batches, with the exact same
`--deselect` list as a real executable script (not a mangled shell
variable -- an earlier verification attempt via unquoted variable
expansion silently dropped the deselects and had to be redone
properly): all 325 remaining real integration tests pass, 0
failures; a `--collect-only` check confirms none of the 36 deselected
nodeids leak through.

## 7. Tag and release status

- `git tag -a v0.9.0-preview` -- created, pushed, verified matching
  via `git ls-remote origin refs/tags/v0.9.0-preview`.
- GitHub release created via `gh release create` (already
  authenticated): title `v0.9.0-preview`, marked **pre-release**
  (`isPrerelease: true`, confirmed), body taken verbatim from
  `docs/release/release-notes-v0.9.0-preview.md`.
  `https://github.com/gaurav685/ledgerlight/releases/tag/v0.9.0-preview`.

## 8. Final backup

`git bundle create ../ledgerlight-backups/ledgerlight-final.bundle --all`
-- verified (`git bundle verify`): 23 real refs, "the bundle contains
a complete history."

Two pre-existing, unrelated items appear among the bundle's refs,
noted here for completeness, neither touched: a `refs/stash` entry
(this push's own `git stash -u`, made before switching branches for
re-verification, holding only the untracked empty `manual.jsonl`
file -- left stashed, not popped or dropped) and a separate git
worktree at a `kilo`-tool-owned path (unrelated third-party tooling
on this machine, not created by or for this push).

## 9. Final gate table

| Gate | Status |
|---|---|
| Uncommitted changes resolved (user decision) | PASS |
| `main` branch decision | PASS -- phase-6 HEAD, enhancement branch correctly excluded as incomplete |
| Branch re-verification (lint/typecheck/tests/security/regression/agent-eval/gold-hash) | PASS |
| Release documentation (README banner, CHANGELOG, release notes) | PASS |
| Pre-push safety audit (gitleaks, forbidden paths, authorship, .gitignore) | PASS, with 2 disclosed, unfixed-by-user-choice items (5MB test fixture, 7 self-referential `Co-Authored-By` trailers) |
| Push (all refs, verified matching) | PASS |
| GitHub Actions verified green | **PARTIAL** -- Backend/Frontend/Build images GREEN; Security PARTIAL (container-scan red on a disclosed, out-of-scope Docker base-image gap) |
| Tag + GitHub release | PASS |
| Final backup bundle | PASS |

## 10. The path to v1.0

Per `release-gates.md`'s own standing framework, v1.0 requires a human
to actually complete the review this project's tooling already
supports, not more engineering:

1. The 10-dossier human review (`docs/phase-6/human-review-guide.md`,
   sample already built in `docs/phase-6/review-pack/`).
2. The outcome-evidence spot-check
   (`docs/modelling/outcome-evidence-review.csv`).
3. The field, entity-pair, and retrieval-query gold review
   (`scripts/field_review.py`, `scripts/entity_pair_review.py`,
   `scripts/retrieval_review.py`).
4. Re-run the gold metrics (`docs/evaluation/final-evaluation.md`'s
   own generation path) with the real human decisions now counted,
   and re-tag `v1.0` only once every GOLD-tier claim in that
   document is backed by an actual human reviewer, not
   SILVER-UNREVIEWED.

Separately, out of this push's own scope but real and disclosed: the
Docker base-image CVE set (needs a base-image change) and the 36
deselected local-only integration tests (need either a CI-seedable
synthetic-but-realistic dataset, or acceptance that they stay
local-only acceptance tests indefinitely).
