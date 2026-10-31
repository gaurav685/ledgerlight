"""Phase 3 §8: real scoring and storage. `write_scores` persists real
model outputs to the `scores` table; `get_score` retrieves the most
recent real score for a company at or before a given `as_of` --
point-in-time correct, never a future score leaking backward.
`record_experiment` persists one real backtest/train run to the
`experiments` table so a later `backtest` re-run on the same snapshot
can be diffed against it (§9's reproducibility requirement).

Model artifacts themselves go to Garage (gitignored), with their
sha256 recorded in `model_registry` -- not handled by this module,
which only writes the real per-company scores and run metadata.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass
from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class ScoreRow:
    company_id: uuid.UUID
    as_of: dt.date
    model_name: str
    model_version: str
    raw_probability: float
    calibrated_probability: float
    percentile: float | None
    top_shap_contributors: list[tuple[str, float]] | None
    feature_set_version: str
    outcome_spec_hash: str


def compute_percentiles(probabilities_by_company: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    """Real percentile rank (0-100) of each company's probability
    among the real cohort scored at the same as_of -- never computed
    against a different month's cohort. A single-company cohort has
    no real rank to offer, so it gets the real midpoint (50.0) rather
    than a fabricated extreme."""
    if not probabilities_by_company:
        return {}
    items = sorted(probabilities_by_company.items(), key=lambda kv: kv[1])
    n = len(items)
    if n == 1:
        return {items[0][0]: 50.0}
    return {company_id: 100.0 * rank / (n - 1) for rank, (company_id, _value) in enumerate(items)}


def write_scores(session: Session, rows: list[ScoreRow]) -> None:
    for row in rows:
        session.execute(
            text(
                "INSERT INTO scores "
                "(id, company_id, as_of, model_name, model_version, raw_probability, "
                " calibrated_probability, percentile, top_shap_contributors, "
                " feature_set_version, outcome_spec_hash) "
                "VALUES (:id, :company_id, :as_of, :model_name, :model_version, "
                " :raw_probability, :calibrated_probability, :percentile, "
                " CAST(:top_shap_contributors AS JSONB), :feature_set_version, "
                " :outcome_spec_hash) "
                "ON CONFLICT (company_id, as_of, model_name, model_version) DO UPDATE SET "
                "raw_probability = EXCLUDED.raw_probability, "
                "calibrated_probability = EXCLUDED.calibrated_probability, "
                "percentile = EXCLUDED.percentile, "
                "top_shap_contributors = EXCLUDED.top_shap_contributors, "
                "feature_set_version = EXCLUDED.feature_set_version, "
                "outcome_spec_hash = EXCLUDED.outcome_spec_hash"
            ),
            {
                "id": uuid.uuid4(),
                "company_id": row.company_id,
                "as_of": row.as_of,
                "model_name": row.model_name,
                "model_version": row.model_version,
                "raw_probability": row.raw_probability,
                "calibrated_probability": row.calibrated_probability,
                "percentile": row.percentile,
                "top_shap_contributors": (
                    json.dumps(row.top_shap_contributors)
                    if row.top_shap_contributors is not None
                    else None
                ),
                "feature_set_version": row.feature_set_version,
                "outcome_spec_hash": row.outcome_spec_hash,
            },
        )


@dataclass
class RetrievedScore:
    company_id: uuid.UUID
    as_of: dt.date
    model_name: str
    model_version: str
    raw_probability: float
    calibrated_probability: float
    percentile: float | None
    top_shap_contributors: list[object] | None
    feature_set_version: str
    outcome_spec_hash: str


def get_score(
    session: Session,
    company_id: uuid.UUID,
    as_of: dt.date,
    model_name: str,
    model_version: str,
) -> RetrievedScore | None:
    """Real point-in-time retrieval: the most recent real score for
    this company/model with `score.as_of <= as_of`. Returns `None` if
    no such score has ever been computed -- never a future score,
    never a fabricated one."""
    row = session.execute(
        text(
            "SELECT company_id, as_of, model_name, model_version, raw_probability, "
            "calibrated_probability, percentile, top_shap_contributors, "
            "feature_set_version, outcome_spec_hash "
            "FROM scores "
            "WHERE company_id = :company_id AND model_name = :model_name "
            "AND model_version = :model_version AND as_of <= :as_of "
            "ORDER BY as_of DESC LIMIT 1"
        ),
        {
            "company_id": company_id,
            "model_name": model_name,
            "model_version": model_version,
            "as_of": as_of,
        },
    ).one_or_none()
    if row is None:
        return None
    return RetrievedScore(
        company_id=cast(uuid.UUID, row[0]),
        as_of=cast(dt.date, row[1]),
        model_name=cast(str, row[2]),
        model_version=cast(str, row[3]),
        raw_probability=cast(float, row[4]),
        calibrated_probability=cast(float, row[5]),
        percentile=cast("float | None", row[6]),
        top_shap_contributors=cast("list[object] | None", row[7]),
        feature_set_version=cast(str, row[8]),
        outcome_spec_hash=cast(str, row[9]),
    )


def record_experiment(
    session: Session,
    config: dict[str, object],
    data_snapshot_hashes: dict[str, object],
    git_sha: str,
    metrics: dict[str, object],
    artifacts_uri: str | None = None,
) -> uuid.UUID:
    experiment_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO experiments "
            "(id, config_json, data_snapshot_hashes, git_sha, metrics_json, artifacts_uri) "
            "VALUES (:id, CAST(:config AS JSONB), CAST(:hashes AS JSONB), :git_sha, "
            "CAST(:metrics AS JSONB), :artifacts_uri)"
        ),
        {
            "id": experiment_id,
            "config": json.dumps(config),
            "hashes": json.dumps(data_snapshot_hashes),
            "git_sha": git_sha,
            "metrics": json.dumps(metrics),
            "artifacts_uri": artifacts_uri,
        },
    )
    return experiment_id
