"""Tests for ledgerlight.modelling.models -- the real B0-B3 baselines
and the LightGBM model + calibration rule from Phase 3 brief §6.
Uses small synthetic DatasetRow sets so the degenerate-data guards
(single class, empty train, too few calibration positives) are each
exercised directly, independent of how much real data exists today."""

from __future__ import annotations

import datetime as dt
import uuid

import numpy as np
import pytest

from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.models import (
    B1_DISTRESS_RATING_ORDINAL,
    CALIBRATION_ISOTONIC_POSITIVE_FLOOR,
    LightGBMSelection,
    calibrate,
    compute_shap_contributions,
    fit_predict_b0_base_rate,
    fit_predict_b1_rating_rule,
    fit_predict_lightgbm,
    fit_predict_logistic,
    select_lightgbm_config,
    split_inner_validation,
    train_final_lightgbm,
)

COMPANY_A = uuid.uuid4()
COMPANY_B = uuid.uuid4()
COMPANY_C = uuid.uuid4()


def _row(
    company_id: uuid.UUID,
    as_of: dt.date,
    label: int,
    features: dict[str, float | None] | None = None,
) -> DatasetRow:
    return DatasetRow(
        company_id=company_id,
        company_name=str(company_id),
        as_of=as_of,
        features=features or {},
        label=label,
        censored=False,
        censor_reason=None,
    )


def test_b0_predicts_the_real_train_prevalence_for_every_test_row() -> None:
    train_rows = [
        _row(COMPANY_A, dt.date(2019, 1, 31), 1),
        _row(COMPANY_A, dt.date(2019, 2, 28), 0),
        _row(COMPANY_A, dt.date(2019, 3, 31), 0),
        _row(COMPANY_A, dt.date(2019, 4, 30), 0),
    ]
    test_rows = [_row(COMPANY_B, dt.date(2020, 1, 31), 0)]
    scores = fit_predict_b0_base_rate(train_rows, test_rows)
    assert scores[(COMPANY_B, dt.date(2020, 1, 31))] == pytest.approx(0.25)


def test_b0_with_empty_train_returns_zero_not_a_crash() -> None:
    scores = fit_predict_b0_base_rate([], [_row(COMPANY_A, dt.date(2020, 1, 31), 0)])
    assert scores[(COMPANY_A, dt.date(2020, 1, 31))] == 0.0


def test_b1_predicts_positive_for_distress_grade_rating() -> None:
    test_rows = [
        _row(
            COMPANY_A,
            dt.date(2020, 1, 31),
            0,
            {
                "current_rating_ordinal": float(B1_DISTRESS_RATING_ORDINAL),
                "downgrades_count_12m": 0,
            },
        )
    ]
    scores = fit_predict_b1_rating_rule(test_rows)
    assert scores[(COMPANY_A, dt.date(2020, 1, 31))] == 1.0


def test_b1_predicts_positive_for_multiple_recent_downgrades_even_at_good_rating() -> None:
    test_rows = [
        _row(
            COMPANY_A,
            dt.date(2020, 1, 31),
            0,
            {"current_rating_ordinal": 0.0, "downgrades_count_12m": 2},
        )
    ]
    scores = fit_predict_b1_rating_rule(test_rows)
    assert scores[(COMPANY_A, dt.date(2020, 1, 31))] == 1.0


def test_b1_predicts_negative_for_a_stable_investment_grade_company() -> None:
    test_rows = [
        _row(
            COMPANY_A,
            dt.date(2020, 1, 31),
            0,
            {"current_rating_ordinal": 2.0, "downgrades_count_12m": 0},
        )
    ]
    scores = fit_predict_b1_rating_rule(test_rows)
    assert scores[(COMPANY_A, dt.date(2020, 1, 31))] == 0.0


def test_b1_predicts_negative_when_never_rated() -> None:
    test_rows = [_row(COMPANY_A, dt.date(2020, 1, 31), 0, {})]
    scores = fit_predict_b1_rating_rule(test_rows)
    assert scores[(COMPANY_A, dt.date(2020, 1, 31))] == 0.0


def test_logistic_falls_back_to_prevalence_with_a_single_train_class() -> None:
    train_rows = [
        _row(COMPANY_A, dt.date(2019, 1, 31), 0, {"ret_1m": 0.1}),
        _row(COMPANY_A, dt.date(2019, 2, 28), 0, {"ret_1m": -0.1}),
    ]
    test_rows = [_row(COMPANY_B, dt.date(2020, 1, 31), 0, {"ret_1m": 0.0})]
    scores = fit_predict_logistic(train_rows, test_rows, ["ret_1m"])
    assert scores[(COMPANY_B, dt.date(2020, 1, 31))] == 0.0


