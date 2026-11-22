"""Tests for the precision-review enhancement
(ledgerlight.knowledge.precision_review): the exclusion rules, the
deterministic stratified sampler, the company cap, and the detector-
freeze guard that stops a sample from being evaluated against a
detector that has since changed.

DB-backed tests use the real local Postgres (`db_session`, transaction-
rolled-back) the same way tests/test_label_sample.py does, with
synthetic fixtures scoped by explicit id sets so they never touch or
get counted against the real corpus's own rows.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentVersion
from ledgerlight.knowledge.models import Chunk, Event, EventField, EventType, LabelItem
from ledgerlight.knowledge.precision_review import (
    Candidate,
    build_exclusion_set,
    current_detector_state,
    stratified_sample,
)
from ledgerlight.review_pack.audit import append_entry, latest_decisions

pytestmark = pytest.mark.integration


# --- fixture helpers (mirrors tests/test_label_sample.py) -------------------


def _make_version(session: Session) -> DocumentVersion:
    document = Document(
        source_id="sebi", source_key=f"test://precision/{uuid.uuid4()}", document_type="x"
    )
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key=f"raw/test/{uuid.uuid4()}.pdf",
        bytes=10,
        mime_type="application/pdf",
        retrieval_method="automated_fetch",
        retrieval_url="https://example.com/test.pdf",
        retrieved_at=dt.datetime.now(dt.UTC),
        known_at=dt.datetime.now(dt.UTC),
        known_at_basis="retrieved_at",
        tool_version="test/1",
    )
    session.add(version)
    session.flush()
    return version


def _make_chunk(session: Session, version: DocumentVersion, *, page: int = 1) -> Chunk:
    chunk = Chunk(
        version_id=version.id,
        page_number=page,
        char_start=0,
        char_end=10,
        text="irrelevant synthetic chunk text",
        chunker_version="test/1",
        known_at=dt.datetime.now(dt.UTC),
    )
    session.add(chunk)
    session.flush()
    return chunk


def _make_label_item(
    session: Session, version: DocumentVersion, chunk: Chunk | None, *, proposed: str = "none"
) -> LabelItem:
    item = LabelItem(
        version_id=version.id,
        page_number=1,
        chunk_id=chunk.id if chunk else None,
        proposed_event_type_code=proposed,
        proposer_name="keyword-rule-baseline",
        proposer_version="3",
        review_status="pending",
    )
    session.add(item)
    session.flush()
    return item


# --- exclusion rules ---------------------------------------------------------


def test_exclusion_covers_phase2_gold_label_set(db_session: Session, tmp_path: Path) -> None:
    version = _make_version(db_session)
    excluded_chunk = _make_chunk(db_session, version)
    kept_chunk = _make_chunk(db_session, version, page=2)
    excluded_item = _make_label_item(db_session, version, excluded_chunk)
    _make_label_item(db_session, version, kept_chunk)

    gold_path = tmp_path / "gold.json"
    gold_path.write_text(
        json.dumps({"records": [{"label_item_id": str(excluded_item.id)}]}), encoding="utf-8"
    )
    frozen_path = tmp_path / "frozen.json"
    frozen_path.write_text(json.dumps({"item_ids": []}), encoding="utf-8")

    report = build_exclusion_set(
        db_session,
        gold_labels_path=gold_path,
        frozen_test_split_path=frozen_path,
        hardening_cited_ids=frozenset(),
        review_pack_audit_paths=[],
    )

    assert excluded_chunk.id in report.excluded_chunk_ids
    assert kept_chunk.id not in report.excluded_chunk_ids
    assert report.by_source["phase2_gold_label_set"] == 1


def test_exclusion_covers_frozen_test_split_net_new(db_session: Session, tmp_path: Path) -> None:
    version = _make_version(db_session)
    chunk = _make_chunk(db_session, version)
    item = _make_label_item(db_session, version, chunk)

    gold_path = tmp_path / "gold.json"
    gold_path.write_text(json.dumps({"records": []}), encoding="utf-8")
    frozen_path = tmp_path / "frozen.json"
    frozen_path.write_text(json.dumps({"item_ids": [str(item.id)]}), encoding="utf-8")

    report = build_exclusion_set(
        db_session,
        gold_labels_path=gold_path,
        frozen_test_split_path=frozen_path,
        hardening_cited_ids=frozenset(),
        review_pack_audit_paths=[],
    )

    assert chunk.id in report.excluded_chunk_ids
    assert report.by_source["frozen_test_split_net_new"] == 1


def test_exclusion_covers_hardening_cited_ids(db_session: Session, tmp_path: Path) -> None:
    version = _make_version(db_session)
    chunk = _make_chunk(db_session, version)
    item = _make_label_item(db_session, version, chunk)

    empty_path = tmp_path / "empty.json"
    empty_path.write_text(json.dumps({"records": [], "item_ids": []}), encoding="utf-8")

    report = build_exclusion_set(
        db_session,
        gold_labels_path=empty_path,
        frozen_test_split_path=empty_path,
        hardening_cited_ids=frozenset({str(item.id)}),
        review_pack_audit_paths=[],
    )

    assert chunk.id in report.excluded_chunk_ids
    assert report.by_source["hardening_docs_cited_net_new"] == 1


def _existing_event_type(session: Session, code: str) -> EventType:
    event_type = session.scalar(select(EventType).where(EventType.code == code))
    assert event_type is not None, f"taxonomy not loaded: {code} missing"
    return event_type


def test_exclusion_covers_ai_qa_review_pack_field_review(
    db_session: Session, tmp_path: Path
) -> None:
    version = _make_version(db_session)
    chunk = _make_chunk(db_session, version, page=3)

    event_type = _existing_event_type(db_session, "AUD_RESIGN")
    event = Event(
        event_type_id=event_type.id,
        known_at=dt.datetime.now(dt.UTC),
        severity="low",
        status="candidate",
        detector_name="test",
        detector_version="1",
        confidence=0.5,
    )
    db_session.add(event)
    db_session.flush()
    field = EventField(
        event_id=event.id,
        field_name="audit_firm",
        value_json="Test & Co",
        evidence_version_id=version.id,
        evidence_page=chunk.page_number,
        evidence_char_start=0,
        evidence_char_end=5,
        extractor_name="test",
        extractor_version="1",
        confidence=0.9,
        validation_status="validated",
    )
    db_session.add(field)
    db_session.flush()

    field_audit_path = tmp_path / "field-review-audit.jsonl"
    field_audit_path.write_text(
        json.dumps({"item_id": str(field.id), "decision": "correct"}) + "\n", encoding="utf-8"
    )
    empty_path = tmp_path / "empty.json"
    empty_path.write_text(json.dumps({"records": [], "item_ids": []}), encoding="utf-8")

    report = build_exclusion_set(
        db_session,
        gold_labels_path=empty_path,
        frozen_test_split_path=empty_path,
        hardening_cited_ids=frozenset(),
        review_pack_audit_paths=[field_audit_path],
    )

    assert chunk.id in report.excluded_chunk_ids
    assert report.by_source["ai_qa_review_pack_net_new"] == 1


def test_exclusion_non_field_review_pack_files_contribute_nothing(
    db_session: Session, tmp_path: Path
) -> None:
    empty_path = tmp_path / "empty.json"
    empty_path.write_text(json.dumps({"records": [], "item_ids": []}), encoding="utf-8")
    other_path = tmp_path / "retrieval-review-audit.jsonl"
    other_path.write_text(json.dumps({"item_id": str(uuid.uuid4())}) + "\n", encoding="utf-8")

    report = build_exclusion_set(
        db_session,
        gold_labels_path=empty_path,
        frozen_test_split_path=empty_path,
        hardening_cited_ids=frozenset(),
        review_pack_audit_paths=[other_path],
    )

    assert report.by_source["ai_qa_review_pack"] == 0
    assert any("retrieval-review-audit.jsonl" in note for note in report.notes)


# --- deterministic stratified sampling ---------------------------------------


def _candidates(n: int, *, companies: list[str], event_type: str = "KMP_EXIT") -> list[Candidate]:
    return [
        Candidate(
            chunk_id=uuid.uuid4(),
            event_type=event_type,
            company_id=uuid.UUID(int=i % len(companies)),
            company_name=companies[i % len(companies)],
        )
        for i in range(n)
    ]


def test_sampling_is_deterministic_given_same_seed() -> None:
    candidates = _candidates(50, companies=["A", "B", "C", "D", "E"])
    first = stratified_sample(candidates, seed=42, limit=20)
    second = stratified_sample(candidates, seed=42, limit=20)
    assert [c.chunk_id for c in first.selected] == [c.chunk_id for c in second.selected]


def test_sampling_different_seed_can_differ() -> None:
    candidates = _candidates(50, companies=["A", "B", "C", "D", "E"])
    seed42 = stratified_sample(candidates, seed=42, limit=20)
    seed7 = stratified_sample(candidates, seed=7, limit=20)
    assert {c.chunk_id for c in seed42.selected} != {c.chunk_id for c in seed7.selected}


def test_sampling_reports_shortfall_when_too_few_eligible() -> None:
    candidates = _candidates(3, companies=["A"])
    result = stratified_sample(candidates, seed=42, limit=20)
    assert len(result.selected) == 3
    assert result.shortfall == 17
    assert result.eligible_total == 3


def test_sampling_no_shortfall_when_enough_eligible() -> None:
    candidates = _candidates(25, companies=["A", "B", "C", "D", "E"])
    result = stratified_sample(candidates, seed=42, limit=20)
    assert len(result.selected) == 20
    assert result.shortfall == 0


# --- company cap --------------------------------------------------------------


def test_company_cap_is_enforced_when_enough_companies_exist() -> None:
    # 10 companies x 10 items = 100 candidates; cap for limit=20 is
    # ceil(20*0.30)=6, and there's plenty of supply to honour it.
    candidates = _candidates(100, companies=[f"co-{i}" for i in range(10)])
    result = stratified_sample(candidates, seed=42, limit=20)
    assert len(result.selected) == 20
    assert max(result.companies.values()) <= 6


def test_company_cap_relaxed_when_too_few_companies_to_honour_it() -> None:
    # Only 1 company exists at all -- the cap can't be honoured without
    # starving the sample, so the sample still fills to `limit`.
    candidates = _candidates(30, companies=["only-co"])
    result = stratified_sample(candidates, seed=42, limit=20)
    assert len(result.selected) == 20
    assert result.companies == {"only-co": 20}


# --- resume (the generic append-only audit mechanism every review-pack
# CLI, including scripts/precision_review.py, relies on for resuming) ---


def test_audit_resume_skips_already_decided_items(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    append_entry(audit_path, item_id="item-1", decision="correct", reviewer="r1")
    append_entry(audit_path, item_id="item-2", decision="skip", reviewer="r1", note="unsure")

    decided = latest_decisions(audit_path)
    assert set(decided) == {"item-1", "item-2"}

    # Re-deciding an item overwrites its latest decision (simulating a
    # resumed run correcting an earlier skip), without losing the append-only
    # history of the first decision.
    append_entry(audit_path, item_id="item-2", decision="correct", reviewer="r1")
    decided_again = latest_decisions(audit_path)
    assert decided_again["item-2"]["decision"] == "correct"
    assert sum(1 for _ in audit_path.open(encoding="utf-8")) == 3


# --- detector-freeze guard ----------------------------------------------------


def test_detector_freeze_matches_current_code_and_artifact() -> None:
    """Guards §1.2: if this fails, either the recorded freeze manifest is
    stale (re-run scripts/build_precision_review_sample.py to produce a
    NEW sample before evaluating precision on it) or the manifest itself
    was hand-edited. Either way, this sample must not be used as-is."""
    freeze_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "manifests"
        / "precision-review-v1-detector.json"
    )
    if not freeze_path.exists():
        pytest.skip("precision-review-v1-detector.json not built yet")

    with freeze_path.open(encoding="utf-8") as f:
        frozen = json.load(f)

    current = current_detector_state()
    assert frozen["detectors"] == current, (
        "the checked-out detector code/artifact no longer matches the frozen "
        "manifest -- any precision measured against data/manifests/"
        "precision-review-v1.jsonl is no longer about the current detector; "
        "build a NEW sample instead of reusing this one"
    )
