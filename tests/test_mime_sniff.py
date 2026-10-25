from __future__ import annotations

import zipfile
from io import BytesIO

from ledgerlight.processing.mime_sniff import is_html, is_pdf, is_zip, sniff_mime


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
