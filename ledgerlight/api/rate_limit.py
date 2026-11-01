"""Phase 5 §3: real, Postgres-backed fixed-window rate limiting. See
`docs/adr/0010-rate-limiting.md` for why Postgres-backed rather than
in-process, and the real limitation that choice carries.
"""

from __future__ import annotations

import datetime as dt
from typing import cast

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session as DbSession


class RateLimitExceeded(Exception):
    """Carries the real `retry_after_seconds` the caller should put in
    a real `Retry-After` response header."""

    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limit exceeded, retry after {retry_after_seconds:.1f}s")


def check_and_increment(
    db: DbSession,
    key: str,
    limit: int,
    window: dt.timedelta,
) -> None:
    """One real, atomic fixed-window check-and-increment. `key`
    already encodes whatever real scope is being limited (e.g.
    `f"user:{user_id}"`, `f"api_key:{key_id}"`, `f"ip:{ip}"`) --
    this function itself is scope-agnostic.

    The real UPSERT below is atomic per row (Postgres's own
    `ON CONFLICT DO UPDATE` guarantee): concurrent requests racing on
    the same real key cannot both read a stale count and both decide
    they're under the limit -- each commits its own real increment
    before the next one can read it. Raises `RateLimitExceeded` (never
    silently drops the request) once a real window's count reaches
    `limit`.

    Runs in its OWN, immediately-committed connection/transaction --
    never `db`'s own request-scoped transaction. A rate-limit
    increment must count a real attempt regardless of whether the
    rest of the request later fails and rolls back (otherwise a
    client could probe indefinitely via requests that fail for an
    unrelated reason, never actually tripping the limit); calling
    `db.commit()` directly on the shared per-request session here
    would also prematurely commit everything else that request has
    done so far, which is never this function's call to make."""
    now = dt.datetime.now(dt.UTC)
    window_cutoff = now - window
    # Always called with an Engine-bound session (the real per-request
    # app-role session, or a real test session built the same way) --
    # never a Connection-bound one (the project's rolled-back `db_session`
    # test fixture), which has no `.connect()` of its own to open a real,
    # independent transaction from.
    engine = cast(Engine, db.get_bind())
    with engine.connect() as conn, conn.begin():
        row = conn.execute(
            text(
                """
                INSERT INTO rate_limit_counters (key, window_start, count)
                VALUES (:key, :now, 1)
                ON CONFLICT (key) DO UPDATE SET
                    count = CASE
                        WHEN rate_limit_counters.window_start <= :window_cutoff THEN 1
                        ELSE rate_limit_counters.count + 1
                    END,
                    window_start = CASE
                        WHEN rate_limit_counters.window_start <= :window_cutoff THEN :now
                        ELSE rate_limit_counters.window_start
                    END
                RETURNING count, window_start
                """
            ),
            {"key": key, "now": now, "window_cutoff": window_cutoff},
        ).one()
    count = cast(int, row[0])
    window_start = cast(dt.datetime, row[1])
    if count > limit:
        retry_after = (window_start + window - now).total_seconds()
        raise RateLimitExceeded(max(retry_after, 0.0))
