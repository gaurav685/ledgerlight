"""Tests for ledgerlight.agent.eval -- Phase 4 Sec8 evaluation.

`seed_track_company_ids`/`universe_track_company_ids` are read-only
(the project's usual rolled-back `db_session` fixture works fine).
`run_one`/`run_evaluation` call `run_investigation`, which commits
internally, so those use the same real, independent-session-with-
manual-cleanup pattern as `test_agent_state_machine.py`. A full real
15+15-company evaluation is too slow for a test suite -- these tests
exercise `run_one` directly and `run_evaluation` with its
`seed_company_ids`/`universe_company_ids` override, never the full
real selection.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from ledgerlight.agent.eval import (
    SEED_TRACK,
    UNIVERSE_TRACK,
    _percentile,
    compute_check_type_stats,
    run_evaluation,
    run_one,
    seed_track_company_ids,
    universe_track_company_ids,
)
from ledgerlight.ingestion.seed_track import SEED_COMPANY_SEARCH_NAMES
from ledgerlight.knowledge.models import Company

pytestmark = pytest.mark.integration


# --- seed_track_company_ids / universe_track_company_ids (read-only) ---------


def test_seed_track_company_ids_resolves_the_real_15_companies(db_session: Session) -> None:
    resolved = seed_track_company_ids(db_session)
    expected_symbols = {
        identifiers.nse_symbol
        for _name, identifiers in SEED_COMPANY_SEARCH_NAMES
        if identifiers.nse_symbol
    }
    assert set(resolved.values()) <= expected_symbols
    assert len(resolved) > 0


def test_universe_track_company_ids_never_overlaps_seed(db_session: Session) -> None:
    seed_ids = set(seed_track_company_ids(db_session))
    universe_ids = universe_track_company_ids(db_session)
    assert seed_ids.isdisjoint(universe_ids)


def test_universe_track_company_ids_respects_requested_total(db_session: Session) -> None:
    universe_ids = universe_track_company_ids(db_session, event_company_count=3, total=5)
    assert len(universe_ids) <= 5


# --- _percentile (pure) --------------------------------------------------------


def test_percentile_of_empty_list_is_zero() -> None:
    assert _percentile([], 0.5) == 0.0


def test_percentile_of_single_value_is_that_value() -> None:
    assert _percentile([3.0], 0.95) == 3.0


def test_percentile_p50_of_an_odd_sorted_list() -> None:
    assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0


def test_percentile_p95_interpolates() -> None:
    values = [float(v) for v in range(1, 11)]  # 1..10
    result = _percentile(values, 0.95)
    assert 9.0 <= result <= 10.0


# --- run_one / run_evaluation (real commits) -----------------------------------


@pytest.fixture
def real_session() -> Iterator[Session]:
    from pathlib import Path

    from sqlalchemy import text

    from ledgerlight.config.settings import Settings
    from ledgerlight.db.session import make_session_factory

    repo_root = Path(__file__).resolve().parent.parent
    try:
        settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    except Exception as exc:
        pytest.skip(f"could not load real .env for integration test: {exc}")

    session_factory = make_session_factory(settings)
    try:
        session = session_factory()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable (is the Docker stack up?): {exc}")

    created_company_ids: list[uuid.UUID] = []
    session.info["created_company_ids"] = created_company_ids
    try:
        yield session
    finally:
        if created_company_ids:
            session.execute(
                text(
                    "DELETE FROM review_decisions_audit WHERE review_task_id IN "
                    "(SELECT id FROM review_tasks WHERE dossier_id IN "
                    "(SELECT id FROM dossiers WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))))"
                ),
                {"ids": created_company_ids},
            )
            session.execute(
                text(
                    "DELETE FROM review_tasks WHERE dossier_id IN "
                    "(SELECT id FROM dossiers WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids)))"
                ),
                {"ids": created_company_ids},
            )
            session.execute(
                text(
                    "DELETE FROM dossiers WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
                ),
                {"ids": created_company_ids},
            )
            session.execute(
                text(
                    "DELETE FROM claims WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
                ),
                {"ids": created_company_ids},
            )
            session.execute(
                text(
                    "DELETE FROM investigation_steps WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
                ),
                {"ids": created_company_ids},
            )
            session.execute(
                text("DELETE FROM investigations WHERE company_id = ANY(:ids)"),
                {"ids": created_company_ids},
            )
            session.execute(
                text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": created_company_ids}
            )
            session.commit()
        session.close()


def _make_company(session: Session, name: str) -> uuid.UUID:
    company = Company(id=uuid.uuid4(), display_name=name)
    session.add(company)
    session.commit()
    session.info["created_company_ids"].append(company.id)
    return company.id


def test_run_one_on_a_fresh_company_finalises_with_no_leak(real_session: Session) -> None:
    company_id = _make_company(real_session, "Eval Fresh Co")
    result = run_one(real_session, company_id, SEED_TRACK, dt.date(2020, 1, 1))
    assert result.final_status == "FINALISED"
    assert result.unsupported_claim_leaked is False
    assert result.claim_count > 0  # standing limitations + the disclaimer, at minimum
    assert result.claims_removed_in_repair == 0


def test_run_evaluation_with_an_explicit_small_override_aggregates_correctly(
    real_session: Session,
) -> None:
    seed_company = _make_company(real_session, "Eval Override Seed Co")
    universe_company = _make_company(real_session, "Eval Override Universe Co")

    report = run_evaluation(
        real_session,
        as_of_dates=(dt.date(2020, 1, 1),),
        seed_company_ids=[seed_company],
        universe_company_ids=[universe_company],
    )

    assert len(report.results) == 2
    assert report.status_breakdown.get(f"{SEED_TRACK}:FINALISED") == 1
    assert report.status_breakdown.get(f"{UNIVERSE_TRACK}:FINALISED") == 1
    assert report.unsupported_claim_leaks == []
    assert report.runtime_p50 >= 0.0
    assert any(stat.total > 0 for stat in report.check_type_stats)


def test_compute_check_type_stats_aggregates_across_investigations(real_session: Session) -> None:
    company_a = _make_company(real_session, "Eval Check Stats Co A")
    company_b = _make_company(real_session, "Eval Check Stats Co B")
    result_a = run_one(real_session, company_a, SEED_TRACK, dt.date(2020, 1, 1))
    result_b = run_one(real_session, company_b, UNIVERSE_TRACK, dt.date(2020, 1, 1))

    stats = compute_check_type_stats(
        real_session, [result_a.investigation_id, result_b.investigation_id]
    )
    assert len(stats) > 0
    for stat in stats:
        assert stat.total >= 2  # both fresh companies share the same standing claims
        assert 0.0 <= stat.pass_rate <= 1.0


def test_compute_check_type_stats_with_no_investigations_is_empty(db_session: Session) -> None:
    assert compute_check_type_stats(db_session, []) == []
