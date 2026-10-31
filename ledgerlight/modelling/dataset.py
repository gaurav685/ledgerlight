"""Real labeled dataset for the PRIMARY outcome model (§6), restricted
to the verified-coverage universe (§7 condition 1, user 2026-10-31):
only the real companies with both IBBI and CARE Filing coverage, only
`as_of` months whose full [as_of, as_of+12mo) forward window falls
inside the real verified coverage window.

Every row carries its own censoring status explicitly -- a censored
row's label is `None`, never a fabricated 0 or 1. Features come only
from the STRUCTURED (`price-liquidity-1.0`) and RULE_VERIFIED
(`rule-verified-1.0`) tiers, enforced by
`ledgerlight.modelling.feature_policy.assert_primary_model_feature_policy`
before this module ever runs.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.modelling.censoring import check_censoring
from ledgerlight.modelling.coverage import VerifiedCoverage, compute_verified_coverage
from ledgerlight.modelling.feature_policy import assert_primary_model_feature_policy

PRIMARY_FEATURE_SET_VERSIONS = ["price-liquidity-1.0", "rule-verified-1.0"]
PRIMARY_OUTCOME_TYPES = ["PRIMARY_IBBI_ADMISSION", "PRIMARY_RATING_DOWNGRADE_D"]


@dataclass
class DatasetRow:
    company_id: uuid.UUID
    company_name: str
    as_of: dt.date
    features: dict[str, float | None]
    label: int | None  # None iff censored
    censored: bool
    censor_reason: str | None
    triggering_outcome_types: list[str] = field(default_factory=list)
    triggering_event_time: dt.datetime | None = None


def load_primary_outcome_events(
    session: Session, company_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[dt.datetime, str]]]:
    rows = session.execute(
        text(
            """
            SELECT e.company_id, e.event_time, o.outcome_type
            FROM outcomes o JOIN events e ON e.id = o.event_id
            WHERE o.outcome_type = ANY(:types) AND e.company_id = ANY(:ids)
            ORDER BY e.company_id, e.event_time
            """
        ),
        {"types": PRIMARY_OUTCOME_TYPES, "ids": company_ids},
    ).all()
    events: dict[uuid.UUID, list[tuple[dt.datetime, str]]] = {}
    for row in rows:
        company_id = cast(uuid.UUID, row[0])
        event_time = cast(dt.datetime, row[1])
        outcome_type = cast(str, row[2])
        events.setdefault(company_id, []).append((event_time, outcome_type))
    return events


def load_last_real_trade_dates(
    session: Session, company_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dt.date]:
    rows = session.execute(
        text(
            """
            SELECT ci.company_id, max(pb.trade_date)
            FROM price_bars pb
            JOIN company_identifiers ci ON ci.identifier_type = 'NSE_SYMBOL'
              AND ci.value = pb.symbol
              AND pb.trade_date >= ci.valid_from
              AND (ci.valid_to IS NULL OR pb.trade_date <= ci.valid_to)
            WHERE pb.series = 'EQ' AND ci.company_id = ANY(:ids)
            GROUP BY ci.company_id
            """
        ),
        {"ids": company_ids},
    ).all()
    return {cast(uuid.UUID, row[0]): cast(dt.date, row[1]) for row in rows}


def load_feature_rows(
    session: Session, company_ids: list[uuid.UUID]
) -> dict[tuple[uuid.UUID, dt.date], dict[str, float | None]]:
    assert_primary_model_feature_policy(PRIMARY_FEATURE_SET_VERSIONS, session)
    rows = session.execute(
        text(
            """
            SELECT company_id, as_of, values FROM feature_snapshots
            WHERE feature_set_version = ANY(:versions) AND company_id = ANY(:ids)
            """
        ),
        {"versions": PRIMARY_FEATURE_SET_VERSIONS, "ids": company_ids},
    ).all()
    merged: dict[tuple[uuid.UUID, dt.date], dict[str, float | None]] = {}
    for row in rows:
        company_id = cast(uuid.UUID, row[0])
        as_of = cast(dt.date, row[1])
        values = cast("dict[str, float | None]", row[2])
        merged.setdefault((company_id, as_of), {}).update(values)
    return merged


def _label_for_window(
    events: list[tuple[dt.datetime, str]], as_of: dt.date, window_end: dt.date
) -> tuple[int, list[str], dt.datetime | None]:
    triggering = [
        (event_time, outcome_type)
        for event_time, outcome_type in events
        if as_of <= event_time.date() < window_end
    ]
    if not triggering:
        return 0, [], None
    triggering.sort(key=lambda t: t[0])
    return 1, [t[1] for t in triggering], triggering[0][0]


def build_primary_outcome_dataset(
    session: Session, coverage: VerifiedCoverage | None = None
) -> list[DatasetRow]:
    """The real, restricted dataset. `coverage` can be passed in (e.g.
    already computed once by a caller that also wants to print it);
    computed fresh here if omitted."""
    if coverage is None:
        coverage = compute_verified_coverage(session)

    data_coverage_end = session.execute(
        text("SELECT max(trade_date) FROM price_bars WHERE series = 'EQ'")
    ).scalar()
    assert data_coverage_end is not None

    events_by_company = load_primary_outcome_events(session, coverage.company_ids)
    last_trade_by_company = load_last_real_trade_dates(session, coverage.company_ids)
    features_by_key = load_feature_rows(session, coverage.company_ids)

    def add_months(d: dt.date, months: int) -> dt.date:
        month_index = d.month - 1 + months
        year = d.year + month_index // 12
        month = month_index % 12 + 1
        day = d.day
        while True:
            try:
                return dt.date(year, month, day)
            except ValueError:
                day -= 1

    rows: list[DatasetRow] = []
    for idx, company_id in enumerate(coverage.company_ids):
        company_name = coverage.company_names[idx]
        as_of_dates = sorted({key[1] for key in features_by_key if key[0] == company_id})
        events = events_by_company.get(company_id, [])
        last_trade = last_trade_by_company.get(company_id)

        for as_of in as_of_dates:
            window_end = add_months(as_of, 12)
            censoring = check_censoring(
                as_of,
                last_real_trade_date=last_trade,
                data_coverage_end=data_coverage_end,
                verified_coverage_window=(coverage.window_start, coverage.window_end),
            )
            features = features_by_key.get((company_id, as_of), {})

            if censoring.censored:
                rows.append(
                    DatasetRow(
                        company_id=company_id,
                        company_name=company_name,
                        as_of=as_of,
                        features=features,
                        label=None,
                        censored=True,
                        censor_reason=censoring.reason,
                    )
                )
                continue

            label, triggering_types, triggering_time = _label_for_window(events, as_of, window_end)
            rows.append(
                DatasetRow(
                    company_id=company_id,
                    company_name=company_name,
                    as_of=as_of,
                    features=features,
                    label=label,
                    censored=False,
                    censor_reason=None,
                    triggering_outcome_types=triggering_types,
                    triggering_event_time=triggering_time,
                )
            )
    return rows
