"""Tests for ledgerlight.agent.nli_calibration -- pure metric
arithmetic, no model load needed."""

from __future__ import annotations

from ledgerlight.agent.nli_calibration import ThresholdCandidate


def test_threshold_candidate_precision_recall_f1() -> None:
    candidate = ThresholdCandidate(
        threshold=0.5, true_positives=8, false_positives=2, true_negatives=9, false_negatives=1
    )
    assert candidate.precision == 0.8
    assert candidate.recall == 8 / 9
    assert round(candidate.f1, 4) == round(2 * 0.8 * (8 / 9) / (0.8 + 8 / 9), 4)


def test_threshold_candidate_handles_zero_denominators() -> None:
    candidate = ThresholdCandidate(
        threshold=0.5, true_positives=0, false_positives=0, true_negatives=10, false_negatives=0
    )
    assert candidate.precision == 0.0
    assert candidate.recall == 0.0
    assert candidate.f1 == 0.0
