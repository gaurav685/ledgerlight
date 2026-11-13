# Governance Event Study — Pre-Registration Spec v1

**Frozen before any abnormal return is computed.** This document and
its machine-readable twin (`spec.v1.json`) are the pre-registered
methodology. Once the first real run's results exist, this file is
never edited in place — a methodology change becomes `spec.v2.md` /
`spec.v2.json`, and both versions (and both runs) are reported side
by side, never silently replaced.

Spec version: **v1**. Author: user-directed, implemented 2026-11-13.

**sha256 of `spec.v1.json`**: `74be99f7e34b2842066abf6466d3b12e8db06fec08705c035e526cbc67a69133`
(64 hex chars, independently recomputed and confirmed to match).
Registered in `model_registry` (`model_name="event-study-spec"`,
`model_version="v1"`) by `scripts/event_study_register_spec.py`,
which refuses to silently overwrite a version already registered
under a different hash -- the real freeze guard.

## 1. Real infrastructure this spec is grounded in (not assumed)

Checked directly against the live schema before writing this spec
(2026-11-13):

- `price_bars` (`ledgerlight/db/models.py`): NSE bhavcopy only — BSE
  is blocked at acquisition (`docs/phase-1/phase-1-report.md`).
  Columns used: `trade_date`, `symbol`, `close`, `prev_close`,
  `volume`, `turnover` (all `Numeric`, exact decimal arithmetic).
  **No split/corporate-action adjustment field exists at all** — a
  real, disclosed limitation (also flagged in
  `data/taxonomy/outcomes-v1.0.yaml`'s own `SEVERE_DRAWDOWN` entry).
  Real coverage as of this spec: 7,155 distinct symbols, trade dates
  2016-01-01 to 2026-10-30.
- No dedicated NSE holiday-calendar module exists anywhere in this
  repo. The trading-day index this study uses is built directly from
  the **real, distinct `price_bars.trade_date` values actually
  present** (the same precedent `ledgerlight/modelling/price_features.py`
  already uses for trading-day lookbacks) — a missing bhavcopy file
  for a real holiday is already absent from this index by
  construction; it is never separately inferred.
- `Event`/`EventType`/`Outcome` (`ledgerlight/knowledge/models.py`):
  `Event.status` ("candidate"|"verified"|"rejected"|"needs_review")
  is this project's own tier signal, normalized to "VERIFIED"/
  "CANDIDATE" elsewhere (`ledgerlight/agent/tools.py::_TIER_BY_STATUS`).
- `model_registry` (`ledgerlight/knowledge/models.py`): already exists,
  already used by `scripts/train_risk.py` via a raw-SQL upsert on
  `(model_name, model_version)`. Reused here, not duplicated.

## 2. Event types and their REAL verification status (checked, not assumed)

Checked directly: `SELECT count(*), status FROM events JOIN event_types
...` against the live DB, 2026-11-13.

| Event type | Real source | Real tier today | Real count today |
|---|---|---|---|
| CARE rating downgrade | `ledgerlight.modelling.rating_features.extract_rating_observations` (rule-extracted, span-verified against real CARE document text; the same function Phase 3's own model features use) | No tier concept — deterministic regex + real evidence span, not a probabilistic classifier | companies with >=1 CARE filing: **11** (exact downgrade-transition count depends on the real per-company rating sequences — reported as a real filter-stage count at run time, never pre-guessed) |
| CARE rating upgrade | Same function, contrast direction (ordinal decreases) | Same as above | Same universe (11 companies) |
| SEBI order against company | `Event` rows, `event_type.code = "SEBI_ORDER_AGAINST_COMPANY"` (`scripts/populate_outcomes.py::populate_sebi_orders`) | **VERIFIED** (`status="verified"` for every real row checked) | **69** real events |
| IBBI CIRP admission | `Event` rows, `event_type.code = "IBBI_CIRP_ADMISSION"` | **CANDIDATE** -- every one of the 31 real rows is `status="candidate"`, explicitly commented in `scripts/populate_outcomes.py` as "pending the brief's required human spot-check" | **31** real events, **0 verified** |

**A real, disclosed conflict in this brief's own instructions, resolved
explicitly, not silently:** the brief's own event-type list describes
IBBI admissions as "(auto-linked, verified)", but the brief's separate
instruction is "VERIFIED-tier governance events only... EVENT-CANDIDATE
events are excluded from the primary results." The real, current data
shows IBBI admissions are tier=CANDIDATE, not VERIFIED, in this
project's own database — "auto-linked" is true (entity resolution ran),
"verified" (in the tier sense this project uses everywhere else) is
not. Resolved by **treating IBBI admissions as a secondary,
exploratory arm, clearly labelled CANDIDATE-tier / pending human
review, excluded from the primary pre-registered significance claims**
-- consistent with this project's own standing convention (e.g.
`docs/phase-6/phase-6b-review-findings.md`'s own caveat about
AI/unreviewed decisions) of never treating an unreviewed candidate
finding as a validated fact. CARE rating downgrades/upgrades are not
gated by this tier system at all (they bypass the `Event`/tier
pipeline entirely, same as Phase 3's own model features) and are
treated as primary. SEBI orders are genuinely VERIFIED and primary.

**Primary event types** (pre-registered, hypothesis-testing claims
apply): CARE rating downgrade (by severity band, see §3), CARE rating
upgrade (contrast), SEBI order against company.

**Secondary/exploratory event type** (reported, but never claimed as
a confirmatory significance result): IBBI CIRP admission.

## 3. Severity bands (CARE downgrades only)

Using `ledgerlight.modelling.rating_features.RATING_SCALE`/
`RATING_ORDINAL` (AAA=0 best, D=19 worst) directly -- never a new
scale invented for this study:

- **within investment grade**: new rating ordinal <= 9 (BBB- or
  better) and the transition did not cross the investment-grade
  boundary.
- **crossing into sub-investment grade**: old ordinal <= 9, new
  ordinal in [10, 18] (BB+ down to C-).
- **to default (D)**: new ordinal == 19.

A downgrade is any transition where the new observation's ordinal is
strictly greater (worse) than the immediately preceding real
observation for that company; an upgrade is strictly lower (better).
`negative_outlook` transitions (no symbol change, outlook turns
negative) are NOT counted as a rating action for this study -- only a
real symbol change is an event, a disclosed, deliberate narrowing
(the brief's own "rating downgrades... (e.g., within investment
grade, crossing into sub-investment grade, to default D)" language
describes symbol-level severity bands, not outlook-only moves).

## 4. Event date and point-in-time correctness

- Event date = `known_at` (the real public-announcement timestamp;
  for CARE this is `document_versions.known_at`, for SEBI/IBBI the
  real `Event.known_at`), converted to its Asia/Kolkata calendar date
  (same `_format_ist_date`-style conversion as
  `ledgerlight.agent.render`, Phase 6 Correction 2 §3.2 -- reused, not
  reinvented).
- Mapped to **day 0** = the first real trading session (from the
  real trading-day index, §1) at or after that IST calendar date.
- **Both day 0 and day +1 are inside the primary CAR[-1,+1] window**
  (intraday announcement timing relative to market close is unknown,
  per the brief) -- this is a disclosed source of potential
  under/over-estimation of the true window, not resolved by this
  study.
- Point-in-time: an event is only ever included if its real `known_at`
  (or `document_versions.known_at` for CARE) predates the as-of date
  of any analysis that uses it -- the same discipline as every other
  point-in-time check in this project (`ledgerlight.agent.verifier.
  check_point_in_time`). This study does not predict anything forward
  in real time; it is a retrospective measurement, so this guards
  against accidentally using a LATER-arriving correction/restatement
  of an event's own date, not forecasting leakage.

## 5. Market model

- **Estimation window**: trading days [-250, -30] relative to day 0
  (on the real trading-day index, §1). Minimum **120 valid days**
  required (a valid day = the company's own `price_bars` row exists
  for that trading day with a non-null `close`); below that, the
  event is excluded (counted in the filter-stage report, §8).
- **Normal-return model**: market-model OLS,
  `R_it = alpha_i + beta_i * R_mt + e_it`, fit on the estimation
  window only, per company.
- **Market return, primary**: a value-weighted index built from real
  `price_bars.turnover` (the column that actually exists -- shares
  outstanding is not in this schema, so market *capitalization*
  weighting is not possible; **turnover-weighted is a real,
  documented substitute, not the textbook definition**, disclosed
  explicitly here and in every report this produces). Daily index
  return = sum over all real, liquid symbols trading that day of
  `turnover_it * return_it`, divided by `sum(turnover_it)` that day.
- **Market return, robustness**: equal-weighted index (simple mean of
  real daily returns across all liquid symbols trading that day).
- **No split/corporate-action adjustment** (§1) -- a real stock split
  or bonus issue inside a company's own window would show as a
  spurious, extreme single-day "return" in both the event company and
  (if large enough) the index. Not corrected in v1; disclosed as a
  real limitation, and any event whose own estimation or event window
  contains a |daily return| > 50% is flagged in the per-event output
  as `possible_corporate_action`, for a human to inspect, never
  silently dropped or silently trusted.

## 6. Event windows (all in real trading days, relative to day 0)

| Window | Purpose |
|---|---|
| CAR[-1,+1] | **Primary** |
| CAR[0,+5] | Short post-event |
| CAR[-10,+10] | Wider symmetric |
| CAR[-30,-1] | Pre-event drift (information leakage check) |
| CAR[+2,+60] | Post-event drift |

## 7. Filters (applied in this order; each stage's real removal count is reported, never only the final survivor count)

1. **Point-in-time validity** (§4).
2. **Estimation-window sufficiency**: >= 120 valid trading days in
   [-250,-30] (§5).
3. **Liquidity**: the company must have a real, non-null `close` for
   at least 80% of the real trading days in its own estimation
   window (a company suspended for most of that window fails here,
   not silently included with a stale carried-forward price).
4. **Confounding**: if this company has another INCLUDED event
   (any primary type, after filters 1-3) within +/-10 calendar days
   of this one, both events are flagged `confounded` and excluded
   from the primary CAR tables (reported separately, never merged
   into one event's window).
5. **Event-window data availability**: the company must have a real
   `close` for day 0 itself; a fully missing day inside a window is
   excluded from that specific window's own CAR sum (and the
   window's own real N for that event is reported, since window-level
   N can differ event-to-event under this rule).

## 8. Tests

- **Cross-sectional t-test** on each window's real CAR distribution
  across the surviving events of a type (standard Brown-Warner-style
  t, using the real cross-sectional standard deviation of CARs).
- **BMP (Boehmer-Musumeci-Poulsen) standardized residual test** --
  standardizes each event's abnormal return by its own real
  estimation-window residual standard deviation (with the real
  forecast-error correction term) before cross-sectional
  aggregation, so a handful of high-variance events cannot dominate.
- **Corrado rank test** -- non-parametric, ranks each company's real
  returns (event + estimation window pooled) and tests the rank sum
  in the event window; no distributional assumption on returns.
- **Calendar-time clustering**: this study's own real event dates are
  reported as a histogram by calendar month; if >= 20% of all primary
  events in a type fall in the same real calendar month, a
  Kolari-Pynnönen cross-sectional-correlation-adjusted test statistic
  is reported ALONGSIDE the plain BMP statistic for that type,
  explicitly flagged, rather than silently relying on an
  independence assumption clustering would violate.
- **Multiple testing**: Holm-Bonferroni correction applied across the
  real grid of (event type x window) p-values actually reported in
  one run -- never across a hypothetical larger grid, and the
  uncorrected p is always shown alongside the Holm-adjusted one.

## 9. Placebo

For each real included event's company, draw (deterministic seed,
§10) a **pseudo-event date** uniformly at random from that company's
own real trading days in the SAME calendar year as the real event
(year-matched, per the brief), excluding any date within 10 calendar
days of ANY real included event for that company (so a placebo can
never accidentally land on a real event). Compute the same primary
CAR[-1,+1] for the placebo date, using the same market model fit on
that placebo's own [-250,-30] estimation window. Repeat this whole
draw **1,000 times** per real event (reseeded deterministically each
iteration, §10). The real event's own CAR is reported against this
placebo distribution's real empirical percentile, not just its mean,
since the placebo distribution's own shape (not only its center)
matters for a fair comparison.

