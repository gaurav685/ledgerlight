"""MIME sniffing by content, never by trusting the file extension — a
`.pdf` extension on an attacker-controlled download proves nothing."""

from __future__ import annotations

import filetype

# filetype's own magic-byte detection, plus the two text-based formats it
# doesn't sniff (HTML/CSV have no magic bytes) via a small content probe.
_ZIP_MIMES = {"application/zip"}
_PDF_MIMES = {"application/pdf"}

# Real server misconfiguration found 2026-10-30 (an IBBI order URL):
# a tiny HTML/JS "Loading..." stub -- meant to show a spinner while a
# real browser's embedded PDF viewer loads -- concatenated directly in
# front of a complete, valid PDF (full header through %%EOF) in the SAME
# response body, no separation. filetype.guess() only checks magic bytes
# at offset 0, so it misses this; without this check the HTML extractor
# ran on the whole blob and leaked raw PDF binary (incl. NUL bytes,
# which Postgres text columns reject outright) into DocumentPage.raw_text
# instead of real page text. A bound on how far into the body the PDF
# signature can appear avoids treating a coincidental "%PDF-" byte
# sequence deep inside an unrelated large binary as a real embedded PDF.
_EMBEDDED_PDF_SEARCH_WINDOW = 4096


def find_pdf_offset(data: bytes) -> int | None:
    """Byte offset of a `%PDF-` signature within the first
    `_EMBEDDED_PDF_SEARCH_WINDOW` bytes, or None. 0 for an ordinary,
    uncorrupted PDF; a small positive offset for the wrapper-stub case
    above; None for anything else -- including a large binary that
    happens to contain `%PDF-` far from its start, deliberately not
    treated as an embedded PDF."""
    idx = data.find(b"%PDF-")
    if 0 <= idx < _EMBEDDED_PDF_SEARCH_WINDOW:
        return idx
    return None


def sniff_mime(data: bytes) -> str:
    kind = filetype.guess(data)
    if kind is not None:
        return str(kind.mime)

    if find_pdf_offset(data) is not None:
        return "application/pdf"

    sample = data[:4096].lstrip()
    if sample[:1] in (b"<",) and (b"<html" in sample.lower() or b"<!doctype" in sample.lower()):
        return "text/html"

    try:
        text = data[:4096].decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"

    if "," in text.splitlines()[0] if text.splitlines() else False:
        return "text/csv"
    if "<html" in text.lower() or "<!doctype html" in text.lower():
        return "text/html"
    return "text/plain"


def is_pdf(mime: str) -> bool:
    return mime in _PDF_MIMES


def is_zip(mime: str) -> bool:
    return mime in _ZIP_MIMES


def is_html(mime: str) -> bool:
    return mime == "text/html"
