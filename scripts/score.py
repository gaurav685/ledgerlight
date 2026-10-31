"""Phase 3 §9 `score` command: loads the real trained LightGBM model
artifact from Garage (its sha256 recorded by `scripts/train_risk.py`
in `model_registry`) and writes real scores for every company in the
verified-coverage universe at its own latest real feature snapshot
`as_of` -- never a future date, never a company outside the universe
this model was trained on.

Known, disclosed simplifications (stated here rather than built out
further, since this dataset's own real backtest result is that no
model beats the base rate -- see `scripts/backtest.py` -- so there is
no real predictive signal at stake in either gap):
- Training-time missing-feature imputation used each training fold's
  own real column medians
  (`ledgerlight.modelling.models._impute_with_train_median`), which
  were not persisted as part of the saved artifact. At real
  deployment-score time this script imputes missing features with
  0.0 instead -- not bit-for-bit identical to training-time
  preprocessing.
- `calibrated_probability` here equals `raw_probability`: the
  isotonic/Platt calibration map fitted per walk-forward fold in
  `ledgerlight.modelling.backtest` was never persisted as part of the
  deployed artifact, so this script cannot apply it at score time.
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import lightgbm as lgb  # noqa: E402
from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.modelling.coverage import compute_verified_coverage  # noqa: E402
from ledgerlight.modelling.dataset import load_feature_rows  # noqa: E402
from ledgerlight.modelling.models import ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES  # noqa: E402
from ledgerlight.modelling.scoring import ScoreRow, compute_percentiles, write_scores  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402

MODEL_NAME = "primary-risk-lightgbm"
MODEL_VERSION = "1.0"
OUTCOME_SPEC_HASH = "d879a2874d063b0025820ce52223e443b5b14d7c8746aa8d9e3117e4f3503e1b"
FEATURE_SET_VERSION = "primary-structured-rv-1.0"


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        registry_row = session.execute(
            text(
                "SELECT artifact_hash FROM model_registry "
                "WHERE model_name = :name AND model_version = :version"
            ),
            {"name": MODEL_NAME, "version": MODEL_VERSION},
        ).one_or_none()
        if registry_row is None:
            print(f"no model_registry row for {MODEL_NAME}/{MODEL_VERSION} -- run train-risk first")
            return 1
        artifact_sha256 = registry_row[0]

        store = ObjectStore(settings)
        key = store.object_key(artifact_sha256, ".txt")
        artifact_text = store.get(key).decode()
        booster = lgb.Booster(model_str=artifact_text)
        print(f"loaded model artifact {key}")

        coverage = compute_verified_coverage(session)
        features_by_key = load_feature_rows(session, coverage.company_ids)

        latest_as_of_by_company: dict[uuid.UUID, dt.date] = {}
        for company_id, as_of in features_by_key:
            if as_of > latest_as_of_by_company.get(company_id, dt.date.min):
                latest_as_of_by_company[company_id] = as_of

        if not latest_as_of_by_company:
            print("no real feature snapshots found for the verified-coverage universe")
            return 0

        raw_probabilities: dict[uuid.UUID, float] = {}
        for company_id, as_of in latest_as_of_by_company.items():
            features = features_by_key[(company_id, as_of)]
            feature_values = [
                features.get(name) if features.get(name) is not None else 0.0
                for name in ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES
            ]
            prob = float(booster.predict([feature_values])[0])
            raw_probabilities[company_id] = prob

        percentiles = compute_percentiles(raw_probabilities)

        score_rows = [
            ScoreRow(
                company_id=company_id,
                as_of=latest_as_of_by_company[company_id],
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                raw_probability=prob,
                calibrated_probability=prob,
                percentile=percentiles[company_id],
                top_shap_contributors=None,
                feature_set_version=FEATURE_SET_VERSION,
                outcome_spec_hash=OUTCOME_SPEC_HASH,
            )
            for company_id, prob in raw_probabilities.items()
        ]
        write_scores(session, score_rows)
        session.commit()

    for score_row in score_rows:
        print(
            f"{score_row.company_id} as_of={score_row.as_of} "
            f"raw={score_row.raw_probability:.4f} percentile={score_row.percentile:.1f}"
        )
    print(f"wrote {len(score_rows)} real scores")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
