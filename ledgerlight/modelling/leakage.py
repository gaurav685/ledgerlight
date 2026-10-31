"""Sec7 leakage checks, as both automated tests (`tests/test_leakage.py`)
and a real report (`run_leakage_report`, used in the §15 final
report):

- outcome date > as_of for every label
- time-ordered folds with the embargo enforced
- label-permutation test: performance should land roughly at prevalence
- feature-shift test: shifting features forward must make performance
  worse (or at least not better); investigate if it improves
- flag any feature with univariate PR-AUC near 1.0
- a deliberately leaky synthetic feature must be caught, proven
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import numpy as np
from sklearn.metrics import average_precision_score

from ledgerlight.modelling.backtest import BacktestResult, run_backtest
from ledgerlight.modelling.coverage import VerifiedCoverage
from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.dates import add_months
from ledgerlight.modelling.folds import EMBARGO_MONTHS, HORIZON_MONTHS, Fold

UNIVARIATE_PR_AUC_FLAG_THRESHOLD = 0.95


def check_outcome_date_after_as_of(rows: list[DatasetRow]) -> list[str]:
    """Real violations found (empty list = check passed): every real
    labeled positive row's triggering event must fall on or after its
    own as_of -- the forward-window label can never be caused by
    something that already happened before the observation point."""
    violations: list[str] = []
    for row in rows:
        if row.censored or row.label != 1:
            continue
        if row.triggering_event_time is None:
            violations.append(
                f"{row.company_name} {row.as_of}: label=1 with no triggering_event_time"
            )
            continue
        if row.triggering_event_time.date() < row.as_of:
            violations.append(
                f"{row.company_name} {row.as_of}: triggering event "
                f"{row.triggering_event_time} precedes as_of"
            )
    return violations


def check_embargo_enforced(folds: list[Fold]) -> list[str]:
    """Real violations found (empty list = check passed): no fold's
    train row may fall within HORIZON_MONTHS + EMBARGO_MONTHS of that
    fold's own test_start."""
    violations: list[str] = []
    for fold in folds:
        required_cutoff = add_months(fold.test_start, -(HORIZON_MONTHS + EMBARGO_MONTHS))
        if required_cutoff != fold.train_cutoff:
            violations.append(
                f"fold {fold.test_year}: train_cutoff {fold.train_cutoff} != "
                f"required {required_cutoff}"
            )
        for row in fold.train_rows:
            if row.as_of >= fold.train_cutoff:
                violations.append(
                    f"fold {fold.test_year}: train row {row.company_name} {row.as_of} "
                    f"violates the embargo (cutoff {fold.train_cutoff})"
                )
    return violations


def permute_labels(rows: list[DatasetRow], seed: int = 0) -> list[DatasetRow]:
    """Real labeled rows only, with labels permuted across companies
    and time -- any real feature/outcome relationship is destroyed, so
    a model trained on this should perform at roughly the real
    prevalence, not above it."""
    labeled = [row for row in rows if not row.censored]
    rng = np.random.default_rng(seed)
    real_labels = [cast(int, row.label) for row in labeled]
    permuted_labels = rng.permutation(real_labels)
    return [
        DatasetRow(
            company_id=row.company_id,
            company_name=row.company_name,
            as_of=row.as_of,
            features=row.features,
            label=int(new_label),
            censored=False,
            censor_reason=None,
            triggering_outcome_types=row.triggering_outcome_types,
            triggering_event_time=row.triggering_event_time,
        )
        for row, new_label in zip(labeled, permuted_labels, strict=True)
    ]


def shift_features_forward(rows: list[DatasetRow], months: int = 1) -> list[DatasetRow]:
    """Real feature-shift test input: every non-censored row's
    features are replaced with the real features recorded `months`
    later for the SAME company (using the real feature values already
    attached to every row in `rows`, censored or not, so the lookup
    has full coverage). A row with no real later snapshot is dropped,
    never fabricated."""
    features_by_key = {(row.company_id, row.as_of): row.features for row in rows}
    shifted: list[DatasetRow] = []
    for row in rows:
        if row.censored:
            continue
        shifted_as_of = add_months(row.as_of, months)
        shifted_features = features_by_key.get((row.company_id, shifted_as_of))
        if shifted_features is None:
            continue
        shifted.append(
            DatasetRow(
                company_id=row.company_id,
                company_name=row.company_name,
                as_of=row.as_of,
                features=shifted_features,
                label=row.label,
                censored=False,
                censor_reason=None,
                triggering_outcome_types=row.triggering_outcome_types,
                triggering_event_time=row.triggering_event_time,
            )
        )
    return shifted


