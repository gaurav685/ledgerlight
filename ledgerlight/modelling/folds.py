"""Real walk-forward evaluation folds for the PRIMARY outcome model
(Phase 3 brief §7), implementing the frozen methodology already
documented in `docs/modelling/evaluation-protocol.md`: expanding
window, yearly outer test folds, >= 12 month embargo between the
train cutoff and the test start so no training label's own 12-month
forward outcome window can overlap the test period it is evaluated
against.

Folds are built only from already-labeled (non-censored) rows --
`ledgerlight.modelling.dataset.build_primary_outcome_dataset` has
already decided censoring; this module must not re-derive it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.dates import add_months

HORIZON_MONTHS = 12
EMBARGO_MONTHS = 12


@dataclass
class Fold:
    test_year: int
    train_cutoff: dt.date  # train rows have as_of < this
    test_start: dt.date
    test_end: dt.date  # exclusive
    train_rows: list[DatasetRow]
    test_rows: list[DatasetRow]


def build_walk_forward_folds(rows: list[DatasetRow]) -> list[Fold]:
    """One outer fold per calendar year that has at least one labeled
    test row, using every labeled row (regardless of year) whose
    as_of precedes that fold's train cutoff as the training set. A
    fold with zero test rows is real and dropped rather than printed
    as a fabricated empty row -- the fold table only reports folds
    that actually test something.
    """
    labeled = [r for r in rows if not r.censored]
    if not labeled:
        return []

    years = sorted({r.as_of.year for r in labeled})
    folds: list[Fold] = []
    for test_year in years:
        test_start = dt.date(test_year, 1, 1)
        test_end = dt.date(test_year + 1, 1, 1)
        train_cutoff = add_months(test_start, -(HORIZON_MONTHS + EMBARGO_MONTHS))
        test_rows = [r for r in labeled if test_start <= r.as_of < test_end]
        if not test_rows:
            continue
        train_rows = [r for r in labeled if r.as_of < train_cutoff]
        folds.append(
            Fold(
                test_year=test_year,
                train_cutoff=train_cutoff,
                test_start=test_start,
                test_end=test_end,
                train_rows=train_rows,
                test_rows=test_rows,
            )
        )
    return folds


def print_fold_table(folds: list[Fold]) -> None:
    """Print the real fold table per §7: dates, companies,
    observations, positives -- for both the train and test side of
    each fold, so an empty or tiny train set is visible, not hidden."""
    header = (
        f"{'year':>6} {'train_cutoff':>12} {'test_start':>10} {'test_end':>10} "
        f"{'train_n':>8} {'train_co':>9} {'train_pos':>9} "
        f"{'test_n':>7} {'test_co':>8} {'test_pos':>8}"
    )
    print(header)
    for fold in folds:
        train_companies = len({r.company_id for r in fold.train_rows})
        test_companies = len({r.company_id for r in fold.test_rows})
        train_pos = sum(1 for r in fold.train_rows if r.label == 1)
        test_pos = sum(1 for r in fold.test_rows if r.label == 1)
        print(
            f"{fold.test_year:>6} {str(fold.train_cutoff):>12} {str(fold.test_start):>10} "
            f"{str(fold.test_end):>10} {len(fold.train_rows):>8} {train_companies:>9} "
            f"{train_pos:>9} {len(fold.test_rows):>7} {test_companies:>8} {test_pos:>8}"
        )
