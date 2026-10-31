"""Phase 3 §9 `train-risk` command: trains ONE final, deployable
LightGBM model on the full real labeled (non-censored) dataset --
distinct from the walk-forward backtest in `scripts/backtest.py`,
which evaluates the same methodology fold-by-fold but never produces
a model meant to be scored forward.

Hyperparameters are still chosen only on an inner validation split of
this real dataset (`ledgerlight.modelling.models.train_final_lightgbm`),
never peeked from anything this model will later score. The real
model artifact goes to Garage (content-addressed, gitignored) with
its sha256 recorded in `model_registry`, per §8.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.modelling.coverage import compute_verified_coverage  # noqa: E402
from ledgerlight.modelling.dataset import build_primary_outcome_dataset  # noqa: E402
from ledgerlight.modelling.models import (  # noqa: E402
    ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES,
    LIGHTGBM_SEED,
    train_final_lightgbm,
)
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402

MODEL_NAME = "primary-risk-lightgbm"
MODEL_VERSION = "1.0"


def _training_data_snapshot_hash(rows: list) -> str:  # type: ignore[type-arg]
    pairs = sorted((str(row.company_id), str(row.as_of), row.label) for row in rows)
    blob = "\n".join(f"{company_id}:{as_of}:{label}" for company_id, as_of, label in pairs).encode()
    return hashlib.sha256(blob).hexdigest()


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        coverage = compute_verified_coverage(session)
        rows = build_primary_outcome_dataset(session, coverage)
        labeled_rows = [row for row in rows if not row.censored]
        print(f"real labeled rows: {len(labeled_rows)}")

        booster, selection = train_final_lightgbm(
            labeled_rows, ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES, seed=LIGHTGBM_SEED
        )
        if booster is None or selection is None:
            print(
                "insufficient real two-class data in the inner validation split -- "
                "no final model trained (model_registry not updated)"
            )
            return 0

        artifact_bytes = booster.model_to_string().encode()
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        snapshot_hash = _training_data_snapshot_hash(labeled_rows)

        store = ObjectStore(settings)
        store.ensure_bucket()
        key, was_new = store.put_content_addressed(artifact_bytes, artifact_sha256, ".txt")
        print(f"artifact stored at {key} (new upload: {was_new})")

        session.execute(
            text(
                "INSERT INTO model_registry "
                "(id, model_name, model_version, artifact_hash, training_data_snapshot_hash, "
                " params_json) "
                "VALUES (gen_random_uuid(), :model_name, :model_version, :artifact_hash, "
                " :snapshot_hash, CAST(:params AS JSONB)) "
                "ON CONFLICT (model_name, model_version) DO UPDATE SET "
                "artifact_hash = EXCLUDED.artifact_hash, "
                "training_data_snapshot_hash = EXCLUDED.training_data_snapshot_hash, "
                "params_json = EXCLUDED.params_json"
            ),
            {
                "model_name": MODEL_NAME,
                "model_version": MODEL_VERSION,
                "artifact_hash": artifact_sha256,
                "snapshot_hash": snapshot_hash,
                "params": json.dumps(
                    {
                        **selection.config,
                        "use_scale_pos_weight": selection.use_scale_pos_weight,
                        "seed": LIGHTGBM_SEED,
                    }
                ),
            },
        )
        session.commit()

    print(f"model_registry: {MODEL_NAME}/{MODEL_VERSION} artifact_hash={artifact_sha256}")
    print(f"training_data_snapshot_hash: {snapshot_hash}")
    print(
        f"real selected config: {selection.config} "
        f"scale_pos_weight={selection.use_scale_pos_weight}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
