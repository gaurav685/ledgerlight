"""Content-identity hashing for dedup, as distinct from the raw-bytes
hash used for content-addressed storage.

Real finding (Phase 1 verification): re-fetching the exact same NSE
bhavcopy URL twice produced two different raw sha256 values even though
the inner CSV was byte-for-byte identical -- the server regenerates the
ZIP container with a fresh per-entry timestamp on every request. The raw
bytes genuinely differ (so storing/hashing them as received is correct
and not something to paper over), but treating that as "new content" for
versioning purposes created spurious DocumentVersion rows on every
re-fetch of an unchanged trading day. The same class of problem affects
single-entry ZIPs generally.

Real finding (Phase 2 preflight): the same class of problem affects
dynamic HTML pages that embed per-request CSRF tokens / session nonces
(e.g. `Liferay.authToken = 'jE6l8JTh'`) and randomized DOM element IDs
(e.g. `id="cigw_quickAccessNav"` vs `id="pcfr_quickAccessNav"`) -- 4 real
documents (2 IBBI NCLT listing pages, pnbhousing_ir and suzlon_ir
shareholding pages) churned a new version on every re-fetch despite no
real content change. Confirmed by diffing the raw HTML: every difference
was inside a `<script>` tag or a tag attribute, never in visible text.
Fixed the same way as the ZIP case: hash normalized MAIN TEXT (stripped
of script/style tags and tag attributes entirely, since BeautifulSoup's
`get_text()` only returns text nodes), not the raw markup. One further
real wrinkle found while verifying this empirically (not assumed): one
site (suzlon_ir) non-deterministically duplicates its own `<title>` text
as a trailing body text node on some responses but not others -- also
stripped, since a line that exactly matches the page's own <title> is a
known boilerplate/SEO artifact, not content.
"""

from __future__ import annotations

import io
import zipfile

from bs4 import BeautifulSoup

from ledgerlight.common.hashing import sha256_bytes


def _normalized_html_main_text(body: bytes) -> bytes:
    """Visible body text only, with the page's own <title> text excluded
    wherever it recurs (a real non-determinism found empirically, not
    assumed) -- see module docstring for the Phase 2 preflight finding.
    `<script>`/`<style>` content and all tag attributes are already
    excluded by construction: get_text() only returns text nodes."""
    soup = BeautifulSoup(body, "html.parser")
    title_text = soup.title.get_text().strip() if soup.title else None
    for tag in soup(["script", "style"]):
        tag.decompose()
    container = soup.body or soup
    text = container.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line and line != title_text]
    return "\n".join(lines).encode("utf-8")


def content_identity_bytes(body: bytes, mime: str) -> bytes:
    """Returns the bytes that should determine whether two downloads of
    the same URL represent the same logical content. For a single-entry
    ZIP, that's the inner entry's bytes (ignoring container-level
    metadata like per-entry timestamps). For HTML, that's the normalized
    main text (ignoring script/style/attribute-level volatility). For
    anything else, the raw bytes unchanged."""
    if mime == "application/zip":
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as zf:
                names = zf.namelist()
                if len(names) == 1:
                    return zf.read(names[0])
        except zipfile.BadZipFile:
            pass
        return body
    if mime == "text/html":
        return _normalized_html_main_text(body)
    return body


def content_identity_hash(body: bytes, mime: str) -> str:
    return sha256_bytes(content_identity_bytes(body, mime))
