"""Tests for ledgerlight.agent.qc_seed -- Phase 4 Sec7 seeded QC.

`seed_flawed_dossier` runs a real investigation and commits internally
(via `run_investigation`/`record_decision`), so these tests use the
same real, independent-session-with-manual-cleanup pattern as
`test_agent_state_machine.py` and `test_agent_review.py`, not the
project's usual rolled-back `db_session` fixture.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.agent.models import Claim, Dossier, Investigation, ReviewTask
from ledgerlight.agent.qc_seed import (
    ALL_FLAW_TYPES,
    FLAW_MISSING_CITATION,
    FLAW_UNSUPPORTED_CLAIM,
    FLAW_WRONG_DATE,
    FLAW_WRONG_NUMBER,
    SEEDED_QC_EXPECTED_OUTCOME,
    compute_catch_rate_report,
    seed_flawed_dossier,
    seed_qc_batch,
)
from ledgerlight.agent.review import SEEDED_QC, record_decision
from ledgerlight.db.models import Document, DocumentPage, DocumentVersion
from ledgerlight.knowledge.models import Company, Event, EventField, EventType, Filing

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

    created: dict[str, list[uuid.UUID]] = {"companies": [], "document_versions": []}
    session.info["created"] = created
    try:
        yield session
    finally:
        _cleanup(session, created)
        session.close()


def _cleanup(session: Session, created: dict[str, list[uuid.UUID]]) -> None:
    company_ids = created["companies"]
    if company_ids:
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
        session.execute(
            text(
                "DELETE FROM event_fields WHERE event_id IN "
                "(SELECT id FROM events WHERE company_id = ANY(:ids))"
            ),
            {"ids": company_ids},
        )
        session.execute(
            text("DELETE FROM events WHERE company_id = ANY(:ids)"), {"ids": company_ids}
        )
        session.execute(
            text("DELETE FROM filings WHERE company_id = ANY(:ids)"), {"ids": company_ids}
        )
        session.execute(text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": company_ids})
    version_ids = created["document_versions"]
    if version_ids:
        session.execute(
            text("DELETE FROM document_pages WHERE version_id = ANY(:ids)"), {"ids": version_ids}
        )
        session.execute(
            text(
                "DELETE FROM document_versions WHERE id = ANY(:ids) "
                "AND NOT EXISTS (SELECT 1 FROM filings WHERE version_id = document_versions.id)"
            ),
            {"ids": version_ids},
        )
    session.commit()


def _make_company(session: Session, name: str) -> uuid.UUID:
    company = Company(id=uuid.uuid4(), display_name=name)
    session.add(company)
    session.commit()
    session.info["created"]["companies"].append(company.id)
    return company.id


def _make_company_with_real_event(session: Session, name: str, known_at: dt.datetime) -> uuid.UUID:
    """A real company with one real, evidenced governance event --
    the real donor `wrong_date`/`wrong_number` need to corrupt against
    a real, resolving evidence span."""
    company_id = _make_company(session, name)

    document = Document(
        source_id="sebi",
        source_key=f"test://qc-seed/{uuid.uuid4()}",
        document_type="announcement",
    )
    session.add(document)
    session.flush()
    page_text = "The auditor resigned effective 2019-06-15, citing real governance concerns."
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key=f"raw/test/{uuid.uuid4()}.pdf",
        bytes=len(page_text),
        mime_type="application/pdf",
        retrieval_method="automated_fetch",
        retrieval_url="https://example.com/test.pdf",
        retrieved_at=known_at,
        known_at=known_at,
        known_at_basis="retrieved_at",
        tool_version="test/1",
    )
    session.add(version)
    session.flush()
    session.add(
        DocumentPage(
            version_id=version.id,
            page_number=1,
            raw_text=page_text,
            text_sha256=uuid.uuid4().hex,
            char_count=len(page_text),
            extraction_method="text_layer",
            extractor_version="test/1",
        )
    )
    session.flush()
    session.info["created"]["document_versions"].append(version.id)
    session.add(
        Filing(version_id=version.id, company_id=company_id, link_method="manual", confidence=1.0)
    )

    event_type = session.scalar(select(EventType).where(EventType.code == "AUD_RESIGN"))
    assert event_type is not None, "real event type AUD_RESIGN must already exist"
    event = Event(
        event_type_id=event_type.id,
        company_id=company_id,
        known_at=known_at,
        severity="medium",
        status="verified",
        detector_name="test",
        detector_version="1",
        confidence=0.9,
    )
    session.add(event)
    session.flush()
    session.add(
        EventField(
            event_id=event.id,
            field_name="resignation_date",
            value_json="2019-06-15",
            evidence_version_id=version.id,
            evidence_page=1,
            evidence_char_start=0,
            evidence_char_end=len(page_text),
            extractor_name="test",
            extractor_version="1",
            confidence=0.9,
            validation_status="validated",
        )
    )
    session.commit()
    return company_id


# --- seed_flawed_dossier: flaw types that need no real donor ------------------


def test_seed_flawed_dossier_unsupported_claim_opens_a_seeded_review_task(
    real_session: Session,
) -> None:
    company_id = _make_company(real_session, "QC Seed Unsupported Co")
    item = seed_flawed_dossier(
        real_session, company_id, dt.date(2020, 1, 1), FLAW_UNSUPPORTED_CLAIM
    )

    task = real_session.get(ReviewTask, item.review_task_id)
    assert task is not None
    assert task.seeded_qc is True
    assert task.reason_code == SEEDED_QC
    assert task.expected_outcome == SEEDED_QC_EXPECTED_OUTCOME
    assert task.status == "open"

    dossier = real_session.get(Dossier, item.dossier_id)
    assert dossier is not None
    assert dossier.version == 2  # version 1 is the real, unflawed run

    flawed_claim = real_session.get(Claim, item.flawed_claim_id)
    assert flawed_claim is not None
    assert flawed_claim.evidence == []
    assert flawed_claim.payload["qc_flaw_type"] == FLAW_UNSUPPORTED_CLAIM


def test_seed_flawed_dossier_missing_citation_evidence_does_not_resolve(
    real_session: Session,
) -> None:
    company_id = _make_company(real_session, "QC Seed Missing Citation Co")
    item = seed_flawed_dossier(real_session, company_id, dt.date(2020, 1, 1), FLAW_MISSING_CITATION)
    flawed_claim = real_session.get(Claim, item.flawed_claim_id)
    assert flawed_claim is not None
    assert len(flawed_claim.evidence) == 1
    # A deliberately nonexistent document_version_id -- never a real span.
    doc_version_id = flawed_claim.evidence[0]["document_version_id"]  # type: ignore[index]
    exists = real_session.execute(
        text("SELECT 1 FROM document_versions WHERE id = :id"), {"id": doc_version_id}
    ).first()
    assert exists is None


def test_seed_flawed_dossier_never_touches_the_real_investigation_final_status(
    real_session: Session,
) -> None:
    """The real run's own FINALISED/NEEDS_REVIEW outcome is set before
    the flaw is ever injected, and qc_seed must never overwrite it --
    the one invariant Sec8's real statistics rely on."""
    company_id = _make_company(real_session, "QC Seed Final Status Co")
    item = seed_flawed_dossier(
        real_session, company_id, dt.date(2020, 1, 1), FLAW_UNSUPPORTED_CLAIM
    )
    investigation = real_session.get(Investigation, item.investigation_id)
    assert investigation is not None
    assert investigation.final_status == "FINALISED"  # a fresh company always finalises cleanly


