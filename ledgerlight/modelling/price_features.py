"""Pure, STRUCTURED (price/volume-only) point-in-time feature functions
for Phase 3 Sec4's UNIVERSE track -- price and liquidity. Every function
takes a single company's real trading history up to and including a
given as-of trading date and returns one feature value, or None when
there isn't enough real history (never a fabricated/imputed number --
the caller records that as a `data_quality_flag` instead).

Lookbacks are counted in real TRADING days (21/63/126/252 ~ 1/3/6/12
months), not calendar days -- this avoids ambiguity from non-trading
days (weekends, exchange holidays) that a calendar lookback would need
a tolerance window for for every single lookback length.

Each function receives `history`: the company's own EQ price_bars,
sorted ascending by trade_date, as (trade_date, close, volume, turnover)
tuples, truncated by the caller to rows with known_at <= as_of already
(point-in-time safety is the caller's responsibility -- see
scripts/build_feature_snapshots.py). `idx` is the index of the as-of
trading date within that history.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

Bar = tuple[
    dt.date, Decimal | None, int | None, Decimal | None
]  # (trade_date, close, volume, turnover)

LOOKBACKS_TRADING_DAYS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}


@dataclass
class FeatureValue:
    value: float | None
    flag: str | None  # e.g. "insufficient_history_12m" -- set iff value is None


def _close(bar: Bar) -> float | None:
    return float(bar[1]) if bar[1] is not None else None


def simple_return(history: Sequence[Bar], idx: int, lookback: int) -> FeatureValue:
    """(close[idx] / close[idx-lookback]) - 1. Needs `lookback` real
    trading days of history strictly before idx, plus idx itself."""
    if idx < lookback:
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    now = _close(history[idx])
    prior = _close(history[idx - lookback])
    if now is None or prior is None or prior == 0:
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    return FeatureValue(now / prior - 1.0, None)


def _daily_returns(history: Sequence[Bar], idx: int, lookback: int) -> list[float] | None:
    if idx < lookback:
        return None
    closes = [_close(history[i]) for i in range(idx - lookback, idx + 1)]
    if any(c is None for c in closes):
        return None
    returns = []
    for i in range(1, len(closes)):
        prev_c = closes[i - 1]
        cur_c = closes[i]
        assert prev_c is not None and cur_c is not None
        if prev_c == 0:
            return None
        returns.append(cur_c / prev_c - 1.0)
    return returns


def volatility(history: Sequence[Bar], idx: int, lookback: int = 63) -> FeatureValue:
    """Annualized stdev of daily returns over the trailing `lookback`
    trading days (default 63 ~ 3 months), scaled by sqrt(252)."""
    returns = _daily_returns(history, idx, lookback)
    if returns is None or len(returns) < 2:
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return FeatureValue(math.sqrt(variance) * math.sqrt(252), None)


def downside_volatility(history: Sequence[Bar], idx: int, lookback: int = 252) -> FeatureValue:
    """Annualized stdev of only the NEGATIVE daily returns over the
    trailing `lookback` trading days (default 252 ~ 12 months)."""
    returns = _daily_returns(history, idx, lookback)
    if returns is None:
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    negative = [r for r in returns if r < 0]
    if len(negative) < 2:
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    mean = sum(negative) / len(negative)
    variance = sum((r - mean) ** 2 for r in negative) / (len(negative) - 1)
    return FeatureValue(math.sqrt(variance) * math.sqrt(252), None)


def max_drawdown(history: Sequence[Bar], idx: int, lookback: int = 252) -> FeatureValue:
    """Most negative (close / running_max_close - 1) over the trailing
    `lookback` trading days (default 252 ~ 12 months). 0 = never below
    its own running high in the window; negative = real drawdown."""
    if idx < lookback:
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    closes = [_close(history[i]) for i in range(idx - lookback, idx + 1)]
    if any(c is None for c in closes):
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    running_max = closes[0]
    assert running_max is not None
    worst = 0.0
    for c in closes:
        assert c is not None
        running_max = max(running_max, c)
        if running_max > 0:
            worst = min(worst, c / running_max - 1.0)
    return FeatureValue(worst, None)


def turnover_trend(
    history: Sequence[Bar], idx: int, short_lookback: int = 21, long_lookback: int = 252
) -> FeatureValue:
    """mean(turnover, trailing short_lookback) / mean(turnover, trailing
    long_lookback) -- >1 means recent trading activity is elevated
    relative to the company's own trailing-year norm."""
    if idx < long_lookback - 1:
        return FeatureValue(None, f"insufficient_history_{long_lookback}d")
    short_vals = [history[i][3] for i in range(idx - short_lookback + 1, idx + 1)]
    long_vals = [history[i][3] for i in range(idx - long_lookback + 1, idx + 1)]
    if any(v is None for v in short_vals) or any(v is None for v in long_vals):
        return FeatureValue(None, f"insufficient_history_{long_lookback}d")
    short_mean = float(sum(v for v in short_vals if v is not None)) / len(short_vals)
    long_mean = float(sum(v for v in long_vals if v is not None)) / len(long_vals)
    if long_mean == 0:
        return FeatureValue(None, "zero_turnover_denominator")
    return FeatureValue(short_mean / long_mean, None)


def amihud_illiquidity(history: Sequence[Bar], idx: int, lookback: int = 21) -> FeatureValue:
    """Amihud (2002) illiquidity proxy: mean(|daily_return| / turnover)
    over the trailing `lookback` trading days (default 21 ~ 1 month),
    scaled by 1e6 purely for a readable magnitude. Higher = less liquid
    (a given return took less turnover to produce, or vice versa --
    the classic reading is units of price-impact per rupee traded)."""
    if idx < lookback - 1:
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    ratios = []
    for i in range(idx - lookback + 1, idx + 1):
        if i == 0:
            continue
        prev_close = _close(history[i - 1])
        cur_close = _close(history[i])
        turnover = history[i][3]
        if prev_close is None or cur_close is None or turnover is None or prev_close == 0:
            continue
        if turnover == 0:
            continue
        daily_return = abs(cur_close / prev_close - 1.0)
        ratios.append(daily_return / float(turnover))
    if len(ratios) < max(2, lookback // 2):
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    return FeatureValue((sum(ratios) / len(ratios)) * 1_000_000.0, None)


def distance_from_52w_high(history: Sequence[Bar], idx: int, lookback: int = 252) -> FeatureValue:
    """close[idx] / max(close over trailing `lookback` trading days) - 1.
    0 = at its own 52-week high; negative = below it."""
    if idx < lookback:
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    closes = [_close(history[i]) for i in range(idx - lookback, idx + 1)]
    if any(c is None for c in closes):
        return FeatureValue(None, f"insufficient_history_{lookback}d")
    non_null_closes = [c for c in closes if c is not None]
    now = non_null_closes[-1]
    high = max(non_null_closes)
    if high == 0:
        return FeatureValue(None, "zero_high_denominator")
    return FeatureValue(now / high - 1.0, None)
