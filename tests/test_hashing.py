from __future__ import annotations

import hashlib
from pathlib import Path

from ledgerlight.common.hashing import sha256_bytes, sha256_file


def test_sha256_bytes_matches_stdlib() -> None:
    data = b"ledgerlight phase 0 test content"
    assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()


def test_sha256_file_matches_stdlib(tmp_path: Path) -> None:
    data = b"x" * (2 * 1024 * 1024 + 17)  # spans multiple read chunks
    f = tmp_path / "sample.bin"
    f.write_bytes(data)
    assert sha256_file(f) == hashlib.sha256(data).hexdigest()


def test_sha256_bytes_differs_for_different_content() -> None:
    assert sha256_bytes(b"a") != sha256_bytes(b"b")