def test_seed_flawed_dossier_rejects_unknown_flaw_type(real_session: Session) -> None:
    company_id = _make_company(real_session, "QC Seed Unknown Flaw Co")
    with pytest.raises(ValueError, match="unknown flaw_type"):
        seed_flawed_dossier(real_session, company_id, dt.date(2020, 1, 1), "not_a_real_flaw_type")


# --- seed_flawed_dossier: flaw types that need a real donor claim ------------


def test_seed_flawed_dossier_wrong_date_without_a_donor_raises(real_session: Session) -> None:
    company_id = _make_company(real_session, "QC Seed No Donor Co")
    with pytest.raises(ValueError, match="needs a real donor claim"):
        seed_flawed_dossier(real_session, company_id, dt.date(2020, 1, 1), FLAW_WRONG_DATE)


def test_seed_flawed_dossier_wrong_date_corrupts_against_a_real_span(real_session: Session) -> None:
    company_id = _make_company_with_real_event(
        real_session, "QC Seed Wrong Date Co", dt.datetime(2019, 6, 15, tzinfo=dt.UTC)
    )
    item = seed_flawed_dossier(real_session, company_id, dt.date(2020, 1, 1), FLAW_WRONG_DATE)
    flawed_claim = real_session.get(Claim, item.flawed_claim_id)
    assert flawed_claim is not None
    assert flawed_claim.claim_type == "event"
    assert flawed_claim.payload["known_at"] == "1901-01-01T00:00:00+00:00"
    assert len(flawed_claim.evidence) == 1


def test_seed_flawed_dossier_wrong_number_corrupts_against_a_real_span(
    real_session: Session,
) -> None:
    company_id = _make_company_with_real_event(
        real_session, "QC Seed Wrong Number Co", dt.datetime(2019, 6, 15, tzinfo=dt.UTC)
    )
    item = seed_flawed_dossier(real_session, company_id, dt.date(2020, 1, 1), FLAW_WRONG_NUMBER)
    flawed_claim = real_session.get(Claim, item.flawed_claim_id)
    assert flawed_claim is not None
    assert flawed_claim.claim_type == "metric"
    assert flawed_claim.payload["value"] == "ZZZ_SEEDED_QC_NOT_A_REAL_RATING"
    assert len(flawed_claim.evidence) == 1


