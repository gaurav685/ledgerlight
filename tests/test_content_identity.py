"""Regression tests for two real bugs:

1. (Phase 1 verification) Re-fetching the same NSE bhavcopy URL produced
   a different raw sha256 every time because the server regenerates the
   ZIP container's per-entry timestamp on every request, even when the
   inner CSV is byte-identical -- causing spurious DocumentVersion rows
   on every re-fetch of an unchanged trading day.
2. (Phase 2 preflight) The same class of problem for dynamic HTML pages
   with per-request CSRF tokens / randomized DOM ids -- 4 real documents
   churned a new version on every re-fetch despite no real content
   change.

See ledgerlight.ingestion.content_identity, ADR 0004, and
docs/phase-2/phase-2-report.md §1 for the full writeup.
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


def test_non_zip_non_html_content_identity_is_the_raw_bytes() -> None:
    body = b"%PDF-1.4 fake pdf bytes"
    assert content_identity_bytes(body, "application/pdf") == body


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


def _html_with_csrf_and_nonce_id(token: str, nav_id: str) -> bytes:
    return f"""<!DOCTYPE html><html><head><title>Example Corp</title>
<script>Liferay.authToken = '{token}';</script>
</head><body>
<nav id="{nav_id}_quickAccessNav">About Us</nav>
<p>Shareholding pattern as of Q1 2025.</p>
</body></html>""".encode()


def test_csrf_token_and_randomized_dom_id_do_not_change_identity_hash() -> None:
    # The exact real-world symptom: raw bytes differ purely because of a
    # per-request CSRF token (inside a <script>) and a randomized nav
    # element id (a tag attribute) -- neither is visible text.
    page_a = _html_with_csrf_and_nonce_id("jE6l8JTh", "cigw")
    page_b = _html_with_csrf_and_nonce_id("scNXdLRy", "pcfr")

    assert page_a != page_b
    assert content_identity_hash(page_a, "text/html") == content_identity_hash(page_b, "text/html")


def test_duplicated_title_text_in_body_does_not_change_identity_hash() -> None:
    # Real finding: one site non-deterministically duplicates its own
    # <title> text as a trailing body text node on some responses.
    without_dup = (
        b"<html><head><title>Example Corp</title></head>" b"<body><p>Content</p></body></html>"
    )
    with_dup = (
        b"<html><head><title>Example Corp</title></head>"
        b"<body><p>Content</p><p>Example Corp</p></body></html>"
    )
    assert content_identity_hash(without_dup, "text/html") == content_identity_hash(
        with_dup, "text/html"
    )


def test_genuinely_different_html_text_has_different_identity_hash() -> None:
    page_a = _html_with_csrf_and_nonce_id("token1", "nav1")
    page_b = page_a.replace(b"Q1 2025", b"Q2 2025")
    assert content_identity_hash(page_a, "text/html") != content_identity_hash(page_b, "text/html")


def test_script_and_style_tags_are_fully_excluded_from_html_identity() -> None:
    body = b"<html><body><style>.x{color:red}</style><p>Visible</p></body></html>"
    normalized = content_identity_bytes(body, "text/html")
    assert b"color:red" not in normalized
    assert b"Visible" in normalized
