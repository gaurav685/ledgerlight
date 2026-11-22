"""Tests for ledgerlight.knowledge.classifier -- specifically the
RPT_GROWTH evidence filter added after real review
(docs/enhancements/precision-review/results.md) found 18/18 of
tfidf_lr's real RPT_GROWTH flags had no quantified multi-period amount
at all."""

from __future__ import annotations

from unittest.mock import patch

from ledgerlight.knowledge.classifier import tfidf_lr_predict_rpt_growth_filtered


def test_rpt_growth_with_quantified_amounts_is_kept() -> None:
    texts = [
        "Related party transactions with XYZ Limited: Rs. 143.23 crore for the "
        "year ended March 2025, compared to Rs. 125.97 crore for the year ended "
        "March 2024."
    ]
    with patch("ledgerlight.knowledge.classifier.tfidf_lr_predict", return_value=["RPT_GROWTH"]):
        result = tfidf_lr_predict_rpt_growth_filtered(object(), texts)
    assert result == ["RPT_GROWTH"]


def test_rpt_growth_without_quantified_amounts_is_downgraded_to_none() -> None:
    # Real false-positive pattern: RPT policy boilerplate with no
    # quantified amounts, flagged RPT_GROWTH by the bag-of-words model.
    texts = [
        "Before entering related party transactions, necessary approvals are "
        "obtained from the Audit Committee and the Board."
    ]
    with patch("ledgerlight.knowledge.classifier.tfidf_lr_predict", return_value=["RPT_GROWTH"]):
        result = tfidf_lr_predict_rpt_growth_filtered(object(), texts)
    assert result == ["none"]


def test_non_rpt_growth_predictions_are_never_touched() -> None:
    texts = ["Boilerplate about something else entirely."]
    with patch("ledgerlight.knowledge.classifier.tfidf_lr_predict", return_value=["FORENSIC"]):
        result = tfidf_lr_predict_rpt_growth_filtered(object(), texts)
    assert result == ["FORENSIC"]


def test_mixed_batch_filters_only_the_rpt_growth_entries() -> None:
    texts = [
        "Rs. 10 crore in FY24 vs Rs. 8 crore in FY23 related party transactions.",
        "Generic RPT policy text, no amounts.",
        "Completely unrelated boilerplate.",
    ]
    with patch(
        "ledgerlight.knowledge.classifier.tfidf_lr_predict",
        return_value=["RPT_GROWTH", "RPT_GROWTH", "none"],
    ):
        result = tfidf_lr_predict_rpt_growth_filtered(object(), texts)
    assert result == ["RPT_GROWTH", "none", "none"]
