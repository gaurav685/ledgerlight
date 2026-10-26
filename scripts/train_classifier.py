"""Train the TF-IDF + logistic regression event classifier on the dev
split, and record it in model_registry with a training-data snapshot
hash (sha256 of the sorted (chunk_id, label) pairs) so `evaluate` can
reproduce metrics exactly against this exact snapshot."""

from __future__ import annotations

import hashlib
import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.classifier import train_tfidf_lr  # noqa: E402
from ledgerlight.knowledge.classifier_eval import load_split  # noqa: E402
from ledgerlight.knowledge.models import ModelRegistryEntry  # noqa: E402

MODEL_NAME = "tfidf-logreg-event-classifier"
MODEL_VERSION = "1"
MODEL_PATH = Path("data/models/tfidf_lr_v1.pkl")


def _snapshot_hash(examples: list) -> str:  # type: ignore[type-arg]
    pairs = sorted((str(e.chunk_id), e.label) for e in examples)
    blob = "\n".join(f"{c}:{lbl}" for c, lbl in pairs).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        dev_examples = load_split(session, "dev")
        print(f"dev examples: {len(dev_examples)}")

        model = train_tfidf_lr([e.text for e in dev_examples], [e.label for e in dev_examples])
        snapshot_hash = _snapshot_hash(dev_examples)

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)

        existing = (
            session.query(ModelRegistryEntry)
            .filter_by(model_name=MODEL_NAME, model_version=MODEL_VERSION)
            .first()
        )
        if existing is None:
            session.add(
                ModelRegistryEntry(
                    model_name=MODEL_NAME,
                    model_version=MODEL_VERSION,
                    artifact_hash=hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
                    training_data_snapshot_hash=snapshot_hash,
                    params_json={
                        "max_features": 5000,
                        "ngram_range": [1, 2],
                        "class_weight": "balanced",
                    },
                    metrics_json=None,
                )
            )
            session.commit()
            print("model_registry: created")
        else:
            existing.artifact_hash = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
            existing.training_data_snapshot_hash = snapshot_hash
            session.commit()
            print("model_registry: updated")

    print(f"classes: {model.classes}")
    print(f"training_data_snapshot_hash: {snapshot_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
