"""Tests for ledgerlight.modelling.scoring. compute_percentiles is a
pure function, tested directly; write_scores/get_score/record_experiment
are real integration tests against the real DB (the real point-in-time
contract -- get_score must never return a future score)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.knowledge.models import Company
from ledgerlight.modelling.scoring import (
    ScoreRow,
    compute_percentiles,
    get_score,
    record_experiment,
    write_scores,
)

pytestmark = pytest.mark.integration


def test_compute_percentiles_ranks_the_real_cohort() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    percentiles = compute_percentiles({a: 0.1, b: 0.5, c: 0.9})
    assert percentiles[a] == 0.0
    assert percentiles[b] == 50.0
    assert percentiles[c] == 100.0


def test_compute_percentiles_single_company_gets_the_midpoint() -> None:
    a = uuid.uuid4()
    assert compute_percentiles({a: 0.9}) == {a: 50.0}


def test_compute_percentiles_empty_cohort_is_empty() -> None:
    assert compute_percentiles({}) == {}


def _make_company(db_session: Session, name: str) -> uuid.UUID:
    company = Company(id=uuid.uuid4(), display_name=name)
    db_session.add(company)
    db_session.flush()
    return company.id


def test_get_score_never_returns_a_score_from_after_as_of(db_session: Session) -> None:
    company_id = _make_company(db_session, "Scoring Test Co A")
    write_scores(
        db_session,
        [
            ScoreRow(
                company_id=company_id,
                as_of=dt.date(2020, 1, 31),
                model_name="lightgbm",
                model_version="1.0",
                raw_probability=0.2,
                calibrated_probability=0.25,
                percentile=50.0,
                top_shap_contributors=[("ret_1m", 0.1)],
                feature_set_version="primary-structured-rv-1.0",
                outcome_spec_hash="a" * 64,
            ),
            ScoreRow(
                company_id=company_id,
                as_of=dt.date(2020, 6, 30),
                model_name="lightgbm",
                model_version="1.0",
                raw_probability=0.8,
                calibrated_probability=0.75,
                percentile=50.0,
                top_shap_contributors=None,
                feature_set_version="primary-structured-rv-1.0",
                outcome_spec_hash="a" * 64,
            ),
        ],
    )
    db_session.flush()

    before_both = get_score(db_session, company_id, dt.date(2019, 12, 31), "lightgbm", "1.0")
    assert before_both is None

    between = get_score(db_session, company_id, dt.date(2020, 3, 31), "lightgbm", "1.0")
    assert between is not None
    assert between.as_of == dt.date(2020, 1, 31)
    assert between.calibrated_probability == 0.25

    after_both = get_score(db_session, company_id, dt.date(2021, 1, 1), "lightgbm", "1.0")
    assert after_both is not None
    assert after_both.as_of == dt.date(2020, 6, 30)
    assert after_both.calibrated_probability == 0.75


def test_get_score_is_scoped_to_the_real_model_name_and_version(db_session: Session) -> None:
    company_id = _make_company(db_session, "Scoring Test Co B")
    write_scores(
        db_session,
        [
            ScoreRow(
                company_id=company_id,
                as_of=dt.date(2020, 1, 31),
                model_name="b0_base_rate",
                model_version="1.0",
                raw_probability=0.3,
                calibrated_probability=0.3,
                percentile=None,
                top_shap_contributors=None,
                feature_set_version="primary-structured-rv-1.0",
                outcome_spec_hash="a" * 64,
            )
        ],
    )
    db_session.flush()
    assert get_score(db_session, company_id, dt.date(2020, 6, 30), "lightgbm", "1.0") is None
    found = get_score(db_session, company_id, dt.date(2020, 6, 30), "b0_base_rate", "1.0")
    assert found is not None


def test_record_experiment_persists_real_config_and_metrics(db_session: Session) -> None:
    experiment_id = record_experiment(
        db_session,
        config={"model": "lightgbm", "seed": 42},
        data_snapshot_hashes={"feature_snapshots": "deadbeef"},
        git_sha="0" * 40,
        metrics={"pr_auc": 0.27},
    )
    db_session.flush()
    row = db_session.execute(
        text("SELECT git_sha, metrics_json FROM experiments WHERE id = :id"),
        {"id": experiment_id},
    ).one()
    assert row[0] == "0" * 40
    assert row[1]["pr_auc"] == 0.27