# --- seed_qc_batch -------------------------------------------------------------


def test_seed_qc_batch_seeds_zero_items_at_zero_fraction(real_session: Session) -> None:
    company_id = _make_company(real_session, "QC Seed Batch Zero Co")
    items = seed_qc_batch(real_session, [(company_id, dt.date(2020, 1, 1))], seed_fraction=0.0)
    assert items == []


def test_seed_qc_batch_seeds_at_least_one_item_at_a_small_positive_fraction(
    real_session: Session,
) -> None:
    # Real donor claims so whichever flaw type the fixed cycling order picks
    # first (wrong_date, which needs one) can actually be seeded.
    company_ids = [
        _make_company_with_real_event(
            real_session, f"QC Seed Batch Co {i}", dt.datetime(2019, 6, 15, tzinfo=dt.UTC)
        )
        for i in range(3)
    ]
    targets = [(cid, dt.date(2020, 1, 1)) for cid in company_ids]
    items = seed_qc_batch(real_session, targets, seed_fraction=0.1)
    assert len(items) == 1
    assert items[0].flaw_type == ALL_FLAW_TYPES[0]


def test_seed_qc_batch_rejects_an_out_of_range_fraction(real_session: Session) -> None:
    company_id = _make_company(real_session, "QC Seed Batch Invalid Co")
    with pytest.raises(ValueError, match="seed_fraction must be in"):
        seed_qc_batch(real_session, [(company_id, dt.date(2020, 1, 1))], seed_fraction=1.5)


def test_seed_qc_batch_skips_a_target_with_no_donor_instead_of_crashing(
    real_session: Session,
) -> None:
    """A fresh company has no claim with a resolving evidence span --
    wrong_date (ALL_FLAW_TYPES[0], always assigned to the one chosen
    target at fraction=1.0) needs one. The real batch must skip this
    target via on_skip, never raise and abort the whole batch."""
    company_id = _make_company(real_session, "QC Seed Batch No Donor Co")
    skips: list[tuple[uuid.UUID, dt.date, str, str]] = []

    items = seed_qc_batch(
        real_session,
        [(company_id, dt.date(2020, 1, 1))],
        seed_fraction=1.0,
        on_skip=lambda cid, as_of, flaw_type, reason: skips.append((cid, as_of, flaw_type, reason)),
    )

    assert items == []
    assert len(skips) == 1
    assert skips[0][0] == company_id
    assert skips[0][2] == FLAW_WRONG_DATE
    assert "needs a real donor claim" in skips[0][3]


# --- compute_catch_rate_report -------------------------------------------------


def test_compute_catch_rate_report_counts_a_correct_reject_as_caught(
    real_session: Session,
) -> None:
    company_id = _make_company(real_session, "QC Seed Catch Rate Co")
    item = seed_flawed_dossier(
        real_session, company_id, dt.date(2020, 1, 1), FLAW_UNSUPPORTED_CLAIM
    )
    record_decision(real_session, item.review_task_id, "reject", "reviewer_qc", notes="caught it")

    report = compute_catch_rate_report(real_session)
    row = next(r for r in report if r.flaw_type == FLAW_UNSUPPORTED_CLAIM)
    assert row.seeded_count >= 1
    assert row.reviewed_count >= 1
    assert row.caught_count >= 1
    assert row.catch_rate == 1.0


def test_compute_catch_rate_report_counts_a_wrong_approve_as_not_caught(
    real_session: Session,
) -> None:
    company_id = _make_company(real_session, "QC Seed Missed Co")
    item = seed_flawed_dossier(real_session, company_id, dt.date(2020, 1, 1), FLAW_MISSING_CITATION)
    record_decision(real_session, item.review_task_id, "approve", "reviewer_qc", notes="missed it")

    report = compute_catch_rate_report(real_session)
    row = next(r for r in report if r.flaw_type == FLAW_MISSING_CITATION)
    assert row.reviewed_count >= 1
    assert row.catch_rate == 0.0


def test_compute_catch_rate_report_excludes_undecided_seeded_tasks(real_session: Session) -> None:
    company_id = _make_company(real_session, "QC Seed Undecided Co")
    seed_flawed_dossier(real_session, company_id, dt.date(2020, 1, 1), FLAW_UNSUPPORTED_CLAIM)

    report = compute_catch_rate_report(real_session)
    row = next(r for r in report if r.flaw_type == FLAW_UNSUPPORTED_CLAIM)
    assert row.seeded_count >= 1
    # Not yet decided -- excluded from reviewed_count, never counted as a miss.
    assert row.reviewed_count == 0
    assert row.catch_rate is None
