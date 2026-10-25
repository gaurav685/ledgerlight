"""Taxonomy loading and the rule-based thresholds that are "code, each
with boundary tests" per the Phase 2 brief. Loaded wholesale from
data/taxonomy/taxonomy-v*.yaml -- never hand-inserted into
taxonomy_versions/event_types. See docs/knowledge/taxonomy.md.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.common.hashing import sha256_bytes
from ledgerlight.knowledge.models import EventType, TaxonomyVersion


@dataclass
class TaxonomyLoadResult:
    version: str
    event_types_loaded: int
    was_new: bool


def load_taxonomy(session: Session, yaml_path: Path) -> TaxonomyLoadResult:
    """Idempotent: re-running with the same file is a no-op (matched by
    version string); loading a file with a bumped version string adds a
    new TaxonomyVersion + EventType rows without touching the old ones
    (taxonomy versions are immutable, like everything else here)."""
    raw_bytes = yaml_path.read_bytes()
    data: dict[str, Any] = yaml.safe_load(raw_bytes)
    version = str(data["version"])

    existing = session.scalar(select(TaxonomyVersion).where(TaxonomyVersion.version == version))
    if existing is not None:
        return TaxonomyLoadResult(version=version, event_types_loaded=0, was_new=False)

    taxonomy_version = TaxonomyVersion(
        version=version,
        source_file_hash=sha256_bytes(raw_bytes),
        description=data.get("notes"),
    )
    session.add(taxonomy_version)
    session.flush()

    count = 0
    for et in data["event_types"]:
        session.add(
            EventType(
                taxonomy_version_id=taxonomy_version.id,
                code=et["code"],
                name=et["name"],
                definition=et["definition"].strip(),
                required_fields=et.get("required_fields", []),
                optional_fields=et.get("optional_fields", []),
                severity_rules=et.get("severity_rules", []),
                detection_approach=et["detection_approach"],
                thresholds=et.get("thresholds", {}),
            )
        )
        count += 1
    session.commit()
    return TaxonomyLoadResult(version=version, event_types_loaded=count, was_new=True)


# --- PLEDGE_UP ---------------------------------------------------------------

PLEDGE_UP_MIN_INCREASE_PP = Decimal("5.0")
PLEDGE_UP_CROSSING_THRESHOLD_PCT = Decimal("50.0")


def pledge_up_triggers(old_pct: Decimal, new_pct: Decimal) -> bool:
    """taxonomy-v1.0.yaml PLEDGE_UP.thresholds.rule, as code.

    Trigger if the increase is >= 5.0 percentage points, OR the value
    crosses from below 50% to 50% or above. A company already above 50%
    that rises by less than 5pp does NOT re-trigger (see
    tests/test_taxonomy_thresholds.py for the exact boundary cases)."""
    increase = new_pct - old_pct
    crosses_upward = (
        old_pct < PLEDGE_UP_CROSSING_THRESHOLD_PCT and new_pct >= PLEDGE_UP_CROSSING_THRESHOLD_PCT
    )
    return increase >= PLEDGE_UP_MIN_INCREASE_PP or crosses_upward


# --- RESULT_DELAY ------------------------------------------------------------

ResultDelayPeriod = Literal["Q1", "Q2", "Q3", "Q4", "ANNUAL"]

RESULT_DELAY_QUARTERLY_DEADLINE_DAYS = 45
RESULT_DELAY_ANNUAL_DEADLINE_DAYS = 60


def result_delay_deadline(period: ResultDelayPeriod, period_end: dt.date) -> dt.date:
    """SEBI LODR Regulation 33(3)(a): Q1-Q3 within 45 days of quarter-end.
    Regulation 33(3)(d)/(e): annual results (and the last quarter's
    standalone figures, which ride with the annual filing) within 60
    days of financial-year-end -- there is NO separate 45-day deadline
    for Q4. Verified against SEBI's Master Circular
    SEBI/HO/CFD/PoD2/CIR/P/2023/120 -- see docs/knowledge/taxonomy.md."""
    days = (
        RESULT_DELAY_ANNUAL_DEADLINE_DAYS
        if period in ("Q4", "ANNUAL")
        else RESULT_DELAY_QUARTERLY_DEADLINE_DAYS
    )
    return period_end + dt.timedelta(days=days)


@dataclass
class ResultDelayOutcome:
    status: Literal["on_time", "delayed", "unverifiable"]
    delay_days: int | None
    deadline: dt.date | None


def result_delay_check(
    period: ResultDelayPeriod, period_end: dt.date, actual_filing_date: dt.date | None
) -> ResultDelayOutcome:
    """Never guesses: a missing actual_filing_date is `unverifiable`,
    never defaulted to on-time or delayed."""
    if actual_filing_date is None:
        return ResultDelayOutcome(status="unverifiable", delay_days=None, deadline=None)
    deadline = result_delay_deadline(period, period_end)
    delay = (actual_filing_date - deadline).days
    if delay > 0:
        return ResultDelayOutcome(status="delayed", delay_days=delay, deadline=deadline)
    return ResultDelayOutcome(status="on_time", delay_days=0, deadline=deadline)


# --- RPT_GROWTH ---------------------------------------------------------------

RPT_GROWTH_SHARE_INCREASE_PP = Decimal("5.0")
RPT_GROWTH_ABSOLUTE_MULTIPLE = Decimal("2.0")


def rpt_growth_triggers(
    *,
    rpt_amount: Decimal,
    previous_rpt_amount: Decimal,
    revenue: Decimal | None = None,
    previous_revenue: Decimal | None = None,
) -> bool:
    """taxonomy-v1.0.yaml RPT_GROWTH.thresholds.rule -- a documented,
    NOT empirically calibrated placeholder (see the YAML's rationale
    field and docs/knowledge/taxonomy.md)."""
    if previous_rpt_amount > 0 and rpt_amount >= previous_rpt_amount * RPT_GROWTH_ABSOLUTE_MULTIPLE:
        return True
    if (
        revenue is not None
        and previous_revenue is not None
        and previous_revenue > 0
        and revenue > 0
    ):
        share = (rpt_amount / revenue) * 100
        previous_share = (previous_rpt_amount / previous_revenue) * 100
        if share - previous_share >= RPT_GROWTH_SHARE_INCREASE_PP:
            return True
    return False


# --- AUDIT_QUAL ---------------------------------------------------------------

AuditOpinionType = Literal[
    "qualified", "adverse", "disclaimer", "emphasis_of_matter", "unqualified"
]

AUDIT_QUAL_QUALIFICATION_TYPES: frozenset[str] = frozenset({"qualified", "adverse", "disclaimer"})


def audit_qual_is_qualification(opinion_type: AuditOpinionType) -> bool:
    """emphasis_of_matter is explicitly excluded -- a distinct, lower-
    severity flag value, never counted as a qualification."""
    return opinion_type in AUDIT_QUAL_QUALIFICATION_TYPES


def audit_qual_severity(opinion_type: AuditOpinionType) -> Literal["low", "medium", "high"]:
    if opinion_type in ("adverse", "disclaimer"):
        return "high"
    if opinion_type == "qualified":
        return "medium"
    return "low"