## 10. Determinism

Every random draw (placebo dates) uses `numpy.random.default_rng(seed)`
with a seed derived deterministically from
`(spec_sha256, event_id, placebo_iteration_index)` via a fixed hash
construction (never `random.random()`, never an unseeded generator,
never system time) -- so a re-run against the identical frozen input
data reproduces byte-identical placebo draws. The seed derivation
itself is specified in `spec.v1.json`'s own `"placebo_seed_formula"`
field, not left implicit in code comments alone.

## 11. What this study does NOT claim

- Not causal. An abnormal return around an event is a real market
  reaction measurement, never evidence that the event itself *caused*
  value change through any specific mechanism.
- Not investment advice, not a trading signal, not a recommendation.
- Not a replacement for, or a confirmation of, the separate 5-company
  risk-model finding (Phase 3/Phase 6) -- a different question (market
  reaction to an already-disclosed event, vs. forecasting an event
  before it happens) on an overlapping but not identical real sample.
- The IBBI admission arm (§2) is reported for completeness only; it
  is never used to support a primary significance claim, because its
  own real tier is CANDIDATE, not VERIFIED.
- `pymupdf`/document-extraction correctness for the underlying CARE/
  SEBI/IBBI documents is inherited, not re-verified here -- any real
  extraction error in those upstream pipelines propagates into this
  study's own event dates/types, same as every other consumer of
  that data in this project.
