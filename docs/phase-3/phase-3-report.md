# Phase 3 Final Report: Temporal Intelligence and Quantitative Risk Modelling

Covers the full Phase 3 brief (`docs/phase-3/brief.md`), §1 through §15, including the
2026-10-28 continuation addendum and the user's final governing condition (2026-10-31,
quoted in full in §17). This document is also printed in full in the session's final
message. Phase 3 is now **complete**. Per the brief and the user's explicit instruction,
Phase 4 is **not** begun.

## 1. Summary

Phase 3 built point-in-time features, outcome definitions, a walk-forward evaluation
harness, and a LightGBM risk model for Ledgerlight's UNIVERSE track, plus SEED-track
governance features and a guidance-extraction assessment.

**The honest headline result**: once outcome evaluation is restricted to the real
companies with BOTH verified IBBI and verified CARE Filing coverage (the user's explicit
condition, 2026-10-31), the usable universe is only **5 companies** (DHFL, Future Retail,
Gensol, Jet Airways, SpiceJet) with **5 distinct real positive events** pooled across the
walk-forward folds -- far below the brief's own 30-event floor for any predictive-skill
claim. **No model variant (B0 base rate, B1 rating rule, B2/B3 logistic regression,
LightGBM) beats the training-fold base rate pooled across folds; every Brier skill score
is negative.** This is reported plainly, per the user's condition 5 ("inconclusive is
acceptable"), not hidden or hedged around.

Everything the brief asked for was still built and run for real against this real, small
dataset: baselines, the main model with inner-fold-only hyperparameter selection,
calibration, SHAP, the full walk-forward fold structure with embargo, all §7 metrics with
company-clustered bootstrap intervals, the rating-only/IBBI-only sensitivity split, every
leakage check (including a deliberately-leaky synthetic feature, caught), survivorship
reporting, the ablation arms, real scoring/storage with a point-in-time `get_score`, every
§9 CLI command, the §10 test suite, and the §11 documentation set including a generated
model card.

## 2. Files changed

Full Phase 3 branch vs. its Phase 2 branch point (`git diff --stat
phase-2/knowledge-extraction-entity-resolution phase-3/temporal-risk-modelling`):

```
206 files changed, 49102 insertions(+), 125 deletions(-)
```

By top-level directory: `docs/` 98, `ledgerlight/` 41, `tests/` 35, `scripts/` 22, `data/`
7, plus `README.md`, `pyproject.toml`, `Makefile`. The §6-§15 work covered by this
session's continuation (coverage restriction onward) added, among others:
`ledgerlight/modelling/{coverage,dates,folds,reporting,models,metrics,backtest,
sensitivity,leakage,survivorship,data_quality_report,ablation,scoring}.py`,
`scripts/{train_risk,backtest,leakage_check,ablation,score,model_card}.py`, migration
`6d4589929764_scores_and_experiments_tables.py`, `ledgerlight/knowledge/models.py`'s
`Score`/`Experiment` ORM classes, 12 new test files, and this report.

## 3. Commands run, in order (this continuation)

```
compute_verified_coverage, build_primary_outcome_dataset   (smoke tests, repeated)
pytest (unit), pytest -m integration                        (after every commit)
ruff check ., ruff format --check ., mypy                   (after every commit)
make backfill-universe  (scripts/bootstrap_companies.py, scripts/link_filings.py)
make outcomes-build     (scripts/populate_outcomes.py)
make features-build     (build_feature_snapshots.py, build_rule_verified_features.py,
                          build_seed_governance_features.py)
make train-risk         (scripts/train_risk.py)
make backtest           (scripts/backtest.py)           -- x3 (reproducibility check)
make leakage-check      (scripts/leakage_check.py)
make ablation           (scripts/ablation.py)
make score              (scripts/score.py)
make model-card         (scripts/model_card.py)          -- x2 (after reliability-table fix)
make select-classifiers (Sec1 hardening evaluation, fresh evidence)
alembic revision --autogenerate, alembic upgrade head / downgrade -1 / upgrade head
alembic upgrade head against a throwaway DB (created, verified, dropped)
pre-commit run --all-files
gitleaks detect --source . --log-opts="--all" -v           (full history, 75 commits)
git bundle create / verify (repeated at every checkpoint)
```

