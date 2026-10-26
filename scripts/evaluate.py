"""Evaluate all three classifiers (rules baseline, TF-IDF+LR, DeBERTa
zero-shot) on the validation split, select a production classifier, then
report ONCE on the test split with the selected method. All metrics are
against SILVER labels -- see docs/evaluation/phase-2-evaluation.md.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.classifier import (  # noqa: E402
    FINE_TUNE_MIN_POSITIVES_PER_CLASS,
    deberta_zero_shot_predict,
    rules_baseline_predict,
    tfidf_lr_predict,
)
from ledgerlight.knowledge.classifier_eval import (  # noqa: E402
    evaluate_predictions,
    load_split,
    print_report,
)
from scripts.train_classifier import MODEL_PATH  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with MODEL_PATH.open("rb") as f:
        tfidf_model = pickle.load(f)  # noqa: S301 -- our own trained artifact

    with session_factory() as session:
        validation = load_split(session, "validation")
        test = load_split(session, "test")

        print(f"validation examples: {len(validation)}")
        print(f"test examples: {len(test)}")

        print("\n--- fine-tuning decision ---")
        from collections import Counter

        dev = load_split(session, "dev")
        counts = Counter(e.label for e in dev + validation + test)
        print(f"positives per class (dev+validation+test combined): {dict(counts)}")
        print(f"fine-tune threshold: >= {FINE_TUNE_MIN_POSITIVES_PER_CLASS} positives/class")
        max_count = max((c for label, c in counts.items() if label != "none"), default=0)
        print(
            f"max positives in any non-'none' class: {max_count} -- "
            f"{'MEETS' if max_count >= FINE_TUNE_MIN_POSITIVES_PER_CLASS else 'does NOT meet'} "
            "the threshold. Decision: zero-shot only, no fine-tuning attempted."
        )

        print("\n=== VALIDATION ===")
        y_true = [e.label for e in validation]

        y_pred_rules = [rules_baseline_predict(e.text) for e in validation]
        report_rules = evaluate_predictions("rules_baseline", y_true, y_pred_rules)
        print_report(report_rules)

        y_pred_tfidf = tfidf_lr_predict(tfidf_model, [e.text for e in validation])
        report_tfidf = evaluate_predictions("tfidf_lr", y_true, y_pred_tfidf)
        print_report(report_tfidf)

        y_pred_deberta = []
        deberta_confidences = []
        for e in validation:
            code, conf = deberta_zero_shot_predict(e.text)
            y_pred_deberta.append(code)
            deberta_confidences.append(conf)
        report_deberta = evaluate_predictions("deberta_zero_shot", y_true, y_pred_deberta)
        print_report(report_deberta)

        print("\n-- DeBERTa confidence distribution (validation) --")
        if deberta_confidences:
            print(
                f"  min={min(deberta_confidences):.3f} max={max(deberta_confidences):.3f} "
                f"mean={sum(deberta_confidences) / len(deberta_confidences):.3f}"
            )
        print(
            "  (sample sizes per class are too small, 2-28 positives, for a reliable "
            "calibration curve -- not computed; reporting the raw confidence range instead)"
        )

        reports = {
            "rules_baseline": report_rules,
            "tfidf_lr": report_tfidf,
            "deberta_zero_shot": report_deberta,
        }
        selected = max(reports.items(), key=lambda kv: kv[1].macro_f1)
        print(
            f"\n=== Selected production classifier (by validation macro_f1): {selected[0]} "
            f"(macro_f1={selected[1].macro_f1:.3f}) ==="
        )

        print("\n=== TEST (reported once, selected method only) ===")
        y_true_test = [e.label for e in test]
        if selected[0] == "rules_baseline":
            y_pred_test = [rules_baseline_predict(e.text) for e in test]
        elif selected[0] == "tfidf_lr":
            y_pred_test = tfidf_lr_predict(tfidf_model, [e.text for e in test])
        else:
            y_pred_test = [deberta_zero_shot_predict(e.text)[0] for e in test]
        report_test = evaluate_predictions(f"{selected[0]}_TEST", y_true_test, y_pred_test)
        print_report(report_test)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
