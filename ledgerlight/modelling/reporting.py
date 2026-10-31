"""Honest positive-counting and uncertainty reporting for the PRIMARY
outcome model (Phase 3 brief §7, and the user's explicit condition
2026-10-31): company-month rows inflate apparent positive counts,
since one real outcome event makes every as_of in its 12-month
lookback window positive for that company. Every report here prints
DISTINCT outcome events and DISTINCT companies alongside the raw
company-month counts, never only the row count, and every interval is
a company-clustered bootstrap so repeated monthly rows from the same
company are not treated as independent evidence.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ledgerlight.modelling.dataset import DatasetRow

DEFAULT_BOOTSTRAP_ITERATIONS = 2000
INCONCLUSIVE_POSITIVE_FLOOR = 30


@dataclass
class PositiveCounts:
    company_month_rows: int
    distinct_positive_companies: int
    distinct_positive_events: int
    is_inconclusive: bool


def count_positives(rows: list[DatasetRow]) -> PositiveCounts:
    """Real counts for a pool of (already non-censored) rows -- never
    estimated, always a direct count over what was actually passed
    in. `rows` may be a fold's rows or the full pooled dataset; the
    caller decides which, and this function reports on exactly that
    slice."""
    positive_rows = [r for r in rows if not r.censored and r.label == 1]
    company_month_rows = len(positive_rows)
    distinct_positive_companies = len({r.company_id for r in positive_rows})
    distinct_events: set[tuple[uuid.UUID, dt.datetime | None]] = {
        (r.company_id, r.triggering_event_time) for r in positive_rows
    }
    distinct_positive_events = len(distinct_events)
    return PositiveCounts(
        company_month_rows=company_month_rows,
        distinct_positive_companies=distinct_positive_companies,
        distinct_positive_events=distinct_positive_events,
        is_inconclusive=distinct_positive_events < INCONCLUSIVE_POSITIVE_FLOOR,
    )


def print_positive_counts(label: str, rows: list[DatasetRow]) -> PositiveCounts:
    counts = count_positives(rows)
    print(
        f"{label}: company-month rows={counts.company_month_rows} "
        f"distinct positive companies={counts.distinct_positive_companies} "
        f"distinct positive events={counts.distinct_positive_events} "
        f"{'INCONCLUSIVE (< 30 distinct events)' if counts.is_inconclusive else ''}"
    )
    return counts


def company_clustered_bootstrap(
    rows: list[DatasetRow],
    statistic: Callable[[list[DatasetRow]], float],
    *,
    n_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    seed: int = 0,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Company-clustered bootstrap 95% interval (per §7's explicit
    requirement) for any `statistic` computed over a list of
    DatasetRow. Resamples whole companies with replacement (not
    individual rows), so one company's correlated monthly
    observations never get treated as independent draws. Returns
    (point_estimate, lower, upper); point_estimate is the real
    statistic on the full, unresampled `rows`.
    """
    point_estimate = statistic(rows)
    company_ids = sorted({r.company_id for r in rows}, key=str)
    if len(company_ids) < 2:
        # A single company has no real resampling variance to offer;
        # report the point estimate with a degenerate (equal) interval
        # rather than a fabricated one.
        return point_estimate, point_estimate, point_estimate

    by_company: dict[uuid.UUID, list[DatasetRow]] = {}
    for r in rows:
        by_company.setdefault(r.company_id, []).append(r)

    rng = np.random.default_rng(seed)
    n_companies = len(company_ids)
    samples: list[float] = []
    for _ in range(n_iterations):
        chosen = rng.choice(np.array(company_ids, dtype=object), size=n_companies, replace=True)
        resampled: list[DatasetRow] = []
        for company_id in chosen:
            resampled.extend(by_company[company_id])
        samples.append(statistic(resampled))

    alpha = 1 - confidence
    lower = float(np.quantile(samples, alpha / 2))
    upper = float(np.quantile(samples, 1 - alpha / 2))
    return point_estimate, lower, upper
