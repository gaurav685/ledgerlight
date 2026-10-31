"""Phase 3 Sec4.1: build the UNIVERSE track's STRUCTURED price/liquidity
feature snapshots -- the first real feature group, per the brief's
feature policy (PRIMARY model uses STRUCTURED and RULE-VERIFIED features
only). Monthly (month-end) `as_of`, from 2016-01 (the real,
exhaustively-confirmed earliest bhavcopy coverage -- see Sec2.1) through
the end of real `price_bars` coverage.

Universe membership per `as_of` month, per the brief: "the universe at
each as_of is the companies trading in that period's bhavcopy, INCLUDING
those later delisted." A company is only snapshotted for a month it
actually traded in -- not merely "most recent earlier trade" -- so a
company that stops trading simply stops appearing, it is never carried
forward on stale data.

Point-in-time safety: the snapshot trading date for a given `as_of`
month is the LATEST real trade within that month whose underlying
bhavcopy `known_at` <= `as_of`. `max_input_known_at` on the snapshot
is that trade's own `known_at` -- since every earlier trade in the same
company's series has an earlier-or-equal known_at (one reliable
source, nse_archives), this is a safe upper bound on everything the
lookback windows actually read, not merely a convenient value.

A feature that lacks enough real lookback history is recorded as `None`
in `values` with a matching reason in `data_quality_flags` -- never
imputed, never silently dropped from the row.
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.modelling.price_features import (  # noqa: E402
    Bar,
    amihud_illiquidity,
    distance_from_52w_high,
    downside_volatility,
    max_drawdown,
    simple_return,
    turnover_trend,
    volatility,
)

FEATURE_SET_VERSION = "price-liquidity-1.0"

FEATURE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "ret_1m",
        "lookback_days": 21,
        "description": "Simple return over the trailing 21 real trading days (~1 month).",
    },
    {
        "name": "ret_3m",
        "lookback_days": 63,
        "description": "Simple return over the trailing 63 real trading days (~3 months).",
    },
    {
        "name": "ret_6m",
        "lookback_days": 126,
        "description": "Simple return over the trailing 126 real trading days (~6 months).",
    },
    {
        "name": "ret_12m",
        "lookback_days": 252,
        "description": "Simple return over the trailing 252 real trading days (~12 months).",
    },
    {
        "name": "volatility_3m",
        "lookback_days": 63,
        "description": (
            "Annualized stdev of daily returns over the trailing 63 real trading days "
            "(scaled by sqrt(252))."
        ),
    },
    {
        "name": "downside_volatility_12m",
        "lookback_days": 252,
        "description": (
            "Annualized stdev of only the negative daily returns over the trailing "
            "252 real trading days."
        ),
    },
    {
        "name": "max_drawdown_12m",
        "lookback_days": 252,
        "description": (
            "Most negative (close / trailing running-max close - 1) over the trailing "
            "252 real trading days."
        ),
    },
    {
        "name": "turnover_trend_1m_12m",
        "lookback_days": 252,
        "description": (
            "Mean turnover over the trailing 21 real trading days divided by mean "
            "turnover over the trailing 252 real trading days."
        ),
    },
    {
        "name": "amihud_illiquidity_1m",
        "lookback_days": 21,
        "description": (
            "Amihud (2002) illiquidity proxy: mean(|daily return| / turnover) over the "
            "trailing 21 real trading days, scaled by 1e6."
        ),
    },
    {
        "name": "distance_from_52w_high",
        "lookback_days": 252,
        "description": (
            "close / max(close over the trailing 252 real trading days) - 1; 0 = at the "
            "52-week high."
        ),
    },
]

_AS_OF_SEMANTICS = (
    "Month-end as_of. Snapshot trading date = the latest real trade within that "
    "calendar month whose bhavcopy known_at <= as_of. Lookback windows read only "
    "trades at or before that date."
)


def _ensure_feature_definitions(session: Any) -> None:
    for fd in FEATURE_DEFINITIONS:
        session.execute(
            text(
                "INSERT INTO feature_definitions "
                "(id, name, version, description, inputs, provenance_tier, "
                " as_of_semantics, lookback_days, track) "
                "VALUES (:id, :name, :version, :description, :inputs, 'STRUCTURED', "
                " :as_of_semantics, :lookback_days, 'UNIVERSE') "
                "ON CONFLICT (name, version) DO NOTHING"
            ),
            {
                "id": uuid.uuid4(),
                "name": fd["name"],
                "version": FEATURE_SET_VERSION,
                "description": fd["description"],
                "inputs": '["price_bars.close", "price_bars.turnover"]',
                "as_of_semantics": _AS_OF_SEMANTICS,
                "lookback_days": fd["lookback_days"],
            },
        )
    session.commit()


def _load_company_series(session: Any) -> dict[uuid.UUID, list[tuple[dt.date, Bar, dt.datetime]]]:
    """One company_id -> sorted list of (trade_date, Bar, known_at).
    Bar is (trade_date, close, volume, turnover) for price_features."""
    rows = session.execute(
        text(
            """
            SELECT ci.company_id, pb.trade_date, pb.close, pb.volume, pb.turnover, dv.known_at
            FROM price_bars pb
            JOIN company_identifiers ci
              ON ci.identifier_type = 'NSE_SYMBOL' AND ci.value = pb.symbol
              AND pb.trade_date >= ci.valid_from
              AND (ci.valid_to IS NULL OR pb.trade_date <= ci.valid_to)
            JOIN document_versions dv ON dv.id = pb.version_id
            WHERE pb.series = 'EQ'
            ORDER BY ci.company_id, pb.trade_date
            """
        )
    ).all()

    by_company: dict[uuid.UUID, list[tuple[dt.date, Bar, dt.datetime]]] = defaultdict(list)
    for company_id, trade_date, close, volume, turnover, known_at in rows:
        bar: Bar = (trade_date, close, volume, turnover)
        by_company[company_id].append((trade_date, bar, known_at))
    return by_company


def _month_end(year: int, month: int) -> dt.date:
    if month == 12:
        return dt.date(year, 12, 31)
    return dt.date(year, month + 1, 1) - dt.timedelta(days=1)


def _build_snapshots_for_company(
    company_id: uuid.UUID, series: list[tuple[dt.date, Bar, dt.datetime]]
) -> list[dict[str, Any]]:
    bars: list[Bar] = [s[1] for s in series]
    known_ats: list[dt.datetime] = [s[2] for s in series]

    months: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, (trade_date, _bar, _known_at) in enumerate(series):
        months[(trade_date.year, trade_date.month)].append(idx)

    snapshots: list[dict[str, Any]] = []
    for (year, month), idxs in sorted(months.items()):
        as_of = _month_end(year, month)
        eligible = [i for i in idxs if known_ats[i].date() <= as_of]
        if not eligible:
            continue
        snapshot_idx = max(eligible)

        values: dict[str, float | None] = {}
        flags: set[str] = set()

        for name, lookback in (
            ("ret_1m", 21),
            ("ret_3m", 63),
            ("ret_6m", 126),
            ("ret_12m", 252),
        ):
            result = simple_return(bars, snapshot_idx, lookback)
            values[name] = result.value
            if result.flag:
                flags.add(result.flag)

        for name, fn, kwargs in (
            ("volatility_3m", volatility, {"lookback": 63}),
            ("downside_volatility_12m", downside_volatility, {"lookback": 252}),
            ("max_drawdown_12m", max_drawdown, {"lookback": 252}),
            (
                "turnover_trend_1m_12m",
                turnover_trend,
                {"short_lookback": 21, "long_lookback": 252},
            ),
            ("amihud_illiquidity_1m", amihud_illiquidity, {"lookback": 21}),
            ("distance_from_52w_high", distance_from_52w_high, {"lookback": 252}),
        ):
            result = fn(bars, snapshot_idx, **kwargs)
            values[name] = result.value
            if result.flag:
                flags.add(result.flag)

        snapshots.append(
            {
                "company_id": company_id,
                "as_of": as_of,
                "values": values,
                "max_input_known_at": known_ats[snapshot_idx],
                "data_quality_flags": sorted(flags),
            }
        )
    return snapshots


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        _ensure_feature_definitions(session)
        by_company = _load_company_series(session)

        total_snapshots = 0
        companies_processed = 0
        batch: list[dict[str, Any]] = []

        for company_id, series in by_company.items():
            snapshots = _build_snapshots_for_company(company_id, series)
            batch.extend(snapshots)
            total_snapshots += len(snapshots)
            companies_processed += 1

            if len(batch) >= 5000:
                _flush_batch(session, batch)
                batch = []

        if batch:
            _flush_batch(session, batch)

        session.commit()

    print(f"companies_processed: {companies_processed}")
    print(f"feature_snapshots_written: {total_snapshots}")
    return 0


def _flush_batch(session: Any, batch: list[dict[str, Any]]) -> None:
    import json

    for row in batch:
        values_json = json.dumps(
            {k: (v if v is None else float(v)) for k, v in row["values"].items()}
        )
        session.execute(
            text(
                "INSERT INTO feature_snapshots "
                "(id, company_id, as_of, feature_set_version, values, "
                " max_input_known_at, data_quality_flags) "
                "VALUES (:id, :company_id, :as_of, :feature_set_version, "
                " CAST(:values AS JSONB), :max_input_known_at, CAST(:flags AS JSONB)) "
                "ON CONFLICT (company_id, as_of, feature_set_version) "
                "DO UPDATE SET values = EXCLUDED.values, "
                "max_input_known_at = EXCLUDED.max_input_known_at, "
                "data_quality_flags = EXCLUDED.data_quality_flags"
            ),
            {
                "id": uuid.uuid4(),
                "company_id": row["company_id"],
                "as_of": row["as_of"],
                "feature_set_version": FEATURE_SET_VERSION,
                "values": values_json,
                "max_input_known_at": row["max_input_known_at"],
                "flags": json.dumps(row["data_quality_flags"]),
            },
        )


if __name__ == "__main__":
    raise SystemExit(main())
