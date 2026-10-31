"""Tests for ledgerlight.modelling.scoring.write_experiment_doc --
Phase 3 §11's docs/experiments/<id>.md, auto-generated."""

from __future__ import annotations

import uuid
from pathlib import Path

from ledgerlight.modelling.scoring import write_experiment_doc


def test_write_experiment_doc_creates_a_real_file_with_the_real_content(tmp_path: Path) -> None:
    experiment_id = uuid.uuid4()
    path = write_experiment_doc(
        experiment_id,
        config={"command": "backtest", "seed": 42},
        data_snapshot_hashes={"dataset": "deadbeef"},
        git_sha="a" * 40,
        metrics={"pr_auc": 0.27},
        output_dir=tmp_path,
    )
    assert path == tmp_path / f"{experiment_id}.md"
    content = path.read_text(encoding="utf-8")
    assert str(experiment_id) in content
    assert "a" * 40 in content
    assert '"pr_auc": 0.27' in content


def test_write_experiment_doc_creates_the_output_directory_if_missing(tmp_path: Path) -> None:
    nested_dir = tmp_path / "experiments" / "nested"
    write_experiment_doc(
        uuid.uuid4(),
        config={},
        data_snapshot_hashes={},
        git_sha="b" * 40,
        metrics={},
        output_dir=nested_dir,
    )
    assert nested_dir.is_dir()