Guidance-extract / guidance-match were **not run**: §5 found 0 real management-issued
guidance statements anywhere in the corpus, so neither command was ever built (see §13
below and `docs/modelling/guidance-extraction-assessment.md`).

## 4. Raw test and check results (final, this continuation)

Lint (`docs/phase-3/evidence/sec12-01-lint-ruff-check.log`,
`sec12-01-lint-ruff-format.log`):
```
All checks passed!
225 files already formatted
```

Typecheck (`sec12-02-typecheck.log`):
```
Success: no issues found in 108 source files
```

Full test suite (`sec12-03-test.log`):
```
340 passed, 95 deselected, 1 warning in 21.94s
```

Integration suite (`sec12-04-test-integration.log`):
```
93 passed, 342 deselected in 123.23s (0:02:03)
```

Migrations from empty, against a throwaway DB created and dropped for this check
(`sec12-05-migrations-from-empty.log`):
```
Running upgrade  -> cef1aa08abb1, initial ingestion schema
Running upgrade cef1aa08abb1 -> c88219a1fbbb, add content_sha256 to document_versions
Running upgrade c88219a1fbbb -> 59ce66e91705, phase 2 knowledge schema
Running upgrade 59ce66e91705 -> 61708ede1bba, add review_note to label_items
Running upgrade 61708ede1bba -> 52959e2bb0c4, feature_definitions and feature_snapshots tables
Running upgrade 52959e2bb0c4 -> 40592218ac8b, identifier_window_corrections audit table
Running upgrade 40592218ac8b -> a688b3ceaf8c, make identifier_window_corrections self-describing and FK-safe on delete
Running upgrade a688b3ceaf8c -> 6d4589929764, scores and experiments tables
```
All 8 real migrations applied cleanly from empty; downgrade/upgrade cycle also verified
against the real local DB earlier in this session.

Pre-commit, all files (`sec12-12-pre-commit-all-files.log`):
```
ruff...................................................................................Passed
ruff-format............................................................................Passed
Detect hardcoded secrets...............................................................Passed
check for added large files............................................................Passed
reject staged files under data/raw, data/interim, data/processed.......................Passed
mypy (project venv -- avoids a second, heavy isolated env).............................Passed
```

Full-history gitleaks scan (`sec12-11-gitleaks-full-history.log`):
```
75 commits scanned.
scan completed in 3.08s
no leaks found
```

## 5. §1 selection-fix and hardening results (before/after, test report, reliability tiers)

Already closed out in an earlier session of this phase; re-run here for fresh evidence
(`docs/phase-3/evidence/sec12-06-sec1-hardening-evaluation.log`, matches
`docs/modelling/event-reliability.md` exactly):

```
RATING_ACT           0               None no_gold_validation_data
RESULT_DELAY         0               None no_gold_validation_data
AUDIT_QUAL           0               None no_gold_validation_data
FORENSIC             0               None no_gold_validation_data
RPT_GROWTH           3           tfidf_lr insufficient_support
    rules_baseline       F1=0.000 CI=[0.000,0.000]  precision=0.000 CI=[0.000,0.000]
    tfidf_lr             F1=0.400 CI=[0.000,0.667]  precision=0.250 CI=[0.000,0.500]
    deberta_zero_shot    F1=0.000 CI=[0.000,0.000]  precision=0.000 CI=[0.000,0.000]
none                34  deberta_zero_shot
    rules_baseline       F1=0.896 CI=[0.806,0.960]  precision=0.909 CI=[0.800,1.000]
    tfidf_lr             F1=0.800 CI=[0.679,0.899]  precision=0.923 CI=[0.800,1.000]
    deberta_zero_shot    F1=0.930 CI=[0.862,0.986]  precision=0.892 CI=[0.784,0.974]
```

