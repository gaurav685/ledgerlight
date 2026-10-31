"""Sec7 survivorship reporting: metrics both with and without
later-delisted companies, and the real companies/observations lost by
excluding them. "Later-delisted" here means a real confirmed
disappearance -- the same >= 90-real-day gap between a company's last
real trade and the overall `price_bars` coverage end that
`ledgerlight.modelling.censoring.check_censoring`'s `unknown_trading_stop`
rule already treats as a genuine BHAVCOPY_DISAPPEARANCE, not an
assumption made fresh here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.modelling.backtest import BacktestResult, run_backtest
from ledgerlight.modelling.censoring import BHAVCOPY_DISAPPEARANCE_MIN_GAP_DAYS
from ledgerlight.modelling.coverage import VerifiedCoverage
from ledgerlight.modelling.dataset import DatasetRow, load_last_real_trade_dates
from ledgerlight.modelling.reporting import count_positives


def identify_delisted_companies(
    session: Session, coverage: VerifiedCoverage
) -> dict[uuid.UUID, str]:
    """Real companies in `coverage` with a confirmed >= 90-real-day
    gap between their own last real EQ trade and the real overall
    `price_bars` coverage end."""
    data_coverage_end = session.execute(
        text("SELECT max(trade_date) FROM price_bars WHERE series = 'EQ'")
    ).scalar()
    assert data_coverage_end is not None

    last_trade_by_company = load_last_real_trade_dates(session, coverage.company_ids)
    delisted: dict[uuid.UUID, str] = {}
    for company_id, name in zip(coverage.company_ids, coverage.company_names, strict=True):
        last_trade = last_trade_by_company.get(company_id)
        if last_trade is None:
            continue
        gap_days = (data_coverage_end - last_trade).days
        if gap_days >= BHAVCOPY_DISAPPEARANCE_MIN_GAP_DAYS:
            delisted[company_id] = name
    return delisted


@dataclass
class SurvivorshipReport:
    delisted_company_names: list[str] = field(default_factory=list)
    labeled_rows_lost: int = 0
    distinct_events_lost: int = 0
    distinct_companies_lost: int = 0
    with_delisted: BacktestResult | None = None
    without_delisted: BacktestResult | None = None


def run_survivorship_report(
    session: Session,
    coverage: VerifiedCoverage,
    rows: list[DatasetRow],
    seed: int = 42,
) -> SurvivorshipReport:
    """Real, run-every-time: reruns the full backtest twice (with and
    without the real later-delisted companies) rather than estimating
    the delta from the already-computed full-universe backtest."""
    delisted_ids = identify_delisted_companies(session, coverage)
    without_rows = [row for row in rows if row.company_id not in delisted_ids]

    lost_rows = [row for row in rows if row.company_id in delisted_ids]
    lost_labeled_rows = [row for row in lost_rows if not row.censored]
    lost_counts = count_positives(lost_rows)

    with_backtest = run_backtest(rows, coverage, seed=seed)
    without_backtest = run_backtest(without_rows, coverage, seed=seed)

    return SurvivorshipReport(
        delisted_company_names=sorted(delisted_ids.values()),
        labeled_rows_lost=len(lost_labeled_rows),
        distinct_events_lost=lost_counts.distinct_positive_events,
        distinct_companies_lost=len(delisted_ids),
        with_delisted=with_backtest,
        without_delisted=without_backtest,
    )


def print_survivorship_report(report: SurvivorshipReport) -> None:
    print(
        "real delisted companies excluded in the 'without' variant: "
        f"{report.delisted_company_names}"
    )
    print(
        f"labeled rows lost: {report.labeled_rows_lost}; distinct events lost: "
        f"{report.distinct_events_lost}; distinct companies lost: "
        f"{report.distinct_companies_lost}"
    )
    for label, backtest in (
        ("WITH delisted", report.with_delisted),
        ("WITHOUT delisted", report.without_delisted),
    ):
        if backtest is None:
            continue
        counts = backtest.pooled_positive_counts
        lgbm = backtest.pooled_outputs.get("LightGBM")
        pr_auc = lgbm.metrics.pr_auc if lgbm else None
        print(
            f"{label}: n={counts.company_month_rows if counts else 0} "
            f"distinct events={counts.distinct_positive_events if counts else 0} "
            f"LightGBM pooled PR-AUC={pr_auc}"
        )
