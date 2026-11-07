"""Tests for ledgerlight.agent.state_machine -- Phase 4 Sec4.

`run_investigation` commits internally (real steps must be durably
checkpointed for genuine crash-resume, not just flushed -- the same
lesson Phase 3 learned from scripts/process.py's single-transaction
risk). That makes the project's usual `db_session` fixture (which
wraps a test in one outer transaction, rolled back at teardown)
unusable here: an internal commit would commit that outer transaction
too. These tests instead use a real, independent session via the
production `make_session_factory`, and explicitly clean up every real
row they create afterward.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.agent.budgets import BudgetConfig
from ledgerlight.agent.models import Claim, Dossier, Investigation, InvestigationStep
from ledgerlight.agent.state_machine import run_investigation
from ledgerlight.agent.tools import get_timeline
from ledgerlight.knowledge.models import Company

pytestmark = pytest.mark.integration


@pytest.fixture
def real_session() -> Iterator[Session]:
    from pathlib import Path

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
        _cleanup(session, created_company_ids)
        session.close()


def _cleanup(session: Session, company_ids: list[uuid.UUID]) -> None:
    if not company_ids:
        return
    session.execute(
        text(
            "DELETE FROM review_decisions_audit WHERE review_task_id IN "
            "(SELECT id FROM review_tasks WHERE dossier_id IN "
            "(SELECT id FROM dossiers WHERE investigation_id IN "
            "(SELECT id FROM investigations WHERE company_id = ANY(:ids))))"
        ),
        {"ids": company_ids},
    )
    session.execute(
        text(
            "DELETE FROM review_tasks WHERE dossier_id IN "
            "(SELECT id FROM dossiers WHERE investigation_id IN "
            "(SELECT id FROM investigations WHERE company_id = ANY(:ids)))"
        ),
        {"ids": company_ids},
    )
    session.execute(
        text(
            "DELETE FROM dossiers WHERE investigation_id IN "
            "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
        ),
        {"ids": company_ids},
    )
    session.execute(
        text(
            "DELETE FROM claims WHERE investigation_id IN "
            "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
        ),
        {"ids": company_ids},
    )
    session.execute(
        text(
            "DELETE FROM investigation_steps WHERE investigation_id IN "
            "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
        ),
        {"ids": company_ids},
    )
    session.execute(
        text("DELETE FROM investigations WHERE company_id = ANY(:ids)"), {"ids": company_ids}
    )
    session.execute(text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": company_ids})
    session.commit()


def _make_company(session: Session, name: str) -> uuid.UUID:
    company = Company(id=uuid.uuid4(), display_name=name)
    session.add(company)
    session.commit()
    session.info["created_company_ids"].append(company.id)
    return company.id


def test_run_investigation_finalises_a_fresh_company_with_no_data(real_session: Session) -> None:
    """A fresh company with no real events/filings/ratings produces
    only the standing limitation claims + a 'no score' risk_signal --
    all of which should verify cleanly and reach FINALISED."""
    company_id = _make_company(real_session, "State Machine Fresh Co")
    outcome = run_investigation(
        real_session, company_id, dt.date(2020, 1, 1), "test", BudgetConfig()
    )
    assert outcome.investigation.final_status == "FINALISED"
    assert outcome.investigation.state == "FINALISE"
    assert outcome.rendered is not None
    assert "disclaimer" in outcome.rendered.sections


def test_run_investigation_needs_review_on_budget_exceeded(real_session: Session) -> None:
    company_id = _make_company(real_session, "State Machine Budget Co")
    outcome = run_investigation(
        real_session,
        company_id,
        dt.date(2020, 1, 1),
        "test",
        BudgetConfig(max_steps=1),
    )
    assert outcome.investigation.final_status == "NEEDS_REVIEW"
    assert outcome.investigation.failure_reason is not None
    assert "budget_exceeded" in outcome.investigation.failure_reason


def test_run_investigation_persists_a_dossier_even_on_needs_review(real_session: Session) -> None:
    company_id = _make_company(real_session, "State Machine Dossier Co")
    outcome = run_investigation(
        real_session, company_id, dt.date(2020, 1, 1), "test", BudgetConfig(max_steps=1)
    )
    dossier = real_session.query(Dossier).filter_by(investigation_id=outcome.investigation.id).one()
    assert dossier.status == "NEEDS_REVIEW"


def test_run_investigation_checkpoints_every_state(real_session: Session) -> None:
    company_id = _make_company(real_session, "State Machine Checkpoint Co")
    outcome = run_investigation(
        real_session, company_id, dt.date(2020, 1, 1), "test", BudgetConfig()
    )
    steps = (
        real_session.query(InvestigationStep)
        .filter_by(investigation_id=outcome.investigation.id)
        .order_by(InvestigationStep.step_no)
        .all()
    )
    states_seen = [s.state for s in steps]
    assert states_seen == ["PLAN", "GATHER", "TIMELINE", "DRAFT", "VERIFY"]
    assert steps[0].step_no == 0
    assert [s.step_no for s in steps] == list(range(len(steps)))


def test_run_investigation_resume_after_a_simulated_crash_gives_the_same_final_dossier(
    real_session: Session,
) -> None:
    """Simulates a real crash right after GATHER's checkpoint (the
    process is killed before TIMELINE ever runs): manually rewinds a
    completed investigation's state back to "TIMELINE" and deletes the
    claims/dossier that came after that point, then resumes. The
    final dossier must match a fresh, uninterrupted run on the same
    real company/as_of exactly."""
    as_of = dt.date(2020, 1, 1)
    company_id = _make_company(real_session, "State Machine Resume Co")
    first_pass = run_investigation(real_session, company_id, as_of, "test", BudgetConfig())
    assert first_pass.investigation.final_status == "FINALISED"
    first_pass_sections = first_pass.rendered.sections if first_pass.rendered else {}
    investigation_id = first_pass.investigation.id

    # Roll THAT SAME investigation back to a pre-DRAFT state to simulate
    # the crash, then resume it -- the real comparison is this one
    # investigation's own first-pass render against its resumed render,
    # never two different companies' dossiers (which would legitimately
    # differ by the real company name alone).

    real_session.query(Dossier).filter_by(investigation_id=investigation_id).delete()
    real_session.query(Claim).filter_by(investigation_id=investigation_id).delete()
    real_session.query(InvestigationStep).filter(
        InvestigationStep.investigation_id == investigation_id,
        InvestigationStep.state.in_(["TIMELINE", "DRAFT", "VERIFY", "REPAIR"]),
    ).delete(synchronize_session=False)
    investigation = real_session.get(Investigation, investigation_id)
    assert investigation is not None
    investigation.state = "TIMELINE"
    investigation.final_status = None
    investigation.failure_reason = None
    real_session.commit()

    resumed = run_investigation(
        real_session,
        company_id,
        as_of,
        "test",
        resume_investigation_id=investigation_id,
    )
    assert resumed.investigation.final_status == "FINALISED"
    assert resumed.rendered is not None
    assert resumed.rendered.sections == first_pass_sections


def _cleanup_one_investigation(session: Session, investigation_id: uuid.UUID) -> None:
    """Scoped to exactly one investigation -- unlike `_cleanup`, never
    touches the company or any of its other investigations. Used by
    the real-company regression tests below, which run against
    pre-existing production-like companies (DMART, VAKRANGEE,
    PNBHOUSING) that this test must never delete or whose real
    historical investigations it must never disturb."""
    session.execute(
        text(
            "DELETE FROM review_decisions_audit WHERE review_task_id IN "
            "(SELECT id FROM review_tasks WHERE dossier_id IN "
            "(SELECT id FROM dossiers WHERE investigation_id = :iid))"
        ),
        {"iid": investigation_id},
    )
    session.execute(
        text(
            "DELETE FROM review_tasks WHERE dossier_id IN "
            "(SELECT id FROM dossiers WHERE investigation_id = :iid)"
        ),
        {"iid": investigation_id},
    )
    session.execute(
        text("DELETE FROM dossiers WHERE investigation_id = :iid"), {"iid": investigation_id}
    )
    session.execute(
        text("DELETE FROM claims WHERE investigation_id = :iid"), {"iid": investigation_id}
    )
    session.execute(
        text("DELETE FROM investigation_steps WHERE investigation_id = :iid"),
        {"iid": investigation_id},
    )
    session.execute(text("DELETE FROM investigations WHERE id = :iid"), {"iid": investigation_id})
    session.commit()


# --- Phase 6 Correction 1 Sec2: the real "0 filings known as of" bug ---------
#
# Five real, already-FINALISED dossiers (DMART x2, VAKRANGEE,
# PNBHOUSING x2) rendered "0 real filings known as of" while
# `get_timeline` independently returned real filings for the same
# company/as_of. Root cause (confirmed via the real persisted
# `InvestigationStep`/`Claim.verification_checks` evidence,
# docs/phase-6/phase-6-correction-1.md Sec2): these five investigations
# ran on 2026-11-01 BEFORE that same day's verifier fix (commit
# 379fa27, then 9189752) added `timeline_entry` to the real dispatch in
# `verify_claim` -- under the then-current code every `timeline_entry`
# claim (which legitimately carries no evidence SPAN) fell through to
# the generic "unsupported claim" check and failed closed, and the
# investigations were never re-run after the fix landed. Current code
# already dispatches `timeline_entry` claims to `check_timeline_entry_claim`
# correctly (covered by tests/test_agent_verifier.py's own dispatch
# tests) -- this test instead regression-pins the fix at the full
# pipeline level: re-running each of the five real (company, as_of)
# pairs today must FINALISE with a chronology claiming exactly the
# real, independently-queried filing count, never zero.
REAL_PREVIOUSLY_BROKEN_CASES = [
    pytest.param(
        uuid.UUID("597dab79-c0fd-425c-8bf3-4c045ef57479"), dt.date(2023, 1, 1), 13, id="DMART-2023"
    ),
    pytest.param(
        uuid.UUID("597dab79-c0fd-425c-8bf3-4c045ef57479"), dt.date(2019, 1, 1), 11, id="DMART-2019"
    ),
    pytest.param(
        uuid.UUID("c84bde57-0fa2-444e-b70d-ec413d030d62"),
        dt.date(2023, 1, 1),
        11,
        id="VAKRANGEE-2023",
    ),
    pytest.param(
        uuid.UUID("b75df19e-08c3-4eeb-ad32-1614b1487346"),
        dt.date(2023, 1, 1),
        16,
        id="PNBHOUSING-2023",
    ),
    pytest.param(
        uuid.UUID("b75df19e-08c3-4eeb-ad32-1614b1487346"),
        dt.date(2019, 1, 1),
        7,
        id="PNBHOUSING-2019",
    ),
]


@pytest.mark.parametrize(
    "company_id, as_of, expected_real_filing_count", REAL_PREVIOUSLY_BROKEN_CASES
)
def test_rerunning_a_previously_broken_real_dossier_shows_real_filings(
    real_session: Session,
    company_id: uuid.UUID,
    as_of: dt.date,
    expected_real_filing_count: int,
) -> None:
    independent_count = sum(
        1 for entry in get_timeline(real_session, company_id, as_of).data if entry.kind == "filing"
    )
    assert independent_count == expected_real_filing_count, (
        "the real, independently-queried filing count for this company/as_of no "
        "longer matches this test's own frozen expectation -- the real underlying "
        "data changed; update expected_real_filing_count with a documented reason, "
        "never silently"
    )

    outcome = run_investigation(real_session, company_id, as_of, "test-phase-6-correction-1")
    try:
        assert outcome.investigation.final_status == "FINALISED"
        assert outcome.rendered is not None
        claimed_count = len(outcome.rendered.sections.get("chronology", []))
        assert claimed_count == independent_count, (
            f"dossier claimed {claimed_count} real filings but an independent "
            f"get_timeline() query found {independent_count} for the same "
            "company/as_of -- the real Sec2 bug has regressed"
        )
        assert claimed_count > 0
    finally:
        _cleanup_one_investigation(real_session, outcome.investigation.id)
