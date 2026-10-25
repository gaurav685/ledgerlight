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
single-entry ZIPs generally; dynamic HTML pages with per-request
CSRF/session tokens are a related but distinct problem, not addressed
here -- see docs/ingestion/architecture.md.
"""

from __future__ import annotations

import io
import zipfile

from ledgerlight.common.hashing import sha256_bytes


def content_identity_bytes(body: bytes, mime: str) -> bytes:
    """Returns the bytes that should determine whether two downloads of
    the same URL represent the same logical content. For a single-entry
    ZIP, that's the inner entry's bytes (ignoring container-level
    metadata like per-entry timestamps); for anything else, the raw
    bytes unchanged."""
    if mime == "application/zip":
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as zf:
                names = zf.namelist()
                if len(names) == 1:
                    return zf.read(names[0])
        except zipfile.BadZipFile:
            pass
    return body


def content_identity_hash(body: bytes, mime: str) -> str:
    return sha256_bytes(content_identity_bytes(body, mime))
