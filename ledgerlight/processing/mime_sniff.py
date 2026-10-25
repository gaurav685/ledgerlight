"""MIME sniffing by content, never by trusting the file extension — a
`.pdf` extension on an attacker-controlled download proves nothing."""

from __future__ import annotations

import filetype

# filetype's own magic-byte detection, plus the two text-based formats it
# doesn't sniff (HTML/CSV have no magic bytes) via a small content probe.
_ZIP_MIMES = {"application/zip"}
_PDF_MIMES = {"application/pdf"}


def sniff_mime(data: bytes) -> str:
    kind = filetype.guess(data)
    if kind is not None:
        return str(kind.mime)

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
