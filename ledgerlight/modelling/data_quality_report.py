"""Sec7's own data-quality report (distinct from the standing
`docs/modelling/data-quality.md`): real missingness by feature and
year, computed from the real feature values already attached to every
`DatasetRow` -- including censored rows, so missingness reflects real
snapshot coverage, not just the labeled subset. Entity-link
exclusions and bhavcopy gaps are not recomputed here; they are already
real, evidenced numbers in `docs/modelling/data-quality.md` and
`docs/phase-3/evidence/link-filings-run-post-sec3-broadening.log`, and
the final report cites those directly.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ledgerlight.modelling.dataset import DatasetRow


@dataclass
class MissingnessReport:
    # feature name -> year -> real fraction of rows missing that feature
    by_feature_and_year: dict[str, dict[int, float]] = field(default_factory=dict)


def compute_missingness_by_feature_and_year(
    rows: list[DatasetRow], feature_names: list[str]
) -> MissingnessReport:
    counts: dict[str, dict[int, list[int]]] = {
        name: defaultdict(lambda: [0, 0]) for name in feature_names
    }
    for row in rows:
        year = row.as_of.year
        for name in feature_names:
            bucket = counts[name][year]
            bucket[1] += 1
            if row.features.get(name) is not None:
                bucket[0] += 1

    by_feature_and_year: dict[str, dict[int, float]] = {}
    for name, years in counts.items():
        by_feature_and_year[name] = {
            year: 1.0 - (present / total) for year, (present, total) in sorted(years.items())
        }
    return MissingnessReport(by_feature_and_year=by_feature_and_year)


def print_missingness_report(report: MissingnessReport) -> None:
    for name, by_year in report.by_feature_and_year.items():
        formatted = ", ".join(f"{year}={fraction:.2f}" for year, fraction in by_year.items())
        print(f"{name}: {formatted}")