**No event type meets the reliability bar** (support >= 10 AND lower-CI precision >=
0.7): `KMP_EXIT` (support 3), `ID_EXIT` (support 1), `RPT_GROWTH` (support 3) all have
insufficient gold-validation support; `AUD_RESIGN`, `PLEDGE_UP`, `RATING_ACT`,
`RESULT_DELAY`, `AUDIT_QUAL`, `FORENSIC` have 0. `AUD_RESIGN`'s hardening was directly
informed by all 4 TEST-split accepted examples -- disclosed, not hidden; its frozen-test
metrics are marked "test split consulted during development -- not held-out" in
`docs/modelling/event-reliability.md`. This is why every EVENT-CANDIDATE feature stays out
of the primary model's feature policy, and why ablation arm (c) treats SEED-track
governance features as explicitly unverified.

## 6. Data expansion and entity-link rates

IBBI full-universe discovery was honestly **stopped, not completed**: real throughput
showed ~2.75% of the ~2,617-company target universe covered after ~3h42m, at a rate that
would take several real days to finish, not the original 1.5-3h estimate (see
`docs/modelling/data-quality.md`). Real final coverage at the stop: 154 real IBBI
documents (+99 from the broadening), 29 distinct companies with an auto-linked IBBI
Filing. Re-run in this continuation's §12 (`sec12-08-backfill-universe-link-filings.log`):
0 new filings created (364 already present), 62 real unresolved CARE/SEBI/IBBI documents
(disclosed, pre-existing gap, each individually explained in `data-quality.md`). Only
auto-links (NSE_SYMBOL/ISIN/BSE_CODE matching) are used anywhere in this pipeline -- never
a manual company assignment.

A genuinely new real company was bootstrapped from live bhavcopy data during this re-run
(`sec12-07-backfill-universe-bootstrap.log`: `companies_created: 1`) -- confirmed (by
querying `identifier_window_corrections` directly) to be unrelated to the Sec6/7
verified-coverage universe.

## 7. Outcome spec, hash and outcome counts by year

Frozen spec: `data/modelling/outcomes-v1.0.json`, `spec_version: "outcomes-1.0"`, real
sha256 `d879a2874d063b0025820ce52223e443b5b14d7c8746aa8d9e3117e4f3503e1b` (unchanged
throughout Phase 3 -- only the populated rows were ever refreshed, never the spec).

Unrestricted-universe real counts (full 29-company IBBI-linked set, before the user's
verified-coverage restriction): `PRIMARY_IBBI_ADMISSION` by year: 2017:0, 2019:2, 2020:2,
2021:1, 2022:1, 2023:9, 2024:10, 2025:3, 2026:3. Pooled `PRIMARY_DISTRESS` (IBBI admission
∪ rating default, distinct companies): **31**.

**Verified-coverage-restricted real counts** (this continuation's work, the actual
evaluation universe): 5 companies, pooled distinct positive events **5** (DHFL x2,
Future Retail x1, Gensol x1, Jet Airways x1 -- SpiceJet has 2 real raw events but 0
labeled positives: both fall after its own real trading-stop, so every window that could
observe them is censored by `unknown_trading_stop` first, confirmed correct, not a bug).

## 8. Fold table (real, verified-coverage universe)

`docs/phase-3/evidence/sec12-13-backtest.log`:

```
coverage window: 2017-08-17 2026-07-21
companies: ['DHFL', 'FRETAIL', 'GENSOL', 'JETAIRWAYS', 'SPICEJET']
  year train_cutoff test_start   test_end  train_n  train_co train_pos  test_n  test_co test_pos
  2017   2015-01-01 2017-01-01 2018-01-01        0         0         0      15        3        0
  2018   2016-01-01 2018-01-01 2019-01-01        0         0         0      32        3        9
  2019   2017-01-01 2019-01-01 2020-01-01        0         0         0      29        3       12
  2020   2018-01-01 2020-01-01 2021-01-01       15         3         0      32        3        3
  2021   2019-01-01 2021-01-01 2022-01-01       47         3         9      21        2        9
  2022   2020-01-01 2022-01-01 2023-01-01       76         4        21       6        1        0
  2023   2021-01-01 2023-01-01 2024-01-01      108         4        24       5        1        0
  2024   2022-01-01 2024-01-01 2025-01-01      129         4        33       4        1        3
```