def test_logistic_fits_and_scores_with_two_real_classes() -> None:
    train_rows = [
        _row(COMPANY_A, dt.date(2019, 1, 31), 1, {"ret_1m": -0.5}),
        _row(COMPANY_A, dt.date(2019, 2, 28), 0, {"ret_1m": 0.5}),
        _row(COMPANY_B, dt.date(2019, 1, 31), 1, {"ret_1m": -0.4}),
        _row(COMPANY_B, dt.date(2019, 2, 28), 0, {"ret_1m": 0.4}),
    ]
    test_rows = [_row(COMPANY_C, dt.date(2020, 1, 31), 0, {"ret_1m": 0.5})]
    scores = fit_predict_logistic(train_rows, test_rows, ["ret_1m"])
    assert 0.0 <= scores[(COMPANY_C, dt.date(2020, 1, 31))] <= 1.0


def test_select_lightgbm_config_returns_none_with_empty_inner_splits() -> None:
    assert select_lightgbm_config([], [], ["ret_1m"]) is None


def test_select_lightgbm_config_returns_none_with_a_single_class() -> None:
    inner_train = [_row(COMPANY_A, dt.date(2018, 1, 31), 0, {"ret_1m": 0.1})]
    inner_val = [_row(COMPANY_A, dt.date(2019, 6, 30), 0, {"ret_1m": 0.2})]
    assert select_lightgbm_config(inner_train, inner_val, ["ret_1m"]) is None


def test_select_lightgbm_config_picks_a_real_candidate_with_enough_two_class_data() -> None:
    rng = np.random.default_rng(0)
    inner_train = [
        _row(
            COMPANY_A,
            dt.date(2018, 1, 1) + dt.timedelta(days=30 * i),
            i % 2,
            {"ret_1m": float(rng.normal())},
        )
        for i in range(20)
    ]
    inner_val = [
        _row(
            COMPANY_A,
            dt.date(2020, 1, 1) + dt.timedelta(days=30 * i),
            i % 2,
            {"ret_1m": float(rng.normal())},
        )
        for i in range(10)
    ]
    selection = select_lightgbm_config(inner_train, inner_val, ["ret_1m"])
    assert selection is not None
    assert selection.config in [
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


def test_fit_predict_lightgbm_falls_back_when_train_has_a_single_class() -> None:
    train_rows = [_row(COMPANY_A, dt.date(2019, 1, 31), 0, {"ret_1m": 0.1})]
    test_rows = [_row(COMPANY_B, dt.date(2020, 1, 31), 0, {"ret_1m": 0.0})]
    result = fit_predict_lightgbm(train_rows, test_rows, ["ret_1m"])
    assert result.booster is None
    assert result.selection is None
    assert result.test_scores[(COMPANY_B, dt.date(2020, 1, 31))] == 0.0


def test_split_inner_validation_respects_the_embargo() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2018, 1, 31), 0),
        _row(COMPANY_A, dt.date(2019, 1, 31), 0),
        _row(COMPANY_A, dt.date(2020, 6, 30), 1),
        _row(COMPANY_A, dt.date(2020, 12, 31), 1),
    ]
    inner_train, inner_val = split_inner_validation(rows, validation_fraction=0.5)
    assert all(r.as_of not in {row.as_of for row in inner_val} for r in inner_train)
    for train_row in inner_train:
        for val_row in inner_val:
            assert train_row.as_of < val_row.as_of


def test_calibration_uses_isotonic_only_at_or_above_the_positive_floor() -> None:
    val_rows = [
        _row(
            COMPANY_A,
            dt.date(2019, 1, 1) + dt.timedelta(days=i),
            1 if i < CALIBRATION_ISOTONIC_POSITIVE_FLOOR else 0,
        )
        for i in range(100)
    ]
    scores = {(r.company_id, r.as_of): float(i) / 100 for i, r in enumerate(val_rows)}
    selection = LightGBMSelection(
        config={
            "num_leaves": 7,
            "min_data_in_leaf": 10,
            "feature_fraction": 1.0,
            "lambda_l1": 0.0,
            "lambda_l2": 0.0,
        },
        use_scale_pos_weight=False,
        inner_validation_pr_auc=0.5,
        inner_validation_scores=scores,
    )
    test_scores = {(COMPANY_B, dt.date(2020, 1, 31)): 0.5}
    result = calibrate(selection, val_rows, test_scores)
    assert result.method == "isotonic"


