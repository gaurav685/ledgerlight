"""Boundary tests for every rule-based taxonomy threshold in
ledgerlight.knowledge.taxonomy -- each exact boundary the Phase 2 brief
calls out explicitly."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from ledgerlight.knowledge.taxonomy import (
    audit_qual_is_qualification,
    audit_qual_severity,
    pledge_up_triggers,
    result_delay_check,
    result_delay_deadline,
    rpt_growth_triggers,
)

# --- PLEDGE_UP ---------------------------------------------------------------


def test_pledge_up_increase_of_4_99pp_does_not_trigger() -> None:
    assert pledge_up_triggers(Decimal("40.00"), Decimal("44.99")) is False


def test_pledge_up_increase_of_exactly_5_00pp_triggers() -> None:
    assert pledge_up_triggers(Decimal("40.00"), Decimal("45.00")) is True


def test_pledge_up_crossing_49_9_to_50_0_triggers() -> None:
    assert pledge_up_triggers(Decimal("49.9"), Decimal("50.0")) is True


def test_pledge_up_crossing_49_9_to_above_50_triggers() -> None:
    assert pledge_up_triggers(Decimal("49.9"), Decimal("52.0")) is True


def test_pledge_up_staying_above_50_with_small_increase_does_not_trigger() -> None:
    assert pledge_up_triggers(Decimal("55.0"), Decimal("56.0")) is False


def test_pledge_up_no_change_does_not_trigger() -> None:
    assert pledge_up_triggers(Decimal("30.0"), Decimal("30.0")) is False


def test_pledge_up_decrease_does_not_trigger() -> None:
    assert pledge_up_triggers(Decimal("60.0"), Decimal("55.0")) is False


# --- RESULT_DELAY --------------------------------------------------------


def test_result_delay_q1_deadline_is_45_days_after_quarter_end() -> None:
    assert result_delay_deadline("Q1", dt.date(2025, 6, 30)) == dt.date(2025, 8, 14)


def test_result_delay_annual_deadline_is_60_days_after_fy_end() -> None:
    assert result_delay_deadline("ANNUAL", dt.date(2025, 3, 31)) == dt.date(2025, 5, 30)


def test_result_delay_q4_uses_the_annual_60_day_deadline_not_45() -> None:
    # The real regulatory nuance: Q4 standalone figures ride with the
    # annual filing under Reg 33(3)(e) -- never checked against the
    # 45-day quarterly rule.
    q4_deadline = result_delay_deadline("Q4", dt.date(2025, 3, 31))
    annual_deadline = result_delay_deadline("ANNUAL", dt.date(2025, 3, 31))
    assert q4_deadline == annual_deadline == dt.date(2025, 5, 30)


def test_result_delay_filed_exactly_on_deadline_is_on_time() -> None:
    outcome = result_delay_check("Q1", dt.date(2025, 6, 30), dt.date(2025, 8, 14))
    assert outcome.status == "on_time"
    assert outcome.delay_days == 0


def test_result_delay_filed_one_day_late_is_delayed() -> None:
    outcome = result_delay_check("Q1", dt.date(2025, 6, 30), dt.date(2025, 8, 15))
    assert outcome.status == "delayed"
    assert outcome.delay_days == 1


def test_result_delay_missing_filing_date_is_unverifiable_not_guessed() -> None:
    outcome = result_delay_check("Q1", dt.date(2025, 6, 30), None)
    assert outcome.status == "unverifiable"
    assert outcome.delay_days is None
    assert outcome.deadline is None


# --- RPT_GROWTH ----------------------------------------------------------


def test_rpt_growth_absolute_doubling_triggers() -> None:
    assert (
        rpt_growth_triggers(rpt_amount=Decimal("200"), previous_rpt_amount=Decimal("100")) is True
    )


def test_rpt_growth_just_under_doubling_without_revenue_data_does_not_trigger() -> None:
    assert (
        rpt_growth_triggers(rpt_amount=Decimal("199"), previous_rpt_amount=Decimal("100")) is False
    )


def test_rpt_growth_share_increase_of_5pp_triggers() -> None:
    # 10/100=10% share -> 20/120=16.67% share: +6.67pp >= 5pp
    assert (
        rpt_growth_triggers(
            rpt_amount=Decimal("20"),
            previous_rpt_amount=Decimal("10"),
            revenue=Decimal("120"),
            previous_revenue=Decimal("100"),
        )
        is True
    )


def test_rpt_growth_small_share_increase_without_doubling_does_not_trigger() -> None:
    # 10/100=10% -> 11/100=11%: +1pp, absolute growth only 1.1x
    assert (
        rpt_growth_triggers(
            rpt_amount=Decimal("11"),
            previous_rpt_amount=Decimal("10"),
            revenue=Decimal("100"),
            previous_revenue=Decimal("100"),
        )
        is False
    )


def test_rpt_growth_zero_previous_amount_does_not_crash() -> None:
    assert rpt_growth_triggers(rpt_amount=Decimal("10"), previous_rpt_amount=Decimal("0")) is False


# --- AUDIT_QUAL ------------------------------------------------------------


def test_audit_qual_emphasis_of_matter_is_not_a_qualification() -> None:
    assert audit_qual_is_qualification("emphasis_of_matter") is False


def test_audit_qual_qualified_is_a_qualification() -> None:
    assert audit_qual_is_qualification("qualified") is True


def test_audit_qual_adverse_and_disclaimer_are_qualifications() -> None:
    assert audit_qual_is_qualification("adverse") is True
    assert audit_qual_is_qualification("disclaimer") is True


def test_audit_qual_unqualified_is_not_a_qualification() -> None:
    assert audit_qual_is_qualification("unqualified") is False


def test_audit_qual_severity_ordering() -> None:
    assert audit_qual_severity("adverse") == "high"
    assert audit_qual_severity("disclaimer") == "high"
    assert audit_qual_severity("qualified") == "medium"
    assert audit_qual_severity("emphasis_of_matter") == "low"
