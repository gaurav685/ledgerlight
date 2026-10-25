from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ledgerlight.processing.limits import (
    LimitExceededError,
    ProcessingLimits,
    check_file_size,
    check_page_count,
    check_zip_safety,
)


def test_file_size_within_limit_ok(tmp_path: Path) -> None:
    f = tmp_path / "small.bin"
    f.write_bytes(b"x" * 100)
    check_file_size(f, ProcessingLimits(max_file_size_bytes=1000))


def test_file_size_over_limit_raises(tmp_path: Path) -> None:
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * 2000)
    with pytest.raises(LimitExceededError):
        check_file_size(f, ProcessingLimits(max_file_size_bytes=1000))


def test_page_count_within_limit_ok() -> None:
    check_page_count(5, ProcessingLimits(max_pages=10))


def test_page_count_over_limit_raises() -> None:
    with pytest.raises(LimitExceededError):
        check_page_count(11, ProcessingLimits(max_pages=10))


def test_zip_within_limits_ok(tmp_path: Path) -> None:
    zpath = tmp_path / "ok.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("data.csv", "a,b,c\n1,2,3\n")
    check_zip_safety(zpath, ProcessingLimits())


def test_zip_too_many_entries_raises(tmp_path: Path) -> None:
    zpath = tmp_path / "many.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for i in range(5):
            zf.writestr(f"f{i}.txt", "x")
    with pytest.raises(LimitExceededError):
        check_zip_safety(zpath, ProcessingLimits(zip_max_entries=3))


def test_zip_uncompressed_bomb_raises(tmp_path: Path) -> None:
    zpath = tmp_path / "bomb.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("huge.txt", "0" * 10_000)
    with pytest.raises(LimitExceededError):
        check_zip_safety(zpath, ProcessingLimits(zip_max_uncompressed_bytes=100))


def test_zip_path_traversal_entry_raises(tmp_path: Path) -> None:
    zpath = tmp_path / "traversal.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../../etc/passwd", "evil")
    with pytest.raises(LimitExceededError):
        check_zip_safety(zpath, ProcessingLimits())


def test_zip_absolute_path_entry_raises(tmp_path: Path) -> None:
    zpath = tmp_path / "absolute.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("/etc/passwd", "evil")
    with pytest.raises(LimitExceededError):
        check_zip_safety(zpath, ProcessingLimits())
