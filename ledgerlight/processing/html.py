"""HTML text extraction. Never executes JavaScript — BeautifulSoup only
parses the static markup; `<script>`/`<style>` content is stripped before
extracting text."""

from __future__ import annotations

from bs4 import BeautifulSoup

EXTRACTOR_VERSION = "html-bs4-1"


def extract_html_text(html_bytes: bytes) -> str:
    soup = BeautifulSoup(html_bytes, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
