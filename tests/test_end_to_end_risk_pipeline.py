"""Phase 3 §10's required integration test: the end-to-end risk
pipeline on a small real slice. The real verified-coverage universe
(5 companies, 144 labeled rows) already IS that small slice -- this
test runs coverage -> dataset -> folds -> backtest -> leakage-check ->
scoring/get_score against the real local DB end to end and asserts
the real invariants hold, rather than re-deriving a synthetic toy
dataset that would test a different code path than production."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ledgerlight.modelling.backtest import MODEL_NAMES, run_backtest
from ledgerlight.modelling.coverage import compute_verified_coverage
from ledgerlight.modelling.dataset import build_primary_outcome_dataset
from ledgerlight.modelling.leakage import run_leakage_report
from ledgerlight.modelling.models import ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES
from ledgerlight.modelling.scoring import ScoreRow, get_score, write_scores

pytestmark = pytest.mark.integration


def test_end_to_end_pipeline_on_the_real_small_verified_coverage_slice(db_session: Session) -> None:
    coverage = compute_verified_coverage(db_session)
    assert len(coverage.company_ids) >= 1

    rows = build_primary_outcome_dataset(db_session, coverage)
    labeled_rows = [row for row in rows if not row.censored]
    assert len(rows) > 0
    assert len(labeled_rows) > 0

    backtest = run_backtest(rows, coverage)
    assert set(backtest.pooled_outputs) == set(MODEL_NAMES)
    for name in MODEL_NAMES:
        output = backtest.pooled_outputs[name]
        assert output.metrics.n == sum(len(fold.test_rows) for fold in backtest.folds)

    assert backtest.pooled_positive_counts is not None
    assert backtest.pooled_positive_counts.distinct_positive_events >= 0

    leakage_report = run_leakage_report(
        rows, coverage, ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES, backtest
    )
    assert leakage_report.outcome_date_violations == []
    assert leakage_report.embargo_violations == []

    # write_scores/get_score round-trip on one real company, inside the
    # same rolled-back transaction as the rest of this test.
    one_company_id = coverage.company_ids[0]
    one_row = next(row for row in labeled_rows if row.company_id == one_company_id)
    write_scores(
        db_session,
        [
            ScoreRow(
                company_id=one_company_id,
                as_of=one_row.as_of,
                model_name="integration-test-model",
                model_version="1.0",
                raw_probability=0.42,
                calibrated_probability=0.42,
                percentile=50.0,
                top_shap_contributors=None,
                feature_set_version="primary-structured-rv-1.0",
                outcome_spec_hash="b" * 64,
            )
        ],
    )
    db_session.flush()
    retrieved = get_score(
        db_session, one_company_id, one_row.as_of, "integration-test-model", "1.0"
    )
    assert retrieved is not None
    assert retrieved.raw_probability == 0.42
