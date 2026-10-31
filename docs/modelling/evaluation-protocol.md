# Walk-Forward Evaluation Protocol (Phase 3 §7)

Status: **designed, not yet executed.** Per the user's explicit condition, no training,
tuning, or backtest runs until the full-universe IBBI discovery crawl has finished or is
honestly stopped with its coverage recorded (`docs/modelling/data-quality.md`). This
document specifies the methodology so execution, once unblocked, follows a frozen protocol
rather than being designed after seeing results.

## Fold structure

- Expanding-window, yearly outer folds.
- Train: `as_of < T - H - embargo`, where `H` = 12 months (the outcome horizon,
  `docs/modelling/outcomes.md`).
- Test: `as_of in [T, T+1y)`.
- Embargo: at least 12 months between the end of a training window and the start of its
  test window, so no training label's own 12-month forward outcome window can overlap the
  test period it is being evaluated against.
- The real `as_of` grid spans 2016-01-31 to 2026-10-31 (`docs/modelling/data-quality.md`).
  Given `H` + embargo = 24 months minimum between a fold's train cutoff and its test start,
  the usable outer-fold years run from approximately 2018 through the most recent year
  with a full, non-right-censored 12-month-forward window.
- The fold table (dates, companies, observations, positives per fold) will be printed and
  committed as real output when §7 runs -- not estimated here.

## Metrics (per fold and pooled, each with real counts)

- PR-AUC vs. prevalence (the real baseline rate, not an assumed 0.5).
- ROC-AUC (secondary -- PR-AUC is primary given real class imbalance).
- Precision@K: top 1% and top 50 per month.
- Recall at a fixed alert rate.
- Brier score and Brier skill score vs. the real base rate.
- ECE (expected calibration error) plus a reliability diagram.
- Lead time: median real days from the first alert above threshold to the real outcome
  date, for true positives only.

## Uncertainty

- Company-clustered bootstrap, 95% intervals, on every key metric (clustering by company
  so a single company's correlated monthly observations don't understate the real
  variance).
- **Real, final count, after the full-universe IBBI crawl was honestly stopped and
  outcomes rebuilt (2026-10-31)**: the real pooled `PRIMARY_DISTRESS` positive count
  (`IBBI_CIRP_ADMISSION` 31 ∪ `RATING_DOWNGRADE_D` 14, by distinct company) is **31** --
  right at the brief's own 30-positive floor for "statistically inconclusive, no
  predictive-skill claim." This number is itself the product of catching and fixing two
  real detection bugs found by direct inspection during the rebuild (a naive heuristic
  had inflated it to 101 before the fixes -- see `docs/modelling/outcomes.md` §2.1). Stated
  here plainly, before any model is trained: whichever side of the 30-positive line the
  real walk-forward split's pooled count lands on, it will be reported as such, not hidden
  or hedged around with an unjustified threshold change.

## Leakage checks (automated tests AND a report)

| Check | Status | Where |
|---|---|---|
| `max_input_known_at <= as_of` for every snapshot | **DONE** | `tests/test_point_in_time_integrity.py`; query in `docs/phase-3/evidence/point-in-time-proof.log` (100%, 0 violations, exit gate 4) |
| Outcome date > as_of for every label | Designed, not yet implemented as a standalone test | to be added alongside the walk-forward fold builder |
| Time-ordered folds with the embargo enforced | Designed (see Fold structure above) | to be implemented as part of the fold builder itself |
| Label-permutation test: performance roughly at prevalence | Not yet run | requires a trained model (§6, blocked) |
| Feature-shift test: shifting features forward must make performance worse | Not yet run | requires a trained model (§6, blocked) |
| Flag any feature with univariate PR-AUC near 1.0 | Not yet run | requires real training data labelled and split (§6, blocked) |
| A deliberately leaky synthetic feature must be caught, proven | Not yet run | requires the above test harness to exist first |

## Survivorship

Report every metric both with and without later-delisted companies, and separately list
the companies and observation-count lost by excluding them. The real universe already
includes later-delisted companies by construction (`docs/phase-3/progress.md`'s §4.1
entry: "the universe at each as_of is the companies trading in that period's bhavcopy,
INCLUDING those later delisted" -- enforced, not assumed), so this report is a real
comparison, not a caveat about missing data.

## Data-quality report (§7's own requirement, distinct from `data-quality.md`)

To be generated at evaluation time, from the real built snapshots: missingness by feature
and year (every `data_quality_flags` entry already recorded per snapshot, see §4.1-4.3);
rating and IBBI coverage over time (real counts already available from
`docs/modelling/data-quality.md`, refreshed post-crawl); entity-link exclusions (the real
`unresolved` counts from `scripts/link_filings.py`'s own output, see
`docs/phase-3/evidence/link-filings-run-post-sec3-broadening.log`); bhavcopy gaps (none
known beyond the already-fixed 2016-01 to 2017-01-04 parsing gap, §2.1).

## Ablation arms

- (a) STRUCTURED only (`price-liquidity-1.0`).
- (b) (a) + RULE-VERIFIED (`rule-verified-1.0`).
- (c) (b) + EVENT-CANDIDATE, unverified (SEED-track governance features, §4.3 -- disclosed
  as near-all-CANDIDATE tier with the known_at-clustering caveat already documented).
  Report the deltas with intervals; if (c) adds nothing measurable, or hurts, say so
  plainly -- this is a real, live possibility given §4.3's own disclosed limitations on
  the EVENT-CANDIDATE tier's temporal signal quality.
