from __future__ import annotations

import zipfile
from io import BytesIO

from ledgerlight.processing.mime_sniff import find_pdf_offset, is_html, is_pdf, is_zip, sniff_mime


def test_sniffs_real_pdf_magic_bytes() -> None:
    data = b"%PDF-1.4\n%fake but has the real magic bytes\n" + b"0" * 100
    mime = sniff_mime(data)
    assert is_pdf(mime)


def test_sniffs_real_zip_magic_bytes() -> None:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("x.txt", "hello")
    assert is_zip(sniff_mime(buf.getvalue()))


def test_sniffs_html_with_no_magic_bytes() -> None:
    data = b"<!DOCTYPE html><html><body>hi</body></html>"
    assert is_html(sniff_mime(data))


def test_html_extension_lie_is_not_trusted_as_pdf() -> None:
    # A file claiming to be a PDF by extension (not checked here at all --
    # sniff_mime never looks at a filename) but whose bytes are HTML.
    data = b"<html><body>not a pdf</body></html>"
    mime = sniff_mime(data)
    assert not is_pdf(mime)
    assert is_html(mime)


def test_csv_text_sniffed_as_csv() -> None:
    data = b"SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE\nINFY,EQ,100,110,95,105\n"
    assert sniff_mime(data) == "text/csv"


def test_plain_text_fallback() -> None:
    data = b"just some plain text with no commas or markup at all"
    assert sniff_mime(data) == "text/plain"


def test_embedded_pdf_after_html_loading_stub_is_sniffed_as_pdf() -> None:
    """Real case (an IBBI order URL, 2026-10-30): the server concatenates
    a tiny HTML/JS 'Loading...' stub directly in front of a complete,
    valid PDF in the same response body, no separation. Must be sniffed
    as a real PDF, not HTML -- the alternative leaked raw PDF binary
    (incl. NUL bytes, which Postgres rejects outright) into extracted
    page text."""
    stub = b'<html><head><script src="jquery.js"></script></head>'
    stub += b'<div id="loading">Loading...</div>\n'
    pdf = b"%PDF-1.7\r\n%\xb5\xb5\xb5\xb5\r\n1 0 obj\r\n<</Type/Catalog>>\r\n%%EOF"
    data = stub + pdf
    mime = sniff_mime(data)
    assert is_pdf(mime)
    assert not is_html(mime)


def test_find_pdf_offset_locates_embedded_signature() -> None:
    stub = b"some preamble bytes "
    data = stub + b"%PDF-1.4\n..."
    assert find_pdf_offset(data) == len(stub)


def test_find_pdf_offset_zero_for_a_clean_pdf() -> None:
    assert find_pdf_offset(b"%PDF-1.4\n...") == 0


def test_find_pdf_offset_none_when_absent() -> None:
    assert find_pdf_offset(b"<html><body>no pdf here</body></html>") is None


def test_find_pdf_offset_none_when_signature_is_far_into_a_large_blob() -> None:
    """A coincidental '%PDF-' byte sequence deep inside an unrelated large
    binary must NOT be treated as an embedded PDF."""
    data = b"x" * 5000 + b"%PDF-1.4\n..."
    assert find_pdf_offset(data) is None
