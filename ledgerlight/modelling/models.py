"""Real B0-B3 baselines and the main LightGBM model for the PRIMARY
outcome (Phase 3 brief §6). Every fit here happens strictly inside one
outer walk-forward fold (`ledgerlight.modelling.folds.Fold`): models
are trained only on `fold.train_rows` and scored only on
`fold.test_rows`, so no model ever sees a label from its own test
period. LightGBM hyperparameters and the imbalance-handling choice
are selected using only an inner validation split carved out of
`fold.train_rows` -- the outer test fold is never consulted before
that choice is frozen (the user's "no peeking" condition, 2026-10-31).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import cast

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score

from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.dates import add_months
from ledgerlight.modelling.folds import EMBARGO_MONTHS, HORIZON_MONTHS
from ledgerlight.modelling.rating_features import RATING_ORDINAL

RowKey = tuple[uuid.UUID, dt.date]

PRICE_LIQUIDITY_FEATURES = [
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "volatility_3m",
    "downside_volatility_12m",
    "max_drawdown_12m",
    "turnover_trend_1m_12m",
    "amihud_illiquidity_1m",
    "distance_from_52w_high",
]
RULE_VERIFIED_FEATURES = [
    "rating_actions_count_12m",
    "downgrades_count_12m",
    "current_rating_ordinal",
    "days_since_last_downgrade",
    "negative_outlook_flag",
    "prior_sebi_orders_count",
    "prior_ibbi_mentions_count",
]
ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES = PRICE_LIQUIDITY_FEATURES + RULE_VERIFIED_FEATURES

# B1's non-learned rule: distress-grade rating OR multiple downgrades in 12m.
B1_DISTRESS_RATING_ORDINAL = RATING_ORDINAL["C+"]
B1_RECENT_DOWNGRADES_THRESHOLD = 2

# §6's small, documented LightGBM search space -- a handful of hand-picked
# configs, not a full factorial grid, chosen on the inner validation fold only.
LIGHTGBM_CANDIDATE_CONFIGS: list[dict[str, float | int]] = [
    {
        "num_leaves": 7,
        "min_data_in_leaf": 10,
        "feature_fraction": 1.0,
        "lambda_l1": 0.0,
        "lambda_l2": 0.0,
    },
    {
        "num_leaves": 15,
        "min_data_in_leaf": 5,
        "feature_fraction": 0.8,
        "lambda_l1": 0.0,
        "lambda_l2": 1.0,
    },
    {
        "num_leaves": 7,
        "min_data_in_leaf": 20,
        "feature_fraction": 0.8,
        "lambda_l1": 1.0,
        "lambda_l2": 1.0,
    },
]
IMBALANCE_OPTIONS = (False, True)  # scale_pos_weight off / on
LIGHTGBM_SEED = 42
CALIBRATION_ISOTONIC_POSITIVE_FLOOR = 50


def _row_key(row: DatasetRow) -> RowKey:
    return (row.company_id, row.as_of)


def _real_labels(rows: list[DatasetRow]) -> list[int]:
    """Labels for rows already known to be non-censored (every
    `DatasetRow.label` is `None` iff `censored`, so this is a real
    cast, not an assumption)."""
    return [cast(int, row.label) for row in rows]


def feature_matrix(
    rows: list[DatasetRow], feature_names: list[str]
) -> tuple[pd.DataFrame, np.ndarray]:
    data = {name: [row.features.get(name) for row in rows] for name in feature_names}
    frame = pd.DataFrame(data, columns=feature_names, dtype=float)
    labels = np.array([row.label for row in rows], dtype=float)
    return frame, labels


def _impute_with_train_median(
    train_x: pd.DataFrame, other_x: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    medians = train_x.median(numeric_only=True).fillna(0.0)
    return train_x.fillna(medians), other_x.fillna(medians)


def split_inner_validation(
    train_rows: list[DatasetRow], validation_fraction: float = 0.2
) -> tuple[list[DatasetRow], list[DatasetRow]]:
    """Time-ordered inner split of one outer fold's train rows: the
    chronologically latest `validation_fraction` of distinct as_of
    months becomes the inner validation set. Inner-train keeps only
    rows whose own 12-month forward label window, plus the same
    12-month embargo used between outer folds, ends before the
    validation period starts -- the same no-peeking discipline applied
    one level in.
    """
    if not train_rows:
        return [], []
    as_of_dates = sorted({row.as_of for row in train_rows})
    if len(as_of_dates) < 2:
        return train_rows, []
    split_idx = max(1, int(len(as_of_dates) * (1 - validation_fraction)))
    split_idx = min(split_idx, len(as_of_dates) - 1)
    validation_start = as_of_dates[split_idx]
    inner_train_cutoff = add_months(validation_start, -(HORIZON_MONTHS + EMBARGO_MONTHS))
    inner_train = [row for row in train_rows if row.as_of < inner_train_cutoff]
    inner_validation = [row for row in train_rows if row.as_of >= validation_start]
    return inner_train, inner_validation


def fit_predict_b0_base_rate(
    train_rows: list[DatasetRow], test_rows: list[DatasetRow]
) -> dict[RowKey, float]:
    """B0: predict the real training-fold prevalence for every test
    row -- the honest "no information" baseline every other model
    must beat."""
    prevalence = float(np.mean(_real_labels(train_rows))) if train_rows else 0.0
    return {_row_key(row): prevalence for row in test_rows}


def fit_predict_b1_rating_rule(test_rows: list[DatasetRow]) -> dict[RowKey, float]:
    """B1: a simple, non-learned rule on the real rating features
    only -- predicts positive iff the current rating is distress-grade
    (C+ or worse) or there have been >= 2 real downgrades in the
    trailing 12 months. No training data is used; this rule is fixed
    before any fold is scored."""
    scores: dict[RowKey, float] = {}
    for row in test_rows:
        ordinal = row.features.get("current_rating_ordinal")
        downgrades = row.features.get("downgrades_count_12m")
        is_distress = ordinal is not None and ordinal >= B1_DISTRESS_RATING_ORDINAL
        is_recent_multi_downgrade = (
            downgrades is not None and downgrades >= B1_RECENT_DOWNGRADES_THRESHOLD
        )
        scores[_row_key(row)] = 1.0 if (is_distress or is_recent_multi_downgrade) else 0.0
    return scores


def fit_predict_logistic(
    train_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
    feature_names: list[str],
    seed: int = 0,
) -> dict[RowKey, float]:
    """B2/B3: logistic regression on the given real feature set.
    Falls back to the real train prevalence (never a fabricated 0.5)
    when the training fold has fewer than two label classes -- a
    logistic model cannot be honestly fit on a single class."""
    train_labels = _real_labels(train_rows)
    if not train_rows or len(set(train_labels)) < 2:
        prevalence = float(np.mean(train_labels)) if train_labels else 0.0
        return {_row_key(row): prevalence for row in test_rows}

    train_x, train_y = feature_matrix(train_rows, feature_names)
    test_x, _ = feature_matrix(test_rows, feature_names)
    train_x, test_x = _impute_with_train_median(train_x, test_x)

    model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed)
    model.fit(train_x, train_y)
    probs = model.predict_proba(test_x)[:, 1]
    return {_row_key(row): float(p) for row, p in zip(test_rows, probs, strict=True)}


def _real_pr_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    if len(set(y_true)) < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


@dataclass
class LightGBMSelection:
    config: dict[str, float | int]
    use_scale_pos_weight: bool
    inner_validation_pr_auc: float
    inner_validation_scores: dict[RowKey, float] = field(default_factory=dict)


def select_lightgbm_config(
    inner_train_rows: list[DatasetRow],
    inner_validation_rows: list[DatasetRow],
    feature_names: list[str],
    seed: int = LIGHTGBM_SEED,
) -> LightGBMSelection | None:
    """Chooses hyperparameters AND the imbalance-handling option using
    only the inner validation fold's real PR-AUC. Returns None when
    there is not enough real data (both classes present in both the
    inner-train and inner-validation splits) to choose anything
    honestly -- the caller must fall back to the base rate, not a
    fabricated choice."""
    if not inner_train_rows or not inner_validation_rows:
        return None
    train_x, train_y = feature_matrix(inner_train_rows, feature_names)
    val_x, val_y = feature_matrix(inner_validation_rows, feature_names)
    if len(set(train_y)) < 2 or len(set(val_y)) < 2:
        return None
    train_x, val_x = _impute_with_train_median(train_x, val_x)

    positive_count = int(train_y.sum())
    scale_pos_weight_value = (len(train_y) - positive_count) / positive_count

    best: LightGBMSelection | None = None
    for config in LIGHTGBM_CANDIDATE_CONFIGS:
        for use_spw in IMBALANCE_OPTIONS:
            params: dict[str, float | int | str | bool] = {
                **config,
                "objective": "binary",
                "seed": seed,
                "deterministic": True,
                "verbosity": -1,
            }
            if use_spw:
                params["scale_pos_weight"] = scale_pos_weight_value
            train_set = lgb.Dataset(train_x, label=train_y)
            val_set = lgb.Dataset(val_x, label=val_y, reference=train_set)
            booster = lgb.train(
                params,
                train_set,
                num_boost_round=200,
                valid_sets=[val_set],
                callbacks=[lgb.early_stopping(20, verbose=False), lgb.log_evaluation(0)],
            )
            preds = booster.predict(val_x, num_iteration=booster.best_iteration)
            score = _real_pr_auc(val_y, np.asarray(preds))
            if best is None or (not np.isnan(score) and score > best.inner_validation_pr_auc):
                val_scores = {
                    _row_key(row): float(p)
                    for row, p in zip(inner_validation_rows, preds, strict=True)
                }
                best = LightGBMSelection(
                    config=config,
                    use_scale_pos_weight=use_spw,
                    inner_validation_pr_auc=score,
                    inner_validation_scores=val_scores,
                )
    return best


@dataclass
class LightGBMFoldResult:
    test_scores: dict[RowKey, float]
    booster: lgb.Booster | None
    selection: LightGBMSelection | None
    test_feature_matrix: pd.DataFrame | None
    feature_names: list[str]


def fit_predict_lightgbm(
    train_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
    feature_names: list[str],
    seed: int = LIGHTGBM_SEED,
) -> LightGBMFoldResult:
    """Selects hyperparameters on an inner validation split of
    `train_rows` only, then fits the final booster on the full outer
    `train_rows` and scores `test_rows`. Falls back to the real train
    prevalence, with no booster, when there is not enough real data to
    select or fit anything honestly."""
    train_labels = _real_labels(train_rows)
    inner_train, inner_validation = split_inner_validation(train_rows)
    selection = select_lightgbm_config(inner_train, inner_validation, feature_names, seed=seed)

    if selection is None or len(set(train_labels)) < 2:
        prevalence = float(np.mean(train_labels)) if train_labels else 0.0
        return LightGBMFoldResult(
            test_scores={_row_key(row): prevalence for row in test_rows},
            booster=None,
            selection=None,
            test_feature_matrix=None,
            feature_names=feature_names,
        )

    train_x, train_y = feature_matrix(train_rows, feature_names)
    test_x, _ = feature_matrix(test_rows, feature_names)
    train_x, test_x = _impute_with_train_median(train_x, test_x)

    positive_count = int(train_y.sum())
    params: dict[str, float | int | str | bool] = {
        **selection.config,
        "objective": "binary",
        "seed": seed,
        "deterministic": True,
        "verbosity": -1,
    }
    if selection.use_scale_pos_weight:
        params["scale_pos_weight"] = (len(train_y) - positive_count) / positive_count

    train_set = lgb.Dataset(train_x, label=train_y)
    booster = lgb.train(params, train_set, num_boost_round=100)
    preds = booster.predict(test_x)
    test_scores = {
        _row_key(row): float(p) for row, p in zip(test_rows, np.asarray(preds), strict=True)
    }
    return LightGBMFoldResult(
        test_scores=test_scores,
        booster=booster,
        selection=selection,
        test_feature_matrix=test_x,
        feature_names=feature_names,
    )


def train_final_lightgbm(
    rows: list[DatasetRow], feature_names: list[str], seed: int = LIGHTGBM_SEED
) -> tuple[lgb.Booster | None, LightGBMSelection | None]:
    """Trains one final LightGBM model on ALL of `rows` (already real,
    non-censored labeled rows) for deployment/scoring -- not a
    walk-forward fold, so there is no test set to score here.
    Hyperparameters are still chosen only on an inner validation split
    of `rows`, never on data this model will later be used to score.
    Returns `(None, None)` if there is not enough real two-class data
    to select or fit anything honestly."""
    if len(set(_real_labels(rows))) < 2:
        return None, None

    inner_train, inner_validation = split_inner_validation(rows)
    selection = select_lightgbm_config(inner_train, inner_validation, feature_names, seed=seed)
    if selection is None:
        return None, None

    train_x, train_y = feature_matrix(rows, feature_names)
    train_x = train_x.fillna(train_x.median(numeric_only=True).fillna(0.0))

    positive_count = int(train_y.sum())
    params: dict[str, float | int | str | bool] = {
        **selection.config,
        "objective": "binary",
        "seed": seed,
        "deterministic": True,
        "verbosity": -1,
    }
    if selection.use_scale_pos_weight:
        params["scale_pos_weight"] = (len(train_y) - positive_count) / positive_count

    train_set = lgb.Dataset(train_x, label=train_y)
    booster = lgb.train(params, train_set, num_boost_round=100)
    return booster, selection


@dataclass
class CalibrationResult:
    method: str  # "isotonic" | "platt" | "uncalibrated"
    reason: str
    calibrated_scores: dict[RowKey, float]


def calibrate(
    selection: LightGBMSelection | None,
    inner_validation_rows: list[DatasetRow],
    raw_test_scores: dict[RowKey, float],
) -> CalibrationResult:
    """§6's calibration rule: isotonic ONLY if the calibration fold
    (the inner validation split already used to select hyperparameters)
    has at least 50 real positives; otherwise Platt scaling; otherwise
    uncalibrated, with the real reason stated -- never silently
    skipped."""
    if selection is None or not inner_validation_rows:
        return CalibrationResult(
            "uncalibrated",
            "no inner validation scores available (insufficient real training data for this fold)",
            dict(raw_test_scores),
        )

    val_rows = [
        row for row in inner_validation_rows if _row_key(row) in selection.inner_validation_scores
    ]
    val_y = np.array([row.label for row in val_rows], dtype=float)
    if len(set(val_y)) < 2:
        return CalibrationResult(
            "uncalibrated",
            "calibration fold has fewer than 2 label classes -- cannot fit any calibration map",
            dict(raw_test_scores),
        )

    val_scores = np.array([selection.inner_validation_scores[_row_key(row)] for row in val_rows])
    positive_count = int(val_y.sum())

    if positive_count >= CALIBRATION_ISOTONIC_POSITIVE_FLOOR:
        from sklearn.isotonic import IsotonicRegression

        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(val_scores, val_y)
        calibrated = {key: float(iso.predict([score])[0]) for key, score in raw_test_scores.items()}
        return CalibrationResult(
            "isotonic",
            f"calibration fold has {positive_count} real positives "
            f"(>= {CALIBRATION_ISOTONIC_POSITIVE_FLOOR})",
            calibrated,
        )

    platt = LogisticRegression()
    platt.fit(val_scores.reshape(-1, 1), val_y)
    calibrated = {
        key: float(platt.predict_proba([[score]])[0, 1]) for key, score in raw_test_scores.items()
    }
    return CalibrationResult(
        "platt",
        f"calibration fold has only {positive_count} real positives "
        f"(< {CALIBRATION_ISOTONIC_POSITIVE_FLOOR}) -- Platt scaling used instead of isotonic",
        calibrated,
    )


def compute_shap_contributions(
    booster: lgb.Booster,
    test_feature_matrix: pd.DataFrame,
    test_rows: list[DatasetRow],
    feature_names: list[str],
    top_k: int = 5,
) -> tuple[dict[str, float], dict[RowKey, list[tuple[str, float]]]]:
    """§6's SHAP TreeExplainer interpretability: real global importance
    (mean absolute SHAP value per feature) plus, per real test
    prediction, the top-k contributing features by absolute SHAP
    value -- both computed on the exact feature matrix that produced
    the stored scores, never recomputed on a different row order."""
    import shap

    explainer = shap.TreeExplainer(booster)
    raw_shap_values = explainer.shap_values(test_feature_matrix)
    shap_values = raw_shap_values[1] if isinstance(raw_shap_values, list) else raw_shap_values

    global_importance = {
        name: float(np.mean(np.abs(shap_values[:, idx]))) for idx, name in enumerate(feature_names)
    }
    per_row_top: dict[RowKey, list[tuple[str, float]]] = {}
    for row_idx, row in enumerate(test_rows):
        contributions = sorted(
            zip(feature_names, shap_values[row_idx], strict=True),
            key=lambda item: abs(item[1]),
            reverse=True,
        )
        per_row_top[_row_key(row)] = [(name, float(value)) for name, value in contributions[:top_k]]
    return global_importance, per_row_top
