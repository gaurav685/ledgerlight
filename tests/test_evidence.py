"""Evidence verification tests: names (normalized substring), dates
(parsed equality), numbers (tolerance), and the failure/unverifiable
paths for each -- a value that fails verification must never be
silently promoted (see ledgerlight.knowledge.extraction)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from ledgerlight.knowledge.evidence import verify_date, verify_name, verify_number

# --- names -----------------------------------------------------------------


def test_name_verifies_against_real_corpus_shaped_span() -> None:
    span = (
        "BY THE STATUTORY AUDITOR - PRICE WATERHOUSE & CO\n"
        "CHARTERED ACCOUNTANTS LLP (PWC)\n\n"
        "This is to hereby inform that Price Waterhouse & Co "
        "Chartered Accountants LLP (PWC) has resigned."
    )
    assert verify_name("Price Waterhouse & Co Chartered Accountants LLP", span) == "validated"


def test_name_verification_is_case_insensitive() -> None:
    assert verify_name("infosys limited", "INFOSYS LIMITED announced today") == "validated"


def test_name_verification_collapses_whitespace() -> None:
    assert verify_name("Infosys Limited", "Infosys\n   Limited announced") == "validated"


def test_name_not_in_span_fails() -> None:
    assert verify_name("Deloitte", "Price Waterhouse has resigned as auditor") == "failed"


def test_name_invented_value_not_present_anywhere_fails() -> None:
    # The adversarial case: a value the extractor invented, never stated
    # in the source at all.
    assert verify_name("Ernst & Young", "The company reported quarterly results.") == "failed"


def test_empty_span_is_unverifiable() -> None:
    assert verify_name("Deloitte", "") == "unverifiable"


# --- dates -------------------------------------------------------------


def test_date_verifies_against_dd_mon_yyyy_format() -> None:
    assert verify_date(dt.date(2018, 4, 28), "Mumbai, April 28, 2018: This is to inform") == (
        "validated"
    )


def test_date_verifies_against_iso_format() -> None:
    assert verify_date(dt.date(2023, 8, 21), "trade date 2023-08-21 close price") == "validated"


def test_date_mismatch_fails() -> None:
    assert verify_date(dt.date(2018, 4, 29), "Mumbai, April 28, 2018: This is to inform") == (
        "failed"
    )


def test_date_with_no_date_in_span_is_unverifiable() -> None:
    assert verify_date(dt.date(2018, 4, 28), "The company announced a change.") == "unverifiable"


# --- numbers -------------------------------------------------------------


def test_number_exact_match_validates() -> None:
    assert verify_number(Decimal("55.25"), "promoter holding stands at 55.25%") == "validated"


def test_number_within_tolerance_validates() -> None:
    assert verify_number(Decimal("55.25"), "promoter holding stands at 55.2495%") == "validated"


def test_number_outside_tolerance_fails() -> None:
    assert verify_number(Decimal("55.25"), "promoter holding stands at 60.00%") == "failed"


def test_number_handles_thousands_separators() -> None:
    assert verify_number(Decimal("1000000"), "the amount was Rs 1,000,000 only") == "validated"


def test_number_no_numbers_in_span_is_unverifiable() -> None:
    assert (
        verify_number(Decimal("55.25"), "no numbers appear in this text at all") == "unverifiable"
    )


def test_number_invented_value_not_present_fails() -> None:
    # Adversarial: an invented percentage not actually stated anywhere.
    assert verify_number(Decimal("99.9"), "promoter holding stands at 30%") == "failed"
