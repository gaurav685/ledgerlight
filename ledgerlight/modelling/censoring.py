"""Real implementation of the two censoring rules documented in
`docs/modelling/outcomes.md` §5 and `data/modelling/outcomes-v1.0.json`'s
`censoring_policy` block -- this module is what makes "censoring
handled" (exit gate 3) a testable claim rather than only a documentation
promise. A company whose primary-outcome label would be a hard 0 only
because its trading stopped, or because the data simply hasn't caught
up yet, must be flagged RIGHT-CENSORED, never silently treated as a
confirmed negative.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

HORIZON_MONTHS = 12
BHAVCOPY_DISAPPEARANCE_MIN_GAP_DAYS = 90


@dataclass
class CensoringResult:
    censored: bool
    reason: str | None  # None iff censored is False


def _add_months(d: dt.date, months: int) -> dt.date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp the day for short months (e.g. 2026-01-31 + 1mo -> 2026-02-28).
    day = d.day
    while True:
        try:
            return dt.date(year, month, day)
        except ValueError:
            day -= 1


def check_censoring(
    as_of: dt.date,
    *,
    last_real_trade_date: dt.date | None,
    data_coverage_end: dt.date,
    verified_coverage_window: tuple[dt.date, dt.date] | None = None,
) -> CensoringResult:
    """Real censoring check for one (company, as_of) primary-outcome
    label window [as_of, as_of + 12 months).

    - `last_real_trade_date`: this company's own real, overall last EQ
      trade date across the full dataset (not just up to `as_of`) --
      for a company still trading at the end of this project's
      coverage, this is simply that coverage end date; for a company
      that genuinely stopped trading earlier, it is that real earlier
      date. None if the company never traded at all (handled
      explicitly rather than assumed, though it should not occur for a
      company with a real feature snapshot).
    - `data_coverage_end`: this project's own real data coverage end
      (e.g. `price_bars`'s own max trade_date) -- the actual, observed
      limit, never today's wall-clock date.
    - `verified_coverage_window`: the real `(window_start, window_end)`
      from `ledgerlight.modelling.coverage.compute_verified_coverage`
      -- the period during which BOTH IBBI and CARE (rating) sources
      were actually checked for this company, per the user's explicit
      condition (2026-10-31). `None` skips this check (e.g. for
      callers evaluating a secondary outcome that doesn't need both
      sources).

    Three independent reasons, checked in order so the most fundamental
    one wins when more than one applies:

    1. `unverified_source_coverage` -- `as_of` itself precedes the
       verified coverage window, or the forward horizon extends past
       its end. Neither IBBI nor CARE discovery was confirmed to have
       been checked for this period, so a "no trigger observed" result
       here is not evidence of a real negative -- it may simply be
       unchecked.
    2. `unknown_trading_stop` -- this company has a REAL, confirmed
       gap (>= 90 days) between its last trade and the end of this
       project's data coverage (i.e. `BHAVCOPY_DISAPPEARANCE` really
       fired for it), and this window's forward horizon extends past
       the point the gap began. A company still trading at the end of
       coverage never triggers this -- its own "last trade" IS the
       coverage end, so no real gap exists to confirm a disappearance.
    3. `end_of_window_observation` -- the forward window simply runs
       past the end of real data coverage, independent of whether this
       company disappeared early. Applies to every company near the
       end of the dataset.
    """
    window_end = _add_months(as_of, HORIZON_MONTHS)

    if verified_coverage_window is not None:
        coverage_start, coverage_end = verified_coverage_window
        if as_of < coverage_start or window_end > coverage_end:
            return CensoringResult(
                True,
                f"unverified_source_coverage: as_of {as_of} / forward window end "
                f"{window_end} falls outside the real verified IBBI+CARE coverage "
                f"window [{coverage_start}, {coverage_end}]",
            )

    if last_real_trade_date is not None:
        real_gap_days = (data_coverage_end - last_real_trade_date).days
        disappeared = real_gap_days >= BHAVCOPY_DISAPPEARANCE_MIN_GAP_DAYS
        disappearance_cutoff = last_real_trade_date + dt.timedelta(
            days=BHAVCOPY_DISAPPEARANCE_MIN_GAP_DAYS
        )
        if disappeared and window_end > disappearance_cutoff:
            return CensoringResult(
                True,
                f"unknown_trading_stop: real disappearance confirmed (last trade "
                f"{last_real_trade_date}, {real_gap_days}d before coverage end "
                f"{data_coverage_end}); forward window ends {window_end}, after the "
                f"disappearance cutoff {disappearance_cutoff}",
            )

    if window_end > data_coverage_end:
        return CensoringResult(
            True,
            f"end_of_window_observation: forward window ends {window_end}, "
            f"after real data coverage end {data_coverage_end}",
        )

    return CensoringResult(False, None)
