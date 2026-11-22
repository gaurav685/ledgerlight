"""Phase 6 Correction 1: every CLI that records a real review decision
must refuse unless a real human explicitly passes `--human`. Added
after an AI session ran these tools under an explicit user override --
see docs/phase-6/phase-6-correction-1.md.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

from ledgerlight.review_pack import require_human_confirmation

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_require_human_confirmation_blocks_without_the_flag() -> None:
    args = argparse.Namespace(human=False, reviewer="someone")
    with pytest.raises(SystemExit) as exc_info:
        require_human_confirmation(args)
    assert exc_info.value.code == 2


def test_require_human_confirmation_blocks_when_attribute_missing() -> None:
    args = argparse.Namespace(reviewer="someone")
    with pytest.raises(SystemExit):
        require_human_confirmation(args)


def test_require_human_confirmation_allows_with_the_flag() -> None:
    args = argparse.Namespace(human=True, reviewer="someone")
    require_human_confirmation(args)  # must not raise


@pytest.mark.parametrize(
    "script,extra_args",
    [
        ("scripts/field_review.py", ["--reviewer", "test"]),
        ("scripts/entity_pair_review.py", ["--reviewer", "test"]),
        ("scripts/retrieval_review.py", ["--reviewer", "test"]),
        ("scripts/outcome_evidence_review.py", ["--reviewer", "test"]),
        ("scripts/precision_review.py", ["--reviewer", "test"]),
    ],
)
def test_file_backed_review_cli_refuses_without_human_flag(
    script: str, extra_args: list[str]
) -> None:
    """Real subprocess run, real argparse, no --human -- must refuse
    with exit code 2 before ever connecting to a database (confirmed
    by the fact this needs no real local stack running to pass)."""
    result = subprocess.run(
        [sys.executable, script, *extra_args, "--limit", "0"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "--human" in result.stderr


def test_dossier_review_decide_refuses_without_human_flag() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/dossier_review.py",
            "decide",
            "--task-id",
            "00000000-0000-0000-0000-000000000000",
            "--decision",
            "approve",
            "--reviewer",
            "test",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "--human" in result.stderr


def test_dossier_review_feedback_refuses_without_human_flag() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/dossier_review.py",
            "feedback",
            "--event-id",
            "00000000-0000-0000-0000-000000000000",
            "--status",
            "verified",
            "--reviewer",
            "test",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "--human" in result.stderr
