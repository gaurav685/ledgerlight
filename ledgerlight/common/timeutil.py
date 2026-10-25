"""UTC time helpers. All timestamps in manifests and logs are UTC ISO-8601."""

from __future__ import annotations

import datetime as dt


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


_IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def ist_date_to_utc(date: dt.date) -> dt.datetime:
    """Convert a source-stated IST calendar date to UTC, at IST midnight.

    Every current Ledgerlight source is India-based and states dates with
    no explicit timezone — see docs/data/temporal-semantics.md. This is
    the one place that ambiguity is resolved, so no ingestion module has
    to get it right independently.
    """
    ist_midnight = dt.datetime(date.year, date.month, date.day, tzinfo=_IST)
    return ist_midnight.astimezone(dt.UTC)
