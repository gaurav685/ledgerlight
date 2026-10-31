"""Tests for ledgerlight.modelling.price_features -- pure functions, no
DB. Each case uses a small, hand-computable synthetic price series so
the expected value can be checked by arithmetic, not just "it runs"."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from ledgerlight.modelling.price_features import (
    Bar,
    amihud_illiquidity,
    distance_from_52w_high,
    downside_volatility,
    max_drawdown,
    simple_return,
    turnover_trend,
    volatility,
)


def _bars(closes: list[float], turnovers: list[float] | None = None) -> list[Bar]:
    start = dt.date(2020, 1, 1)
    turnovers = turnovers or [1000.0] * len(closes)
    return [
        (start + dt.timedelta(days=i), Decimal(str(c)), 100, Decimal(str(t)))
        for i, (c, t) in enumerate(zip(closes, turnovers, strict=True))
    ]


def test_simple_return_exact_arithmetic() -> None:
    bars = _bars([100.0] * 10 + [110.0])
    result = simple_return(bars, idx=10, lookback=10)
    assert result.flag is None
    assert abs(result.value - 0.10) < 1e-9


def test_simple_return_insufficient_history_flagged_not_fabricated() -> None:
    bars = _bars([100.0, 101.0])
    result = simple_return(bars, idx=1, lookback=10)
    assert result.value is None
    assert result.flag == "insufficient_history_10d"


def test_volatility_zero_for_constant_price() -> None:
    bars = _bars([100.0] * 70)
    result = volatility(bars, idx=69, lookback=63)
    assert result.flag is None
    assert abs(result.value) < 1e-9


def test_volatility_positive_for_alternating_price() -> None:
    closes = [100.0 if i % 2 == 0 else 110.0 for i in range(70)]
    bars = _bars(closes)
    result = volatility(bars, idx=69, lookback=63)
    assert result.flag is None
    assert result.value > 0


def test_max_drawdown_exact_arithmetic() -> None:
    # Rises to 120 then falls to 90: max drawdown = 90/120 - 1 = -0.25
    closes = [100.0] * 5 + [120.0] + [100.0, 90.0] + [100.0] * 245
    bars = _bars(closes)
    result = max_drawdown(bars, idx=7, lookback=7)
    assert result.flag is None
    assert abs(result.value - (-0.25)) < 1e-9


def test_max_drawdown_zero_when_monotonically_rising() -> None:
    closes = [100.0 + i for i in range(260)]
    bars = _bars(closes)
    result = max_drawdown(bars, idx=259, lookback=252)
    assert result.flag is None
    assert result.value == 0.0


def test_downside_volatility_ignores_positive_days() -> None:
    # Half the days flat (0% return), half down 10% -- only the down
    # days should enter the downside-vol calc.
    closes = [100.0]
    for _ in range(130):
        closes.append(closes[-1])
        closes.append(closes[-1] * 0.9)
    bars = _bars(closes)
    result = downside_volatility(bars, idx=len(bars) - 1, lookback=252)
    assert result.flag is None
    assert result.value > 0


def test_turnover_trend_exact_ratio() -> None:
    turnovers = [100.0] * 231 + [200.0] * 21  # last 21 days double the rest
    closes = [100.0] * 252
    bars = _bars(closes, turnovers)
    result = turnover_trend(bars, idx=251, short_lookback=21, long_lookback=252)
    assert result.flag is None
    # long mean = (231*100 + 21*200)/252 ; short mean = 200
    expected_long_mean = (231 * 100.0 + 21 * 200.0) / 252
    assert abs(result.value - (200.0 / expected_long_mean)) < 1e-9


def test_amihud_illiquidity_higher_for_lower_turnover() -> None:
    closes = [100.0, 110.0] * 11
    bars_illiquid = _bars(closes, turnovers=[10.0] * 22)
    bars_liquid = _bars(closes, turnovers=[10000.0] * 22)
    illiquid = amihud_illiquidity(bars_illiquid, idx=21, lookback=21)
    liquid = amihud_illiquidity(bars_liquid, idx=21, lookback=21)
    assert illiquid.flag is None and liquid.flag is None
    assert illiquid.value > liquid.value


def test_amihud_illiquidity_succeeds_at_exact_lookback_boundary() -> None:
    """Real off-by-one regression: exactly `lookback` days of history
    (idx == lookback - 1) must succeed, not be flagged insufficient."""
    closes = [100.0, 110.0] * 11  # 22 bars, idx 0..21
    bars = _bars(closes, turnovers=[1000.0] * 22)
    result = amihud_illiquidity(bars, idx=20, lookback=21)
    assert result.flag is None


def test_distance_from_52w_high_at_the_high_is_zero() -> None:
    closes = [100.0 + i for i in range(253)]  # monotonically rising -> today is the high
    bars = _bars(closes)
    result = distance_from_52w_high(bars, idx=252, lookback=252)
    assert result.flag is None
    assert result.value == 0.0


def test_distance_from_52w_high_below_high_is_negative() -> None:
    closes = [100.0] * 100 + [200.0] + [100.0] * 152
    bars = _bars(closes)
    result = distance_from_52w_high(bars, idx=252, lookback=252)
    assert result.flag is None
    assert abs(result.value - (100.0 / 200.0 - 1.0)) < 1e-9
