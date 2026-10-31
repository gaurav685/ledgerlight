"""Shared real calendar-month arithmetic used by censoring, fold
construction and inner-validation splitting -- one implementation so
the day-clamping rule for short months stays identical everywhere it
matters for point-in-time correctness."""

from __future__ import annotations

import datetime as dt


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
