"""Pydantic schemas for structured extraction, one per event type.
Every field that isn't stated in the source text stays None -- never
inferred or invented (see ledgerlight.knowledge.extraction's evidence
verification, which rejects any value that can't be matched back to its
cited span)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class _StrictFields(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AudResignFields(_StrictFields):
    audit_firm: str | None = None
    firm_registration_number: str | None = None
    partner_name: str | None = None
    resignation_date: dt.date | None = None
    effective_date: dt.date | None = None
    stated_reasons: str | None = None


class KmpExitFields(_StrictFields):
    person_name: str | None = None
    din: str | None = None
    designation: str | None = None
    effective_date: dt.date | None = None
    stated_reason: str | None = None
    successor_named: bool | None = None


class IdExitFields(_StrictFields):
    person_name: str | None = None
    din: str | None = None
    effective_date: dt.date | None = None
    stated_reason: str | None = None


class PledgeUpFields(_StrictFields):
    as_of_date: dt.date | None = None
    promoter_holding_pct: Decimal | None = None
    pledged_pct_of_promoter_holding: Decimal | None = None
    previous_as_of_date: dt.date | None = None
    previous_promoter_holding_pct: Decimal | None = None
    previous_pledged_pct_of_promoter_holding: Decimal | None = None


class RatingActFields(_StrictFields):
    agency: str | None = None
    instrument: str | None = None
    previous_rating: str | None = None
    new_rating: str | None = None
    outlook: str | None = None
    action_type: str | None = None
    action_date: dt.date | None = None


class AuditQualFields(_StrictFields):
    opinion_type: str | None = None
    period: str | None = None
    basis_text_span: str | None = None


class ForensicFields(_StrictFields):
    auditor_appointed: str | None = None
    scope: str | None = None
    date: dt.date | None = None


class RptGrowthFields(_StrictFields):
    counterparty: str | None = None
    amount: Decimal | None = None
    period: str | None = None
    previous_amount: Decimal | None = None
    previous_period: str | None = None


class ResultDelayFields(_StrictFields):
    period: str | None = None
    deadline: dt.date | None = None
    actual_date: dt.date | None = None


EVENT_TYPE_SCHEMAS: dict[str, type[_StrictFields]] = {
    "AUD_RESIGN": AudResignFields,
    "KMP_EXIT": KmpExitFields,
    "ID_EXIT": IdExitFields,
    "PLEDGE_UP": PledgeUpFields,
    "RATING_ACT": RatingActFields,
    "AUDIT_QUAL": AuditQualFields,
    "FORENSIC": ForensicFields,
    "RPT_GROWTH": RptGrowthFields,
    "RESULT_DELAY": ResultDelayFields,
}
