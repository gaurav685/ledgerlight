"""The user's explicit Sec6/7 sensitivity condition (2026-10-31):
evaluate the primary model against (a) rating-default-only outcomes
and (b) IBBI-only outcomes, so the real effect of the partial IBBI
crawl coverage is visible rather than hidden inside the combined
PRIMARY outcome. Each variant reuses the exact same verified-coverage
universe and censoring rules -- only the outcome-type filter passed
to `build_primary_outcome_dataset` changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ledgerlight.modelling.backtest import BacktestResult, run_backtest
from ledgerlight.modelling.coverage import VerifiedCoverage, compute_verified_coverage
from ledgerlight.modelling.dataset import build_primary_outcome_dataset

RATING_DEFAULT_ONLY_OUTCOME_TYPES = ["PRIMARY_RATING_DOWNGRADE_D"]
IBBI_ONLY_OUTCOME_TYPES = ["PRIMARY_IBBI_ADMISSION"]


@dataclass
class SensitivityResult:
    primary: BacktestResult
    rating_default_only: BacktestResult
    ibbi_only: BacktestResult


def run_sensitivity_analysis(
    session: Session, coverage: VerifiedCoverage | None = None, seed: int = 42
) -> SensitivityResult:
    """Real, run-every-time -- never cached or assumed. Each of the
    three backtests uses the exact same `coverage` (computed once, if
    not already supplied) so the three variants differ only in which
    real outcome events count as positive."""
    if coverage is None:
        coverage = compute_verified_coverage(session)

    primary_rows = build_primary_outcome_dataset(session, coverage)
    rating_rows = build_primary_outcome_dataset(
        session, coverage, outcome_types=RATING_DEFAULT_ONLY_OUTCOME_TYPES
    )
    ibbi_rows = build_primary_outcome_dataset(
        session, coverage, outcome_types=IBBI_ONLY_OUTCOME_TYPES
    )

    return SensitivityResult(
        primary=run_backtest(primary_rows, coverage, seed=seed),
        rating_default_only=run_backtest(rating_rows, coverage, seed=seed),
        ibbi_only=run_backtest(ibbi_rows, coverage, seed=seed),
    )


def print_sensitivity_summary(result: SensitivityResult) -> None:
    for label, backtest in (
        ("PRIMARY (IBBI admission OR rating default)", result.primary),
        ("rating-default-only", result.rating_default_only),
        ("IBBI-only", result.ibbi_only),
    ):
        counts = backtest.pooled_positive_counts
        lgbm_metrics = backtest.pooled_outputs.get("LightGBM")
        pr_auc = lgbm_metrics.metrics.pr_auc if lgbm_metrics else None
        print(
            f"{label}: distinct events={counts.distinct_positive_events if counts else 0} "
            f"distinct companies={counts.distinct_positive_companies if counts else 0} "
            f"company-month rows={counts.company_month_rows if counts else 0} "
            f"LightGBM pooled PR-AUC={pr_auc} "
            f"{'INCONCLUSIVE' if (counts is None or counts.is_inconclusive) else ''}"
        )