def univariate_pr_auc_flags(
    rows: list[DatasetRow],
    feature_names: list[str],
    threshold: float = UNIVARIATE_PR_AUC_FLAG_THRESHOLD,
) -> dict[str, float]:
    """Real per-feature PR-AUC (best of the raw value or its negation,
    since a feature can be a real inverse predictor), computed only on
    real labeled rows. Returns `{feature: score}` for every feature at
    or above `threshold` -- a real signal worth investigating, not
    automatically proof of leakage."""
    labeled = [row for row in rows if not row.censored]
    y = np.array([row.label for row in labeled], dtype=float)
    if len(set(y.tolist())) < 2:
        return {}

    flags: dict[str, float] = {}
    for name in feature_names:
        values = np.array(
            [
                row.features.get(name) if row.features.get(name) is not None else np.nan
                for row in labeled
            ],
            dtype=float,
        )
        mask = ~np.isnan(values)
        if mask.sum() < 2 or len(set(y[mask].tolist())) < 2:
            continue
        score = max(
            float(average_precision_score(y[mask], values[mask])),
            float(average_precision_score(y[mask], -values[mask])),
        )
        if score >= threshold:
            flags[name] = score
    return flags


@dataclass
class LeakageReport:
    outcome_date_violations: list[str] = field(default_factory=list)
    embargo_violations: list[str] = field(default_factory=list)
    real_pooled_lightgbm_pr_auc: float | None = None
    real_pooled_prevalence: float = 0.0
    permuted_pooled_lightgbm_pr_auc: float | None = None
    feature_shift_pooled_lightgbm_pr_auc: float | None = None
    univariate_pr_auc_flags: dict[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.outcome_date_violations and not self.embargo_violations


def run_leakage_report(
    rows: list[DatasetRow],
    coverage: VerifiedCoverage,
    feature_names: list[str],
    real_backtest: BacktestResult,
    seed: int = 42,
) -> LeakageReport:
    """Runs every real §7 leakage check against the real
    verified-coverage dataset. `real_backtest` is the already-computed
    real `run_backtest` result (reused so this never re-fits the real
    model twice); the permutation and feature-shift variants are each
    run once, fresh, here."""
    outcome_date_violations = check_outcome_date_after_as_of(rows)
    embargo_violations = check_embargo_enforced(real_backtest.folds)

    real_lgbm = real_backtest.pooled_outputs.get("LightGBM")
    real_pr_auc = real_lgbm.metrics.pr_auc if real_lgbm else None
    real_prevalence = real_lgbm.metrics.prevalence if real_lgbm else 0.0

    permuted_rows = permute_labels(rows, seed=seed)
    permuted_backtest = run_backtest(permuted_rows, coverage, seed=seed)
    permuted_lgbm = permuted_backtest.pooled_outputs.get("LightGBM")
    permuted_pr_auc = permuted_lgbm.metrics.pr_auc if permuted_lgbm else None

    shifted_rows = shift_features_forward(rows, months=1)
    shifted_backtest = run_backtest(shifted_rows, coverage, seed=seed)
    shifted_lgbm = shifted_backtest.pooled_outputs.get("LightGBM")
    shifted_pr_auc = shifted_lgbm.metrics.pr_auc if shifted_lgbm else None

    flags = univariate_pr_auc_flags(rows, feature_names)

    return LeakageReport(
        outcome_date_violations=outcome_date_violations,
        embargo_violations=embargo_violations,
        real_pooled_lightgbm_pr_auc=real_pr_auc,
        real_pooled_prevalence=real_prevalence,
        permuted_pooled_lightgbm_pr_auc=permuted_pr_auc,
        feature_shift_pooled_lightgbm_pr_auc=shifted_pr_auc,
        univariate_pr_auc_flags=flags,
    )


def print_leakage_report(report: LeakageReport) -> None:
    print(f"outcome-date-after-as_of violations: {len(report.outcome_date_violations)}")
    for v in report.outcome_date_violations:
        print(f"  {v}")
    print(f"embargo violations: {len(report.embargo_violations)}")
    for v in report.embargo_violations:
        print(f"  {v}")
    print(
        f"real pooled LightGBM PR-AUC: {report.real_pooled_lightgbm_pr_auc} "
        f"(prevalence {report.real_pooled_prevalence})"
    )
    print(f"label-permutation pooled LightGBM PR-AUC: {report.permuted_pooled_lightgbm_pr_auc}")
    print(f"feature-shift pooled LightGBM PR-AUC: {report.feature_shift_pooled_lightgbm_pr_auc}")
    print(
        f"univariate PR-AUC flags (>= {UNIVARIATE_PR_AUC_FLAG_THRESHOLD}): "
        f"{report.univariate_pr_auc_flags}"
    )