def test_calibration_uses_platt_below_the_positive_floor() -> None:
    val_rows = [
        _row(COMPANY_A, dt.date(2019, 1, 1) + dt.timedelta(days=i), 1 if i < 5 else 0)
        for i in range(20)
    ]
    scores = {(r.company_id, r.as_of): float(i) / 20 for i, r in enumerate(val_rows)}
    selection = LightGBMSelection(
        config={
            "num_leaves": 7,
            "min_data_in_leaf": 10,
            "feature_fraction": 1.0,
            "lambda_l1": 0.0,
            "lambda_l2": 0.0,
        },
        use_scale_pos_weight=False,
        inner_validation_pr_auc=0.5,
        inner_validation_scores=scores,
    )
    test_scores = {(COMPANY_B, dt.date(2020, 1, 31)): 0.5}
    result = calibrate(selection, val_rows, test_scores)
    assert result.method == "platt"
    assert "< 50" in result.reason


def test_calibration_is_uncalibrated_when_no_selection_exists() -> None:
    result = calibrate(None, [], {(COMPANY_A, dt.date(2020, 1, 31)): 0.5})
    assert result.method == "uncalibrated"
    assert result.calibrated_scores == {(COMPANY_A, dt.date(2020, 1, 31)): 0.5}


def test_calibration_is_uncalibrated_with_a_single_validation_class() -> None:
    val_rows = [_row(COMPANY_A, dt.date(2019, 1, 31), 0)]
    selection = LightGBMSelection(
        config={
            "num_leaves": 7,
            "min_data_in_leaf": 10,
            "feature_fraction": 1.0,
            "lambda_l1": 0.0,
            "lambda_l2": 0.0,
        },
        use_scale_pos_weight=False,
        inner_validation_pr_auc=0.5,
        inner_validation_scores={(COMPANY_A, dt.date(2019, 1, 31)): 0.3},
    )
    result = calibrate(selection, val_rows, {(COMPANY_B, dt.date(2020, 1, 31)): 0.5})
    assert result.method == "uncalibrated"
    assert "fewer than 2 label classes" in result.reason


def test_shap_contributions_shape_matches_real_test_rows_and_top_k() -> None:
    rng = np.random.default_rng(1)
    train_rows = [
        _row(
            COMPANY_A,
            dt.date(2010, 1, 1) + dt.timedelta(days=60 * i),
            i % 2,
            {"ret_1m": float(rng.normal()), "ret_3m": float(rng.normal())},
        )
        for i in range(60)
    ]
    test_rows = [
        _row(COMPANY_B, dt.date(2021, 1, 31), 0, {"ret_1m": 0.1, "ret_3m": 0.2}),
        _row(COMPANY_B, dt.date(2021, 2, 28), 1, {"ret_1m": -0.1, "ret_3m": -0.2}),
    ]
    result = fit_predict_lightgbm(train_rows, test_rows, ["ret_1m", "ret_3m"])
    if result.booster is None or result.test_feature_matrix is None:
        pytest.skip(
            "not enough real inner-validation data to select a LightGBM config "
            "in this synthetic case"
        )
    global_importance, per_row = compute_shap_contributions(
        result.booster, result.test_feature_matrix, test_rows, result.feature_names, top_k=1
    )
    assert set(global_importance) == {"ret_1m", "ret_3m"}
    for row in test_rows:
        key = (row.company_id, row.as_of)
        assert len(per_row[key]) == 1


def test_train_final_lightgbm_returns_none_with_a_single_class() -> None:
    rows = [_row(COMPANY_A, dt.date(2019, 1, 31), 0, {"ret_1m": 0.1})]
    booster, selection = train_final_lightgbm(rows, ["ret_1m"])
    assert booster is None
    assert selection is None


def test_train_final_lightgbm_fits_a_real_booster_with_enough_two_class_data() -> None:
    rng = np.random.default_rng(2)
    rows = [
        _row(
            COMPANY_A,
            dt.date(2010, 1, 1) + dt.timedelta(days=60 * i),
            i % 2,
            {"ret_1m": float(rng.normal())},
        )
        for i in range(60)
    ]
    booster, selection = train_final_lightgbm(rows, ["ret_1m"])
    assert booster is not None
    assert selection is not None
