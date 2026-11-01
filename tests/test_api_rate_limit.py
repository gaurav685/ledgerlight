"""Tests for ledgerlight.api.rate_limit -- Phase 5 §3/§9. Real commits
(check_and_increment runs its own, independent, immediately-committed
transaction), so this uses the same real, independent-session pattern
as every other committing function in this project, never the
rolled-back `db_session` fixture (which has no `.connect()` of its
own -- see the module's own docstring for why).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.api.models import Tenant
from ledgerlight.api.rate_limit import RateLimitExceeded, check_and_increment
from ledgerlight.config.settings import Settings
from ledgerlight.db.session import make_session_factory

pytestmark = pytest.mark.integration


@pytest.fixture
def real_session() -> Iterator[Session]:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    try:
        settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    except Exception as exc:
        pytest.skip(f"could not load real .env for integration test: {exc}")

    try:
        session = make_session_factory(settings)()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable (is the Docker stack up?): {exc}")

    created_keys: list[str] = []
    session.info["created_keys"] = created_keys
    try:
        yield session
    finally:
        if created_keys:
            session.execute(
                text("DELETE FROM rate_limit_counters WHERE key = ANY(:keys)"),
                {"keys": created_keys},
            )
            session.commit()
        session.close()


def _unique_key(real_session: Session, prefix: str) -> str:
    key = f"{prefix}:{uuid.uuid4().hex}"
    real_session.info["created_keys"].append(key)
    return key


def test_allows_requests_under_the_limit(real_session: Session) -> None:
    key = _unique_key(real_session, "test-under-limit")
    for _ in range(3):
        check_and_increment(real_session, key, limit=3, window=dt.timedelta(seconds=5))


def test_raises_once_the_limit_is_reached(real_session: Session) -> None:
    key = _unique_key(real_session, "test-trips")
    for _ in range(3):
        check_and_increment(real_session, key, limit=3, window=dt.timedelta(seconds=5))
    with pytest.raises(RateLimitExceeded) as exc_info:
        check_and_increment(real_session, key, limit=3, window=dt.timedelta(seconds=5))
    assert exc_info.value.retry_after_seconds > 0


def test_resets_after_the_window_elapses(real_session: Session) -> None:
    """A real 50ms window was flaky here: two separate real DB
    round-trips (`check_and_increment` opens its own connection each
    call) can occasionally be more than 50ms apart on their own,
    making the window already look elapsed before the second call --
    not a real product bug, just too tight a margin for real network/
    connection-pool latency. A 1-second window leaves ample real
    margin for that; the test still proves the real reset behaviour,
    just with a real `time.sleep` long enough to be deterministic."""
    key = _unique_key(real_session, "test-window-reset")
    window = dt.timedelta(seconds=1)
    check_and_increment(real_session, key, limit=1, window=window)
    with pytest.raises(RateLimitExceeded):
        check_and_increment(real_session, key, limit=1, window=window)

    import time

    time.sleep(1.2)
    check_and_increment(real_session, key, limit=1, window=window)


def test_different_keys_are_independent(real_session: Session) -> None:
    key_a = _unique_key(real_session, "test-independent-a")
    key_b = _unique_key(real_session, "test-independent-b")
    check_and_increment(real_session, key_a, limit=1, window=dt.timedelta(seconds=5))
    with pytest.raises(RateLimitExceeded):
        check_and_increment(real_session, key_a, limit=1, window=dt.timedelta(seconds=5))
    # key_b has its own real, independent counter -- unaffected by key_a's.
    check_and_increment(real_session, key_b, limit=1, window=dt.timedelta(seconds=5))


def test_does_not_commit_the_callers_own_pending_work(real_session: Session) -> None:
    """A real, documented property: check_and_increment runs in its
    own, separate connection/transaction -- it must never prematurely
    commit whatever else the caller's own session was in the middle
    of doing."""
    key = _unique_key(real_session, "test-isolation")
    tenant = Tenant(name="RL Isolation Check", slug=f"rl-isolation-{uuid.uuid4().hex[:8]}")
    real_session.add(tenant)

    check_and_increment(real_session, key, limit=5, window=dt.timedelta(seconds=5))

    real_session.rollback()
    still_there = real_session.execute(
        text("SELECT count(*) FROM tenants WHERE slug = :slug"), {"slug": tenant.slug}
    ).scalar()
    assert still_there == 0