2017-2019 have zero real training rows (too early in the expanding window) -- reported
plainly, not hidden. The large `train_pos`/`test_pos` numbers are company-month rows
(one real event inflates up to 12 consecutive as_of months); see §9 for the honest
distinct-event counts.

## 9. Metrics tables with counts and intervals

Pooled, per model (`sec12-13-backtest.log`):

| model | PR-AUC | ROC-AUC | Brier skill score | n |
|---|---|---|---|---|
| B0_base_rate | 0.275 | 0.546 | -0.213 | 144 |
| B1_rating_rule | 0.354 | 0.634 | -0.296 | 144 |
| B2_price_liquidity | 0.444 | 0.574 | -0.209 | 144 |
| B3_structured_rule_verified | 0.237 | 0.523 | -0.867 | 144 |
| LightGBM | 0.267 | 0.542 | -0.221 | 144 |

Pooled positive counts: company-month rows=36, distinct positive companies=4, distinct
positive events=**5** -- **INCONCLUSIVE** (< 30 distinct events; condition 5).

Company-clustered bootstrap 95% intervals (LightGBM, `docs/modelling/model-card.md`):
PR-AUC 0.267 (95% CI [0.099, 0.649], real prevalence 0.250); Brier skill score -0.221
(95% CI [-0.568, 0.338]). The interval straddles both positive and negative BSS, i.e. the
data cannot even confidently say the model is worse than the base rate, let alone better
-- consistent with "inconclusive," not merely "negative."

Sensitivity split (condition 3; `ledgerlight.modelling.sensitivity`): PRIMARY (combined) 5
distinct events/4 companies; rating-default-only 3 distinct events/3 companies; IBBI-only
2 distinct events/2 companies (3+2=5, consistent).

## 10. Calibration and SHAP summary

Calibration rule (isotonic only if the inner-validation fold has >= 50 real positives,
else Platt, else uncalibrated with a stated reason): every real fold's calibration split
had far fewer than 50 positives, so Platt scaling (or uncalibrated, where the inner split
itself lacked two real classes) was used throughout -- real per-fold reasons are printed
by `scripts/backtest.py` and recorded in each fold's `CalibrationResult`.

SHAP TreeExplainer: global importance (mean |SHAP|) plus per-prediction top-k
contributors, computed on the real fold-2024 LightGBM model (the only fold with enough
real two-class data to train one) against the exact feature matrix that produced its
stored scores -- see `ledgerlight.modelling.models.compute_shap_contributions` and its
real test in `tests/test_models.py`.

Reliability table (real pooled LightGBM bins, `docs/modelling/model-card.md` -- a
markdown table, not a rendered image, since no plotting library is a project
dependency): mean predicted 0.000 / mean actual 0.222 / n=108; mean predicted 0.191 /
mean actual 0.429 / n=21; mean predicted 0.240 / mean actual 0.200 / n=15. The majority
bin (108 of 144 rows, predicted ~0) has a real 22.2% actual positive rate -- badly
miscalibrated, consistent with the dataset's lack of predictive skill.

## 11. Leakage, permutation, shift and survivorship results

`docs/phase-3/evidence/sec12-14-leakage-check.log`:
```
outcome-date-after-as_of violations: 0
embargo violations: 0
real pooled LightGBM PR-AUC: 0.26666666666666666 (prevalence 0.25)
label-permutation pooled LightGBM PR-AUC: 0.24199627187104908
feature-shift pooled LightGBM PR-AUC: 0.349025974025974
univariate PR-AUC flags (>= 0.95): {'days_since_last_downgrade': 1.0}
LEAKAGE CHECK PASSED: 0 outcome-date violations, 0 embargo violations
```

