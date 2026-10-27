"""Tests for the frozen Phase 2 evaluation-data guard. Phase 3's own
ground rule: no training, tuning, or threshold-selection code may ever
read a frozen test item."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.modelling.frozen_split_guard import (
    FrozenSplitViolation,
    assert_no_frozen_test_ids,
    load_frozen_test_ids,
    load_gold_label_records,
)


def _write_frozen_manifest(path: Path, ids: list[uuid.UUID]) -> None:
    payload = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "description": "test fixture",
        "count": len(ids),
        "item_ids": sorted(str(i) for i in ids),
        "sha256_of_sorted_ids": "irrelevant-for-this-test",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_guard_raises_when_frozen_test_id_present(tmp_path: Path) -> None:
    frozen_id = uuid.uuid4()
    other_id = uuid.uuid4()
    manifest = tmp_path / "frozen.json"
    _write_frozen_manifest(manifest, [frozen_id, other_id])

    with pytest.raises(FrozenSplitViolation, match="touched 1 frozen test item"):
        assert_no_frozen_test_ids(
            [frozen_id, uuid.uuid4()], context="unit test", frozen_path=manifest
        )


def test_guard_passes_when_no_overlap(tmp_path: Path) -> None:
    manifest = tmp_path / "frozen.json"
    _write_frozen_manifest(manifest, [uuid.uuid4(), uuid.uuid4()])

    # Must not raise.
    assert_no_frozen_test_ids(
        [uuid.uuid4(), uuid.uuid4()], context="unit test", frozen_path=manifest
    )


def test_guard_passes_on_empty_candidate_set(tmp_path: Path) -> None:
    manifest = tmp_path / "frozen.json"
    _write_frozen_manifest(manifest, [uuid.uuid4()])

    assert_no_frozen_test_ids([], context="unit test", frozen_path=manifest)


def test_load_frozen_test_ids_round_trips(tmp_path: Path) -> None:
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    manifest = tmp_path / "frozen.json"
    _write_frozen_manifest(manifest, ids)

    loaded = load_frozen_test_ids(manifest)
    assert loaded == set(ids)


@pytest.mark.integration
def test_frozen_manifest_matches_real_test_split(db_session: Session) -> None:
    """The committed manifest must be a faithful snapshot of the real
    database's test split at the time it was frozen -- if this ever
    fails, the manifest is stale and must be regenerated deliberately,
    not silently."""
    from ledgerlight.knowledge.models import LabelItem

    real_test_ids = set(
        db_session.scalars(select(LabelItem.id).where(LabelItem.split == "test")).all()
    )
    frozen_ids = load_frozen_test_ids()
    assert real_test_ids == frozen_ids


@pytest.mark.integration
def test_train_classifier_dev_split_contains_no_frozen_test_ids(db_session: Session) -> None:
    """Real proof, not just a synthetic unit test: the actual dev split
    used by scripts/train_classifier.py never overlaps the frozen test
    split."""
    from ledgerlight.knowledge.models import LabelItem

    dev_ids = db_session.scalars(select(LabelItem.id).where(LabelItem.split == "dev")).all()
    # Must not raise -- proves the real dev split is clean.
    assert_no_frozen_test_ids(dev_ids, context="real dev split")


@pytest.mark.integration
def test_gold_label_records_match_real_gold_count(db_session: Session) -> None:
    from sqlalchemy import func

    from ledgerlight.knowledge.models import LabelItem

    real_gold_count = db_session.scalar(
        select(func.count())
        .select_from(LabelItem)
        .where(LabelItem.label_source == "human_reviewed")
    )
    records = load_gold_label_records()
    assert len(records) == real_gold_count
    assert all(r["label_item_id"] for r in records)
