# §1.3 real data-quality report: corporate-action detection

Final real run (after the calendar-gap fix in
`ledgerlight/modelling/price_adjustment.py` and the real daily-density
backfill documented in
`evidence-sec1-ingestion-gap-and-backfill.md`):
`scripts/detect_price_adjustments.py --apply`, all 3,847 real EQ
ISINs, real trading-day index now 2,183 days (up from 1,411 before
the backfill).

## Real detected corporate-action factors, by year

| year | detected |
|------|----------|
| 2016 | 626 |
| 2017 | 288 |
| 2018 | 310 |
| 2019 | 558 |
| 2020 | 852 |
| 2021 | 76 |
| 2022 | 199 |
| 2023 | 78 |
| 2024 | 0 |
| 2025 | 45 |
| 2026 | 214 |
| **total** | **3,246** |

Honest reading, not glossed over:

- 2024 shows 0, and 2025 shows only 45 (vs. a few hundred in other
  full-density years). Both years are still at the original sparse
  twice-monthly ingestion density (real data gap, documented in
  `evidence-sec1-ingestion-gap-and-backfill.md`, not fixable within
  this session). This is **not** "no corporate actions happened in
  2024" -- it is "we lack the daily resolution to detect them for
  2024, and only partial resolution for 2025." The calendar-gap fix
  means this shows up as an honest near-zero rather than a wrong
  detection.
- 2020 (852) is real but elevated relative to neighbouring years
  (2019: 558, 2021: 76) -- plausibly real COVID-era volatility
  (genuine large single-day moves that happened to fall within
  `RATIO_MATCH_TOLERANCE` of a plausible ratio by chance) layered on
  top of genuine 2020 corporate actions. Not independently verified
  against public sources beyond the 5 cases already checked in
  `evidence-sec1-corporate-action-verification.md`; flagged here for
  awareness rather than asserted as fact.
- 3,246 total real detections across 3,847 real ISINs over ~9 years
  of real daily (where available) history is a plausible order of
  magnitude (well under 1 per ISIN-year on average) -- not the
  implausible 8,688 the pre-fix run produced.

## Real residual suspicious jumps (no plausible ratio match)

268 total; the script is deliberately memory-bounded (`heapq`,
`TOP_N_RESIDUALS_KEPT = 50`) and keeps only the top 50 by magnitude
for human review rather than holding all 268 in memory at once --
consistent with this project's own standing "prefer bounded memory"
constraint. The full 50 are in
`/tmp/detect_run_final4.log`-style script output (reproducible by
re-running `scripts/detect_price_adjustments.py` without `--apply`);
the most informative real patterns among them:

- **Real ETF/gold-ETF unit splits** (ratio ~0.01, i.e. 1:100): GOLDBEES,
  SETFGOLD, GOLDSHARE, BSLGOLDETF, AXISGOLD, QGOLDHALF, HDFCMFGETF,
  UTIBANKETF, UTINEXT50, UTISXN50, AXISNIFTY, HNGSNGBEES. This is a
  **real, different class of corporate action** (a fund's unit-NAV
  rebase, not a share bonus/split) that
  `ledgerlight.modelling.price_adjustment.PLAUSIBLE_RATIOS` correctly
  does **not** claim to recognize (it was only ever validated against
  real share bonus/split ratios) -- reported honestly as a residual
  for human review rather than silently force-matched. A real,
  disclosed scope gap: ETF unit splits are not covered by this
  detector and would need their own curated ratio set (e.g. 1:100,
  1:10) if adjusted-ETF-price support is ever wanted.
- **Real, independently known large single-day moves with no
  corporate action**: JETAIRWAYS (2019-06-20, the real start of its
  trading collapse before its later suspension), BAJAJFINSV
  (2022-09-13, a real, large single-day drop around a real index
  rebalancing/profit-booking day, not a split), TATASTEEL /
  SRF / JUBLFOOD / CANFINHOME and others -- all real, large,
  genuine-looking single-session moves that do not match any curated
  ratio, correctly left unadjusted.
- A few older small/illiquid names (SUNILHITEC, DAAWAT, VGUARD-dated-
  2016, GAL, PRAKASHSTL) with large real moves not matching a
  plausible ratio -- plausible candidates for manual corporate-action
  research if this list is used for follow-up, but not claimed as
  confirmed here.

## What was NOT done (disclosed, not silently skipped)

- ETF/fund unit-split ratios are not in `PLAUSIBLE_RATIOS` -- flagged
  above, not implemented (out of the brief's own stated scope, which
  is share bonus/split detection).
- 2024 and most of 2025 remain at sparse density; not fixable this
  session (see `evidence-sec1-ingestion-gap-and-backfill.md`).
- The 2020 elevated count is not independently verified beyond the
  method's own 5-case validation; flagged as a real open question,
  not resolved here.
