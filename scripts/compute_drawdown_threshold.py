"""Phase 3 Sec3: compute a real, data-justified severe-drawdown threshold
X for the secondary outcome ("12-month return at least X percentage
points below the market median"), rather than picking an arbitrary round
number. Uses real price_bars (EQ series only -- the single primary
equity listing per company, avoiding double-counting the debt/bond
series the Phase 3 Sec2.4 company-dedup work found share a symbol).

Method: for every month-end date with EQ trading data, for every symbol
with both a close price that month and a close price ~12 months earlier
(within a +/-10 day tolerance for weekends/holidays), compute the trailing
12-month return. Compute the cross-sectional median return per month-end,
and each company's excess return (its own return minus that month's
median). Pool every (symbol, month-end) excess-return observation across
the whole window and report real percentiles -- X is chosen as a stated
percentile of this real, pooled, empirical distribution (documented in
docs/modelling/outcomes.md), not assumed.

**A real contamination was found and must be disclosed, not silently
fixed**: the raw computation's most extreme "drawdowns" are gold ETFs
(GOLDSHARE, HDFCMFGETF, BSLGOLDETF) showing ~99% "losses" that are
actually a real, documented 2021 100:1 unit-value restructuring, not
economic loss -- price_bars is not corporate-action/split-adjusted, and
this project has no compliant source for that adjustment yet. Two
mitigations, both reported alongside the raw figures so the real and
the adjusted numbers stay visible side by side:
1. A symbol-pattern heuristic excludes known ETF-style names (BEES,
   ETF, GOLDSHARE, LIQUID, GOLD, SILVER suffixes/substrings) --
   necessarily imperfect (bhavcopy carries no instrument-type field
   distinguishing a fund from an operating company at all), not a
   claim of completeness.
2. A winsorization bound discards any single-symbol return more
   extreme than +/-90% as a likely unadjusted corporate action rather
   than real performance -- a crude, disclosed backstop, not a
   real split-adjustment pipeline. Building one properly (e.g. from a
   compliant corporate-actions source) is future work, not invented
   here under time pressure.

Usage: python scripts/compute_drawdown_threshold.py
"""

from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import PriceBar  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402

TOLERANCE_DAYS = 10
LOOKBACK_DAYS = 365
WINSORIZE_ABS_RETURN = 0.90  # discard a single-symbol return more extreme than this

_ETF_PATTERN_SUBSTRINGS = ("ETF", "BEES", "GOLDSHARE", "LIQUID", "GOLD", "SILVER")


def _looks_like_etf(symbol: str) -> bool:
    upper = symbol.upper()
    return any(pattern in upper for pattern in _ETF_PATTERN_SUBSTRINGS)


def _month_end_dates(all_dates: set[dt.date]) -> list[dt.date]:
    by_month: dict[tuple[int, int], dt.date] = {}
    for d in all_dates:
        key = (d.year, d.month)
        if key not in by_month or d > by_month[key]:
            by_month[key] = d
    return sorted(by_month.values())


def _nearest_within(
    target: dt.date, available: Mapping[dt.date, object], tolerance: int
) -> dt.date | None:
    if target in available:
        return target
    for delta in range(1, tolerance + 1):
        for candidate in (target + dt.timedelta(days=delta), target - dt.timedelta(days=delta)):
            if candidate in available:
                return candidate
    return None


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        rows = session.execute(
            select(PriceBar.trade_date, PriceBar.symbol, PriceBar.close).where(
                PriceBar.series == "EQ", PriceBar.close.isnot(None)
            )
        ).all()
        print(f"EQ rows loaded: {len(rows)}")

        by_date_symbol: dict[dt.date, dict[str, float]] = defaultdict(dict)
        all_dates: set[dt.date] = set()
        for trade_date, symbol, close in rows:
            if close is None:
                continue
            by_date_symbol[trade_date][symbol] = float(close)
            all_dates.add(trade_date)

        month_ends = _month_end_dates(all_dates)
        print(f"month-end dates: {len(month_ends)} ({month_ends[0]} to {month_ends[-1]})")

        def _median(values: list[float]) -> float:
            s = sorted(values)
            n = len(s)
            return s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2

        def _report(label: str, excess_returns: list[float]) -> None:
            excess_returns = sorted(excess_returns)
            n = len(excess_returns)
            print(f"-- {label}: {n} observations --")
            for pct in (1, 2, 5, 10, 25, 50):
                idx = min(int(n * pct / 100), n - 1)
                print(f"  p{pct}: {excess_returns[idx] * 100:.2f} pp")

        excess_returns_raw: list[float] = []
        excess_returns_filtered: list[float] = []
        months_with_data = 0
        for month_end in month_ends:
            prior_target = month_end - dt.timedelta(days=LOOKBACK_DAYS)
            prior_date = _nearest_within(prior_target, by_date_symbol, TOLERANCE_DAYS)
            if prior_date is None:
                continue

            now_prices = by_date_symbol[month_end]
            prior_prices = by_date_symbol[prior_date]

            returns: dict[str, float] = {}
            for symbol, now_price in now_prices.items():
                prior_price = prior_prices.get(symbol)
                if prior_price is None or prior_price <= 0:
                    continue
                returns[symbol] = (now_price / prior_price) - 1.0

            if len(returns) < 20:  # too few companies to trust a median that month
                continue
            months_with_data += 1

            clean_returns = {
                sym: r
                for sym, r in returns.items()
                if not _looks_like_etf(sym) and abs(r) <= WINSORIZE_ABS_RETURN
            }
            if len(clean_returns) < 20:
                continue

            median_raw = _median(list(returns.values()))
            median_clean = _median(list(clean_returns.values()))
            for r in returns.values():
                excess_returns_raw.append(r - median_raw)
            for r in clean_returns.values():
                excess_returns_filtered.append(r - median_clean)

        print(f"months with usable data: {months_with_data}")
        _report("RAW (unfiltered, includes ETF/split artifacts)", excess_returns_raw)
        _report("FILTERED (ETF-pattern excluded, winsorized at +/-90%)", excess_returns_filtered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
