"""Lenient parsing of the free-form `publication_time` strings recorded in
Phase 0/Correction-1 manifests (e.g. "2025-04-15", "2019-09", "2019").

Only used to populate the informational `published_at` column — it is
never trusted blindly for `known_at` (see
ledgerlight.db.temporal.compute_known_at and
docs/data/temporal-semantics.md), so a day-level or month-level guess here
cannot create a look-ahead-bias bug: unreliable sources' published_at is
ignored by the known_at rule regardless of how it was parsed.
"""

from __future__ import annotations

import datetime as dt
import re

from ledgerlight.common.timeutil import ist_date_to_utc

_FULL_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_YEAR_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_YEAR_ONLY = re.compile(r"^(\d{4})$")


def parse_publication_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    value = value.strip()

    m = _FULL_DATE.match(value)
    if m:
        year, month, day = (int(g) for g in m.groups())
        return ist_date_to_utc(dt.date(year, month, day))

    m = _YEAR_MONTH.match(value)
    if m:
        year, month = (int(g) for g in m.groups())
        return ist_date_to_utc(dt.date(year, month, 1))

    m = _YEAR_ONLY.match(value)
    if m:
        return ist_date_to_utc(dt.date(int(m.group(1)), 1, 1))

    return None
