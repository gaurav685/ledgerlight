"""Real Sec6/7 backtest orchestrator. For each real walk-forward fold
(`ledgerlight.modelling.folds.build_walk_forward_folds`), every model
is fit on that fold's `train_rows` only and scored on its `test_rows`
only -- no model ever sees a label from its own test period, and
LightGBM's hyperparameters are chosen on an inner validation split of
`train_rows` before the outer test fold is scored (the user's
"no peeking" condition, 2026-10-31). Reports both per-fold and pooled
metrics, honest distinct-event/company positive counts, and
company-clustered bootstrap intervals.

`scripts/backtest.py` is a thin CLI wrapper around `run_backtest`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ledgerlight.modelling.coverage import VerifiedCoverage
from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.folds import Fold, build_walk_forward_folds
from ledgerlight.modelling.metrics import MetricsReport, compute_metrics
from ledgerlight.modelling.models import (
    ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES,
    PRICE_LIQUIDITY_FEATURES,
    CalibrationResult,
    LightGBMFoldResult,
    RowKey,
    calibrate,
    fit_predict_b0_base_rate,
    fit_predict_b1_rating_rule,
    fit_predict_lightgbm,
    fit_predict_logistic,
    split_inner_validation,
)
from ledgerlight.modelling.reporting import PositiveCounts, count_positives

MODEL_NAMES = [
    "B0_base_rate",
    "B1_rating_rule",
    "B2_price_liquidity",
    "B3_structured_rule_verified",
    "LightGBM",
]


def _real_train_prevalence(rows: list[DatasetRow]) -> float:
    if not rows:
        return 0.0
    return float(np.mean([row.label for row in rows]))


@dataclass
class FoldModelOutput:
    model_name: str
    scores: dict[RowKey, float]
    metrics: MetricsReport
    positive_counts: PositiveCounts
    calibration: CalibrationResult | None = None


@dataclass
class BacktestResult:
    coverage: VerifiedCoverage
    folds: list[Fold]
    per_fold_outputs: dict[int, dict[str, FoldModelOutput]] = field(default_factory=dict)
    pooled_outputs: dict[str, FoldModelOutput] = field(default_factory=dict)
    pooled_positive_counts: PositiveCounts | None = None
    lightgbm_fold_results: dict[int, LightGBMFoldResult] = field(default_factory=dict)


def _fold_output(
    model_name: str,
    scores: dict[RowKey, float],
    test_rows: list[DatasetRow],
    train_prevalence: float,
    calibration: CalibrationResult | None = None,
) -> FoldModelOutput:
    metrics = compute_metrics(test_rows, scores, train_prevalence)
    positive_counts = count_positives(test_rows)
    return FoldModelOutput(
        model_name=model_name,
        scores=scores,
        metrics=metrics,
        positive_counts=positive_counts,
        calibration=calibration,
    )


def run_backtest(
    rows: list[DatasetRow], coverage: VerifiedCoverage, seed: int = 42
) -> BacktestResult:
    folds = build_walk_forward_folds(rows)
    per_fold_outputs: dict[int, dict[str, FoldModelOutput]] = {}
    lightgbm_fold_results: dict[int, LightGBMFoldResult] = {}
    pooled_scores: dict[str, dict[RowKey, float]] = {name: {} for name in MODEL_NAMES}
    pooled_test_rows: list[DatasetRow] = []

    for fold in folds:
        train_prevalence = _real_train_prevalence(fold.train_rows)
        outputs: dict[str, FoldModelOutput] = {}

        b0_scores = fit_predict_b0_base_rate(fold.train_rows, fold.test_rows)
        outputs["B0_base_rate"] = _fold_output(
            "B0_base_rate", b0_scores, fold.test_rows, train_prevalence
        )

        b1_scores = fit_predict_b1_rating_rule(fold.test_rows)
        outputs["B1_rating_rule"] = _fold_output(
            "B1_rating_rule", b1_scores, fold.test_rows, train_prevalence
        )

        b2_scores = fit_predict_logistic(
            fold.train_rows, fold.test_rows, PRICE_LIQUIDITY_FEATURES, seed=seed
        )
        outputs["B2_price_liquidity"] = _fold_output(
            "B2_price_liquidity", b2_scores, fold.test_rows, train_prevalence
        )

        b3_scores = fit_predict_logistic(
            fold.train_rows, fold.test_rows, ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES, seed=seed
        )
        outputs["B3_structured_rule_verified"] = _fold_output(
            "B3_structured_rule_verified", b3_scores, fold.test_rows, train_prevalence
        )

        lgbm_result = fit_predict_lightgbm(
            fold.train_rows, fold.test_rows, ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES, seed=seed
        )
        lightgbm_fold_results[fold.test_year] = lgbm_result
        _, inner_validation = split_inner_validation(fold.train_rows)
        calibration = calibrate(lgbm_result.selection, inner_validation, lgbm_result.test_scores)
        outputs["LightGBM"] = _fold_output(
            "LightGBM",
            calibration.calibrated_scores,
            fold.test_rows,
            train_prevalence,
            calibration=calibration,
        )

        for name in MODEL_NAMES:
            pooled_scores[name].update(outputs[name].scores)
        pooled_test_rows.extend(fold.test_rows)
        per_fold_outputs[fold.test_year] = outputs

    pooled_train_prevalence = _real_train_prevalence([row for row in rows if not row.censored])
    pooled_outputs = {
        name: _fold_output(name, pooled_scores[name], pooled_test_rows, pooled_train_prevalence)
        for name in MODEL_NAMES
    }
    pooled_positive_counts = count_positives(pooled_test_rows)

    return BacktestResult(
        coverage=coverage,
        folds=folds,
        per_fold_outputs=per_fold_outputs,
        pooled_outputs=pooled_outputs,
        pooled_positive_counts=pooled_positive_counts,
        lightgbm_fold_results=lightgbm_fold_results,
    )