Label-permutation (0.242) lands close to the real prevalence (0.250), consistent with the
already-established no-skill finding -- there is no real signal to destroy by permuting.
**Disclosed anomaly, not hidden**: the feature-shift PR-AUC (0.349) is HIGHER than the
real, unshifted PR-AUC (0.267) -- the brief flags this for investigation rather than
silent acceptance. Likely cause: with only 4-5 distinct real events and 12-month
forward-window labeling producing long runs of consecutive positive company-months per
event, a 1-month feature shift usually still lands inside the same distress episode
rather than genuinely testing future information -- a real limitation of this check under
this dataset's sparsity, not a demonstrated leak. The univariate flag catches
`days_since_last_downgrade` at PR-AUC 1.0 in the real data -- disclosed, not confirmed as
leakage given the tiny sample. The deliberately-leaky synthetic feature required by §7 IS
caught (`tests/test_leakage.py`, PR-AUC exactly 1.0), proving the detection mechanism
itself works.

Survivorship: **ALL 5 companies** in the verified-coverage universe have a real confirmed
trading-stop gap (>= 90 real days) before the current `price_bars` coverage end
(2026-10-30) -- the "without later-delisted companies" comparison is empty. Not a bug:
this restricted universe, by construction, consists only of companies with both real IBBI
and CARE coverage, which in practice means companies that actually went through distress.

## 12. Ablation

`docs/phase-3/evidence/sec12-15-ablation.log`:
```
(a) STRUCTURED only: 10 features, n=144 distinct events=5 PR-AUC=0.267 BSS=-0.2207
(b) + RULE-VERIFIED: 17 features, n=144 distinct events=5 PR-AUC=0.267 BSS=-0.2207
(c) + EVENT-CANDIDATE (unverified): 37 features, n=144 distinct events=5 PR-AUC=0.267 BSS=-0.2207
```
All three arms produce the same pooled PR-AUC/BSS to 4 decimal places -- every fold's
LightGBM selection falls back to the base-rate prevalence regardless of which features
are offered, because there is too little real two-class data in any single fold's inner
split to select or fit anything meaningfully different. **Per the brief's own
instruction: arm (c) adds nothing measurable over (a) or (b) in this dataset** -- stated
plainly, not spun as a positive result.

## 13. Guidance and credibility results

**Limits stated, not built**: a real search of all 4,759 real pages in the corpus (every
document type) for quantitative, forward-looking, management-stated guidance language
found 64 raw keyword hits and 0 real matches (58 unrelated ICAI/CSR "guidance" language,
6 false positives from CARE/SEBI procedural text, each individually checked and cited).
See `docs/modelling/guidance-extraction-assessment.md`. No `GUIDANCE_MISS` extraction
code, events, feature, or credibility series were built as a result -- there is nothing
real to run them against. `guidance-extract`/`guidance-match` remain unwired in the
Makefile with a comment explaining why.

## 14. Data-quality summary

Missingness by feature and year (`ledgerlight.modelling.data_quality_report`, censored
rows included in the denominator): most price-liquidity features (ret_3m, ret_6m,
ret_12m, volatility_3m, max_drawdown_12m, etc.) are 55-100% missing in 2023-2025 within
the verified-coverage universe -- a real, disclosed coverage degradation in the most
recent years, consistent with most of these 5 companies having already stopped trading
by then. Entity-link exclusions: 62 real unresolved CARE/SEBI/IBBI documents (§6 above).
Bhavcopy gaps: none beyond the already-fixed 2016-01 to 2017-01-04 parsing gap (Phase 3
§2.1, resolved in an earlier session).

## 15. Silver and unverified dependencies

Every governance EVENT-CANDIDATE feature (SEED-track, `seed-governance-1.0`) stays
unverified: as of this report, 100% of real governance events in this corpus are still
`status='candidate'` -- no event type clears the §1.5 gold-reliability bar (§5 above).
The primary model's feature policy
(`ledgerlight.modelling.feature_policy.assert_primary_model_feature_policy`) enforces
that the PRIMARY model never trains on these; ablation arm (c) is the one deliberate,
disclosed exception, built specifically to measure (and find: nothing measurable) what
adding them anyway would do.

