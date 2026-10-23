from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _is_ignored(relative_path: str) -> bool:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", relative_path],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    # git check-ignore exits 0 if the path is ignored, 1 if not ignored.
    return proc.returncode == 0


@pytest.mark.parametrize(
    "relative_path",
    [
        ".env",
        ".env.local",
        "data/raw/bse/2026/some-file.pdf",
        "data/interim/scratch.parquet",
        "data/processed/output.csv",
        "local.db",
        "cache.sqlite",
        ".claude/settings.local.json",
        "__pycache__/mod.pyc",
        ".venv/pyvenv.cfg",
    ],
)
def test_sensitive_and_raw_paths_are_ignored(relative_path: str) -> None:
    assert _is_ignored(relative_path), f"expected {relative_path} to be gitignored"


@pytest.mark.parametrize(
    "relative_path",
    [
        ".env.example",
        "data/manifests/sources.yaml",
        "data/README.md",
        "ledgerlight/config/settings.py",
    ],
)
def test_committed_paths_are_not_ignored(relative_path: str) -> None:
    assert not _is_ignored(relative_path), f"expected {relative_path} to NOT be gitignored"
