"""Sec7 ablation arms: (a) STRUCTURED only, (b) (a) + RULE-VERIFIED,
(c) (b) + EVENT-CANDIDATE (unverified, SEED-track governance
features). Each arm fits and scores the real LightGBM pipeline
(hyperparameters chosen on an inner validation split, same as
`ledgerlight.modelling.backtest`) with a different feature set, so the
deltas are attributable only to which features were available.

Arm (c) is a deliberate, disclosed exception to
`ledgerlight.modelling.feature_policy.assert_primary_model_feature_policy`:
it exists specifically to measure what adding unverified EVENT-CANDIDATE
signal does to the real ablation comparison, never to replace or stand
in for the primary model.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from dataclasses import dataclass
from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.folds import build_walk_forward_folds
from ledgerlight.modelling.metrics import MetricsReport, compute_metrics
from ledgerlight.modelling.models import (
    ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES,
    PRICE_LIQUIDITY_FEATURES,
    RowKey,
    calibrate,
    fit_predict_lightgbm,
    split_inner_validation,
)
from ledgerlight.modelling.reporting import PositiveCounts, count_positives

EVENT_CANDIDATE_FEATURE_SET_VERSION = "seed-governance-1.0"


def load_event_candidate_feature_rows(
    session: Session, company_ids: list[uuid.UUID]
) -> tuple[dict[tuple[uuid.UUID, dt.date], dict[str, float | None]], list[str]]:
    """Real SEED-track governance (EVENT-CANDIDATE tier) feature
    values, merged per (company_id, as_of). Feature names are
    discovered from the real stored snapshot values, never
    hardcoded."""
    rows = session.execute(
        text(
            "SELECT company_id, as_of, values FROM feature_snapshots "
            "WHERE feature_set_version = :version AND company_id = ANY(:ids)"
        ),
        {"version": EVENT_CANDIDATE_FEATURE_SET_VERSION, "ids": company_ids},
    ).all()
    merged: dict[tuple[uuid.UUID, dt.date], dict[str, float | None]] = {}
    feature_names: set[str] = set()
    for row in rows:
        company_id = cast(uuid.UUID, row[0])
        as_of = cast(dt.date, row[1])
        values = cast("dict[str, float | None]", row[2])
        merged.setdefault((company_id, as_of), {}).update(values)
        feature_names.update(values.keys())
    return merged, sorted(feature_names)


def merge_event_candidate_features(
    rows: list[DatasetRow], session: Session
) -> tuple[list[DatasetRow], list[str]]:
    company_ids = list({row.company_id for row in rows})
    event_candidate_by_key, feature_names = load_event_candidate_feature_rows(session, company_ids)
    merged_rows = [
        dataclasses.replace(
            row,
            features={
                **row.features,
                **event_candidate_by_key.get((row.company_id, row.as_of), {}),
            },
        )
        for row in rows
    ]
    return merged_rows, feature_names


def _real_train_prevalence(rows: list[DatasetRow]) -> float:
    if not rows:
        return 0.0
    labels = [row.label for row in rows if row.label is not None]
    return float(sum(labels) / len(labels)) if labels else 0.0


@dataclass
class AblationArmResult:
    feature_names: list[str]
    pooled_metrics: MetricsReport
    pooled_positive_counts: PositiveCounts


def run_lightgbm_ablation_arm(
    rows: list[DatasetRow], feature_names: list[str], seed: int = 42
) -> AblationArmResult:
    """Fits and scores the real LightGBM pipeline fold-by-fold with
    exactly `feature_names` available, pools the test scores across
    folds, and reports real pooled metrics + honest positive counts."""
    folds = build_walk_forward_folds(rows)
    pooled_scores: dict[RowKey, float] = {}
    pooled_test_rows: list[DatasetRow] = []

    for fold in folds:
        lgbm_result = fit_predict_lightgbm(
            fold.train_rows, fold.test_rows, feature_names, seed=seed
        )
        _, inner_validation = split_inner_validation(fold.train_rows)
        calibration = calibrate(lgbm_result.selection, inner_validation, lgbm_result.test_scores)
        pooled_scores.update(calibration.calibrated_scores)
        pooled_test_rows.extend(fold.test_rows)

    pooled_train_prevalence = _real_train_prevalence([row for row in rows if not row.censored])
    metrics = compute_metrics(pooled_test_rows, pooled_scores, pooled_train_prevalence)
    positive_counts = count_positives(pooled_test_rows)
    return AblationArmResult(
        feature_names=feature_names, pooled_metrics=metrics, pooled_positive_counts=positive_counts
    )


@dataclass
class AblationResult:
    arm_a_structured: AblationArmResult
    arm_b_plus_rule_verified: AblationArmResult
    arm_c_plus_event_candidate: AblationArmResult


def run_ablation(rows: list[DatasetRow], session: Session, seed: int = 42) -> AblationResult:
    arm_a = run_lightgbm_ablation_arm(rows, PRICE_LIQUIDITY_FEATURES, seed=seed)
    arm_b = run_lightgbm_ablation_arm(rows, ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES, seed=seed)

    arm_c_rows, event_candidate_feature_names = merge_event_candidate_features(rows, session)
    arm_c_feature_names = ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES + event_candidate_feature_names
    arm_c = run_lightgbm_ablation_arm(arm_c_rows, arm_c_feature_names, seed=seed)

    return AblationResult(
        arm_a_structured=arm_a, arm_b_plus_rule_verified=arm_b, arm_c_plus_event_candidate=arm_c
    )


def print_ablation_result(result: AblationResult) -> None:
    for label, arm in (
        ("(a) STRUCTURED only", result.arm_a_structured),
        ("(b) + RULE-VERIFIED", result.arm_b_plus_rule_verified),
        ("(c) + EVENT-CANDIDATE (unverified)", result.arm_c_plus_event_candidate),
    ):
        counts = arm.pooled_positive_counts
        print(
            f"{label}: {len(arm.feature_names)} features, n={arm.pooled_metrics.n} "
            f"distinct events={counts.distinct_positive_events} "
            f"PR-AUC={arm.pooled_metrics.pr_auc} BSS={arm.pooled_metrics.brier_skill_score}"
        )