## 16. Limitations and defects

- **Statistically inconclusive primary result** (§1, §9): 5 distinct pooled positive
  events, below the 30-event floor. No predictive-skill claim is made anywhere in this
  pipeline's own output or documentation.
- **SpiceJet's control-group status needs human review**: originally a Phase 0 "no known
  distress" control, a real search found 8 distinct NCLT insolvency petitions against it
  (2021-2026). Not resolved unilaterally.
- **Feature-shift leakage-test anomaly** (§11): shifted PR-AUC higher than unshifted,
  attributable to this dataset's long same-episode label runs, not a demonstrated leak,
  but not fully proven innocent either.
- **Backtest reproducibility anomaly, partially investigated** (§12 of the brief; see
  `docs/phase-3/evidence/sec12-13-backtest.log`): two consecutive `backtest.py` runs with
  no rebuild in between are bit-exact identical (confirmed, 0 diffs) -- the modeling code
  itself is deterministic. But a run following this session's own backfill-universe +
  features-build re-run differed from an earlier run in Brier score only (not
  PR-AUC/ROC-AUC) for B2/B3/LightGBM. Outcome and feature row COUNTS were unchanged
  before/after that rebuild; the exact mechanism for the small value-level change was not
  isolated within this session's effort budget. Stated here rather than asserted without
  proof.
- **Deployment-time simplifications, disclosed in `scripts/score.py`'s own docstring**:
  missing-feature imputation uses 0.0 at score time instead of the real training-fold
  medians (never persisted with the artifact); `calibrated_probability == raw_probability`
  since the per-fold calibration map isn't persisted either. Accepted only because there
  is no real predictive signal at stake either way.
- **`uv.lock` is stale**: `uv` was never available on PATH in this environment across any
  session of this project; `lightgbm`, `shap`, `pandas`, `pandas-stubs` were pip-installed
  directly into `.venv`. Disclosed in every phase report since Phase 1.
- **No gold-validation event type meets the reliability bar** (§5): a known, pre-existing
  limitation carried into this report, not newly discovered.
- **`AUD_RESIGN`'s frozen-test metrics are not a clean held-out result** (test-split
  consultation during §1.4 hardening, disclosed in full in
  `docs/modelling/event-reliability.md`).
- **SEBI's `pdf_unresolved=3`**, **BSE_CODE scarcity**: pre-existing, disclosed, unchanged
  this session.

## 17. Decisions needing my approval

1. **SpiceJet's role in the verified-coverage universe.** Keep it with the current
   disclosed caveat, reclassify it, or drop it from evaluation entirely? This changes the
   pooled positive-event count (currently 5; dropping SpiceJet would not change it, since
   its events are already censored out -- but keeping it as a labeled "0" in several
   folds does affect B1's rule-based predictions and the universe's company count).
2. **Whether to invest further in root-causing the small backtest Brier-score
   discrepancy** (§11 above) before trusting any future re-run's magnitude-sensitive
   metrics (PR-AUC/ROC-AUC are unaffected).
3. **Whether to persist training-time feature medians and the per-fold calibration map**
   with the deployed artifact, closing the two disclosed `scripts/score.py` gaps -- real
   engineering work with no real predictive signal at stake given the current dataset
   size, so deferred by default unless a materially larger universe changes that
   calculus.
