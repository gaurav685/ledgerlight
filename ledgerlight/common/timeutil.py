"""UTC time helpers. All timestamps in manifests and logs are UTC ISO-8601."""

from __future__ import annotations

import datetime as dt


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()
