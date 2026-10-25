"""NSE bhavcopy URL construction for archives.nseindia.com.

Extracted from scripts/acquire_seed.py (Phase 0/Correction 1) in Phase 1
so the live ingestion job (ledgerlight.ingestion.nse_bhavcopy) and the
original seed script share one implementation instead of two copies
drifting apart — the exact URL format matters (it was reverse-engineered
from real responses; see docs/data/source-inventory.md), so there must be
only one place that knows it. acquire_seed.py is updated to import this
rather than defining it inline; its own behaviour is unchanged.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

UDIFF_CUTOVER = dt.date(2024, 7, 8)


def bhavcopy_url_for_date(date: dt.date) -> str:
    if date < UDIFF_CUTOVER:
        mon = date.strftime("%b").upper()
        return (
            f"https://archives.nseindia.com/content/historical/EQUITIES/"
            f"{date.year}/{mon}/cm{date.day:02d}{mon}{date.year}bhav.csv.zip"
        )
    return f"https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date.strftime('%Y%m%d')}_F_0000.csv.zip"


def business_days(start: dt.date, end: dt.date) -> Iterator[dt.date]:
    """Mon-Fri dates in [start, end] inclusive. NSE holidays within that
    range are not excluded here — they simply 404 at fetch time, which the
    caller treats as a normal skip, not an error (see
    ledgerlight.ingestion.nse_bhavcopy)."""
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += dt.timedelta(days=1)
