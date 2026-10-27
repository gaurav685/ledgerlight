"""Phase 3 §1.3: fixes the circular classifier-selection bug from Phase 2
(selecting by silver validation macro_f1 let rules_baseline "win" simply
because it IS the function that generated the silver labels). Selects a
production classifier PER EVENT TYPE using GOLD validation items only
(label_source='human_reviewed', split='validation'), with bootstrap 95%
CIs and an explicit insufficient-support flag. Read-only against
label_items; never reviews/decides anything.
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.classifier import (  # noqa: E402
    deberta_zero_shot_predict,
    rules_baseline_predict,
    tfidf_lr_predict,
)
from ledgerlight.knowledge.classifier_eval import (  # noqa: E402
    load_gold_split,
    select_production_classifier_per_class,
)
from ledgerlight.knowledge.models import LabelItem  # noqa: E402
from ledgerlight.modelling.frozen_split_guard import assert_no_frozen_test_ids  # noqa: E402
from scripts.train_classifier import MODEL_PATH  # noqa: E402

OUTPUT_PATH = Path("data/manifests/classifier-selection-gold-validation.json")
RAW_PREDICTIONS_PATH = Path("docs/phase-3/evidence/select-classifiers-raw-predictions.json")


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with MODEL_PATH.open("rb") as f:
        tfidf_model = pickle.load(f)

    with session_factory() as session:
        gold_val_ids = session.scalars(
            select(LabelItem.id).where(
                LabelItem.split == "validation", LabelItem.label_source == "human_reviewed"
            )
        ).all()
        assert_no_frozen_test_ids(gold_val_ids, context="select_classifiers.py gold validation")

        gold_val = load_gold_split(session, "validation")
        print(f"gold validation examples: {len(gold_val)}")

        texts = [e.text for e in gold_val]
        ids = [str(e.chunk_id) for e in gold_val]
        golds = [e.label for e in gold_val]
        predictions_by_method = {
            "rules_baseline": [rules_baseline_predict(t) for t in texts],
            "tfidf_lr": tfidf_lr_predict(tfidf_model, texts),
            "deberta_zero_shot": [deberta_zero_shot_predict(t)[0] for t in texts],
        }

    # Raw predictions, saved once -- avoids a repeat ~20min DeBERTa run
    # if a different metric needs recomputing from this same snapshot.
    RAW_PREDICTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RAW_PREDICTIONS_PATH.open("w", encoding="utf-8") as f:
        json.dump({"chunk_ids": ids, "golds": golds, **predictions_by_method}, f, indent=2)
    print(f"wrote raw predictions to {RAW_PREDICTIONS_PATH}")

    selections = select_production_classifier_per_class(gold_val, predictions_by_method)

    print(f"\n{'event_type':<14} {'support':>7} {'selected':>18} {'flag':<28}")
    report = {}
    for cls, sel in selections.items():
        flag = "insufficient_support" if sel.insufficient_support else ""
        if sel.support == 0:
            flag = "no_gold_validation_data"
        print(f"{cls:<14} {sel.support:>7} {str(sel.selected_method):>18} {flag:<28}")
        report[cls] = {
            "support": sel.support,
            "selected_method": sel.selected_method,
            "method_f1": sel.method_f1,
            "f1_95ci": {m: list(ci) for m, ci in sel.f1_ci.items()},
            "method_precision": sel.method_precision,
            "precision_95ci": {m: list(ci) for m, ci in sel.precision_ci.items()},
            "insufficient_support": sel.insufficient_support,
        }
        if sel.method_f1:
            for method, f1 in sel.method_f1.items():
                f1_lo, f1_hi = sel.f1_ci[method]
                p = sel.method_precision[method]
                p_lo, p_hi = sel.precision_ci[method]
                print(
                    f"    {method:<20} F1={f1:.3f} CI=[{f1_lo:.3f},{f1_hi:.3f}]  "
                    f"precision={p:.3f} CI=[{p_lo:.3f},{p_hi:.3f}]"
                )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nwrote {OUTPUT_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
