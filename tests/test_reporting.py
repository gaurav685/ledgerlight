"""Tests for ledgerlight.modelling.reporting -- the user's explicit
condition (2026-10-31) that positives are reported as DISTINCT
outcome events and DISTINCT companies, never only company-month rows,
and that all intervals use a company-clustered bootstrap."""

from __future__ import annotations

import datetime as dt
import uuid

from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.reporting import company_clustered_bootstrap, count_positives

COMPANY_A = uuid.uuid4()
COMPANY_B = uuid.uuid4()


def _row(
    company_id: uuid.UUID,
    as_of: dt.date,
    label: int,
    event_time: dt.datetime | None = None,
) -> DatasetRow:
    return DatasetRow(
        company_id=company_id,
        company_name=str(company_id),
        as_of=as_of,
        features={},
        label=label,
        censored=False,
        censor_reason=None,
        triggering_event_time=event_time,
    )


def test_one_real_event_inflates_many_company_month_rows_but_counts_as_one_event() -> None:
    """A single real event observed from 12 consecutive monthly as_of
    rows must report 12 company-month rows but exactly 1 distinct
    event and 1 distinct company -- this is the exact inflation the
    user's condition targets."""
    event_time = dt.datetime(2020, 6, 15)
    as_of_dates = [dt.date(2019 + (6 + i) // 12, (6 + i) % 12 + 1, 28) for i in range(12)]
    rows = [_row(COMPANY_A, as_of, 1, event_time) for as_of in as_of_dates]
    counts = count_positives(rows)
    assert counts.company_month_rows == 12
    assert counts.distinct_positive_companies == 1
    assert counts.distinct_positive_events == 1


def test_distinct_events_counted_separately_per_company() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2019, 1, 31), 1, dt.datetime(2019, 2, 1)),
        _row(COMPANY_A, dt.date(2020, 1, 31), 1, dt.datetime(2020, 2, 1)),
        _row(COMPANY_B, dt.date(2021, 1, 31), 1, dt.datetime(2021, 2, 1)),
    ]
    counts = count_positives(rows)
    assert counts.distinct_positive_companies == 2
    assert counts.distinct_positive_events == 3


def test_below_30_distinct_events_is_marked_inconclusive() -> None:
    rows = [_row(COMPANY_A, dt.date(2019, 1, 31), 1, dt.datetime(2019, 2, 1))]
    counts = count_positives(rows)
    assert counts.is_inconclusive is True


def test_negative_rows_never_counted_as_positive() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2019, 1, 31), 0),
        _row(COMPANY_A, dt.date(2020, 1, 31), 1, dt.datetime(2020, 2, 1)),
    ]
    counts = count_positives(rows)
    assert counts.company_month_rows == 1
    assert counts.distinct_positive_events == 1


def test_single_company_bootstrap_returns_degenerate_point_interval() -> None:
    """With only one company in the pool, there is no real
    between-company resampling variance -- the interval must equal
    the point estimate exactly, not a fabricated spread."""
    rows = [_row(COMPANY_A, dt.date(2019, 1, 31), 1), _row(COMPANY_A, dt.date(2020, 1, 31), 0)]
    point, lower, upper = company_clustered_bootstrap(rows, lambda rs: sum(r.label for r in rs))
    assert point == lower == upper


def test_bootstrap_resamples_whole_companies_not_individual_rows() -> None:
    """Every bootstrap resample must be built only from intact
    per-company row groups -- i.e. every row for a chosen company id
    is pulled in together, never split."""
    rows = [
        _row(COMPANY_A, dt.date(2019, 1, 31), 1),
        _row(COMPANY_A, dt.date(2019, 2, 28), 1),
        _row(COMPANY_B, dt.date(2019, 1, 31), 0),
    ]

    def statistic(rs: list[DatasetRow]) -> float:
        company_ids = {r.company_id for r in rs}
        for cid in company_ids:
            count = sum(1 for r in rs if r.company_id == cid)
            original_count = sum(1 for r in rows if r.company_id == cid)
            assert count % original_count == 0
        return float(len(rs))

    company_clustered_bootstrap(rows, statistic, n_iterations=50)


def test_point_estimate_is_computed_on_the_real_unresampled_rows() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2019, 1, 31), 1),
        _row(COMPANY_B, dt.date(2019, 1, 31), 0),
    ]
    point, _lower, _upper = company_clustered_bootstrap(rows, lambda rs: sum(r.label for r in rs))
    assert point == 1
