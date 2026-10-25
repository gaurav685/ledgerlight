"""Regression test for a real bug found in Phase 1 verification:
re-fetching the same NSE bhavcopy URL produced a different raw sha256
every time because the server regenerates the ZIP container's per-entry
timestamp on every request, even when the inner CSV is byte-identical --
causing spurious DocumentVersion rows on every re-fetch of an unchanged
trading day. See ledgerlight.ingestion.content_identity and ADR 0004.
"""

from __future__ import annotations

import io
import zipfile

from ledgerlight.ingestion.content_identity import content_identity_bytes, content_identity_hash


def _zip_with_timestamp(
    inner_name: str, inner_bytes: bytes, date_time: tuple[int, int, int, int, int, int]
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo(inner_name, date_time=date_time)
        zf.writestr(info, inner_bytes)
    return buf.getvalue()


def test_same_inner_content_different_zip_timestamp_has_same_identity_hash() -> None:
    inner = b"SYMBOL,SERIES,OPEN\nINFY,EQ,1500.00\n"
    zip_a = _zip_with_timestamp("bhav.csv", inner, (2023, 8, 21, 17, 32, 16))
    zip_b = _zip_with_timestamp("bhav.csv", inner, (2023, 8, 21, 17, 32, 14))

    assert zip_a != zip_b  # raw bytes genuinely differ (the real-world symptom)
    assert content_identity_hash(zip_a, "application/zip") == content_identity_hash(
        zip_b, "application/zip"
    )


def test_genuinely_different_inner_content_has_different_identity_hash() -> None:
    zip_a = _zip_with_timestamp(
        "bhav.csv", b"SYMBOL,SERIES,OPEN\nINFY,EQ,1500.00\n", (2023, 1, 1, 0, 0, 0)
    )
    zip_b = _zip_with_timestamp(
        "bhav.csv", b"SYMBOL,SERIES,OPEN\nINFY,EQ,1600.00\n", (2023, 1, 1, 0, 0, 0)
    )

    assert content_identity_hash(zip_a, "application/zip") != content_identity_hash(
        zip_b, "application/zip"
    )


def test_non_zip_content_identity_is_the_raw_bytes() -> None:
    body = b"<html>some page</html>"
    assert content_identity_bytes(body, "text/html") == body


def test_multi_entry_zip_falls_back_to_raw_bytes() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "a")
        zf.writestr("b.txt", "b")
    body = buf.getvalue()
    assert content_identity_bytes(body, "application/zip") == body


def test_malformed_zip_falls_back_to_raw_bytes() -> None:
    body = b"not actually a zip file"
    assert content_identity_bytes(body, "application/zip") == body
