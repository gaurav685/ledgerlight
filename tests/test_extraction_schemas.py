"""Unit tests for every per-event-type Pydantic extraction schema: all
fields optional (missing stays None, never inferred), extra fields
rejected (strict schema -- a typo in an extractor can't silently create
a new, unvalidated field)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from ledgerlight.knowledge.extraction_schemas import (
    EVENT_TYPE_SCHEMAS,
    AuditQualFields,
    AudResignFields,
    ForensicFields,
    IdExitFields,
    KmpExitFields,
    PledgeUpFields,
    RatingActFields,
    ResultDelayFields,
    RptGrowthFields,
)


def test_all_nine_non_deferred_event_types_have_a_schema() -> None:
    expected = {
        "AUD_RESIGN",
        "KMP_EXIT",
        "ID_EXIT",
        "PLEDGE_UP",
        "RATING_ACT",
        "AUDIT_QUAL",
        "FORENSIC",
        "RPT_GROWTH",
        "RESULT_DELAY",
    }
    assert set(EVENT_TYPE_SCHEMAS.keys()) == expected


@pytest.mark.parametrize("schema_cls", EVENT_TYPE_SCHEMAS.values())
def test_schema_allows_all_fields_missing(schema_cls: type[BaseModel]) -> None:
    instance = schema_cls()
    for field_name in schema_cls.model_fields:
        assert getattr(instance, field_name) is None


@pytest.mark.parametrize("schema_cls", EVENT_TYPE_SCHEMAS.values())
def test_schema_rejects_unknown_extra_field(schema_cls: type[BaseModel]) -> None:
    with pytest.raises(ValidationError):
        schema_cls(this_field_does_not_exist="oops")


def test_aud_resign_accepts_real_shaped_values() -> None:
    f = AudResignFields(
        audit_firm="Price Waterhouse & Co Chartered Accountants LLP",
        resignation_date=dt.date(2018, 4, 28),
        stated_reasons=None,
    )
    assert f.audit_firm == "Price Waterhouse & Co Chartered Accountants LLP"
    assert f.resignation_date == dt.date(2018, 4, 28)
    assert f.firm_registration_number is None


def test_kmp_exit_din_as_string_not_coerced_to_int() -> None:
    f = KmpExitFields(din="01334483")
    assert f.din == "01334483"


def test_id_exit_defaults() -> None:
    f = IdExitFields()
    assert f.person_name is None
    assert f.stated_reason is None


def test_pledge_up_decimal_precision_preserved() -> None:
    f = PledgeUpFields(
        promoter_holding_pct=Decimal("55.25"), pledged_pct_of_promoter_holding=Decimal("12.345")
    )
    assert f.promoter_holding_pct == Decimal("55.25")
    assert f.pledged_pct_of_promoter_holding == Decimal("12.345")


def test_rating_act_fields() -> None:
    f = RatingActFields(
        agency="CARE", previous_rating="AA", new_rating="A+", action_type="downgrade"
    )
    assert f.new_rating == "A+"


def test_audit_qual_opinion_type_is_free_text_not_an_enum() -> None:
    f = AuditQualFields(opinion_type="emphasis_of_matter")
    assert f.opinion_type == "emphasis_of_matter"


def test_forensic_fields() -> None:
    f = ForensicFields(auditor_appointed="BDO", scope="review of related party transactions")
    assert f.auditor_appointed == "BDO"


def test_rpt_growth_decimal_amount() -> None:
    f = RptGrowthFields(counterparty="Promoter Group Entity", amount=Decimal("1000000.50"))
    assert f.amount == Decimal("1000000.50")


def test_result_delay_fields() -> None:
    f = ResultDelayFields(
        period="Q1", deadline=dt.date(2025, 8, 14), actual_date=dt.date(2025, 8, 20)
    )
    assert f.actual_date is not None and f.deadline is not None
    assert (f.actual_date - f.deadline).days == 6