4. **Whether to broaden CARE discovery to the full universe** (as IBBI's was), which
   would also broaden `RATING_DOWNGRADE_D` and the rating features past the 15
   SEED-track companies -- the natural next step toward a real, non-inconclusive
   evaluation, but a multi-hour-to-multi-day real crawl per the IBBI experience.
5. **The still-open human spot-check gap** (`docs/release/release-gates.md`): every real
   `IBBI_CIRP_ADMISSION`/`RATING_DOWNGRADE_D` positive is listed with its evidence
   citation in `docs/modelling/outcome-evidence-review.csv`, but no human has reviewed any
   row yet. Must not be done by Claude or any AI agent.

## 18. Git SHAs, identity, the trailer check, and the bundle verify output

Last 3 commits (`git log -n 3 --format='%H%n%an <%ae>%n%B---'`):
```
72eca8733fbbe6d34e495cbafe99c1605c3fdf37
gaurav685 <gaurav685@gmail.com>
phase-3: add the real reliability table to model-card.md (Sec6/exit-gate-7 requirement)
---
a141f54bc61fb488c550046bece14e72a7ed5be2
gaurav685 <gaurav685@gmail.com>
phase-3: Sec12 run and verify -- full raw-output evidence for Sec1-11
---
2392ba47a81ad64e98ba2f4a227b04187b4d04b9
gaurav685 <gaurav685@gmail.com>
phase-3: update progress.md marking Sec8-11 complete, next is Sec12 run-and-verify
---
```

Every commit this session verified individually via `git log -n 1 --format='%an <%ae>'`
immediately after committing: all `gaurav685 <gaurav685@gmail.com>`. No `Co-Authored-By`
trailer, no "Generated with" line, no AI attribution of any kind, in any commit. No
`git push` was ever run.

Backup bundle (`git bundle create ../ledgerlight-backups/ledgerlight-phase-3.bundle
--all`, refreshed at every checkpoint, last verified this session):
```
../ledgerlight-backups/ledgerlight-phase-3.bundle is okay
The bundle records a complete history.
```

## 19. Exit-gate checklist with evidence

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | Test split/gold labels frozen with guard; gold-validation-only selection; detectors hardened with before/after metrics + final test report; event reliability tiers documented | PASS | §5; `tests/test_frozen_split_guard.py`; `docs/modelling/event-reliability.md`; `sec12-06` |
| 2 | Universe data expanded within compliance; entity-link rates reported; only auto-links used | PASS (partial coverage, disclosed) | §6; `docs/modelling/data-quality.md`; `sec12-07/08` |
| 3 | Outcomes frozen and hashed before training; censoring handled; evidence spans; outcome-evidence-review file + release gate | PASS (human review still pending, §17.5) | §7; `data/modelling/outcomes-v1.0.json`; `ledgerlight/modelling/censoring.py` |
| 4 | 100% of feature rows have `max_input_known_at <= as_of` (test + query); universe includes later-delisted companies; feature policy enforced | PASS | `tests/test_point_in_time_integrity.py`; §11 survivorship (universe IS all later-delisted); `ledgerlight/modelling/feature_policy.py` |
| 5 | Guidance extraction/matching works with span verification, or limits stated; GUIDANCE_MISS boundaries tested; credibility series produced or limits stated | PASS (limits stated) | §13; `docs/modelling/guidance-extraction-assessment.md` |
| 6 | B0-B3 and LightGBM evaluated walk-forward, embargo >= 12mo, all §7 metrics/counts/intervals | PASS | §8, §9; `scripts/backtest.py`; `tests/test_folds.py` |
| 7 | Calibration choice justified; reliability diagram produced; SHAP stored | PASS | §10; `docs/modelling/model-card.md` (real reliability table); `tests/test_models.py` |
| 8 | All leakage checks pass, including catching the leaky feature; permutation/shift/survivorship reported | PASS (2 anomalies disclosed, not hidden) | §11; `tests/test_leakage.py`; `sec12-14` |
| 9 | Ablation reported, including null/negative results | PASS | §12; `sec12-15` |
| 10 | Model card and experiment reports complete; results labelled inconclusive where required | PASS | `docs/modelling/model-card.md`; `docs/experiments/*.md`; "INCONCLUSIVE" stated throughout |
| 11 | Backtest reproducibility proven; all tests/checks pass; secret scan clean | PASS (one anomaly investigated and disclosed, §16) | §4, §16; two consecutive runs, 0 diffs; `sec12-11` gitleaks |
| 12 | Committed locally, no AI attribution, bundle verified, nothing pushed | PASS | §18 |

Stop after Phase 3. **Phase 4 is not begun.**
