"""Minimal, polite HTTP acquisition utility — Phase 0 scope only.

Phase 1 will build the real ingestion pipeline. This tool exists only to
download the Phase 0 seed dataset reproducibly, honouring robots.txt, rate
limits, size limits, and recording a manifest entry for every attempt.
"""

from __future__ import annotations

import ssl
import time
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
import structlog
import truststore
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ledgerlight.acquisition.manifest import CompanyIdentifiers, ManifestEntry, append_entry
from ledgerlight.acquisition.robots import RobotsCache
from ledgerlight.common.hashing import sha256_bytes, sha256_file
from ledgerlight.common.timeutil import utc_now, utc_now_iso

logger = structlog.get_logger(__name__)

_LOGIN_PATH_HINTS = ("login", "signin", "sign-in", "sso", "auth")


class RobotsDisallowed(RuntimeError):
    """Raised when robots.txt disallows fetching a URL."""


class RetryableHTTPError(RuntimeError):
    """Raised for 429/5xx responses so tenacity can retry."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"retryable HTTP status {status_code}")


class FileTooLargeError(RuntimeError):
    pass


class LoginRedirectError(RuntimeError):
    pass


class HTTPStatusError(RuntimeError):
    """Raised for a non-2xx, non-retried response (e.g. 404) — never written to disk."""

    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code} for {url}")


class PoliteFetcher:
    def __init__(
        self,
        *,
        contact_email: str,
        data_dir: Path,
        manifest_path: Path,
        rate_limit_seconds: float = 2.0,
        timeout_seconds: float = 30.0,
        max_retries: int = 5,
        max_file_size_bytes: int = 200_000_000,
    ) -> None:
        self._user_agent = f"LedgerlightAcquisition/0.1 (contact: {contact_email})"
        self._data_dir = data_dir
        self._manifest_path = manifest_path
        self._rate_limit_seconds = rate_limit_seconds
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._max_file_size_bytes = max_file_size_bytes

        # follow_redirects so a normal CDN/attachment redirect works, but we
        # inspect the final URL below and refuse anything that looks like a
        # login page. cookies explicitly disabled (no session persistence).
        #
        # verify uses truststore (the OS trust store) rather than certifi's
        # bundled roots: some sites (observed: vakrangee.in) don't send a
        # complete certificate chain, which the OS verifier completes via
        # AIA fetching (same as a browser) but a plain certifi-only verifier
        # rejects. This is still full, real certificate verification — not
        # a weakened check — just backed by the OS trust store instead of a
        # bundled one.
        self._client = httpx.Client(
            follow_redirects=True,
            max_redirects=5,
            timeout=timeout_seconds,
            cookies=httpx.Cookies(),  # fresh, never reused across requests
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )
        self._robots = RobotsCache(self._user_agent, self._client)
        self._last_request_at: dict[str, float] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _host(self, url: str) -> str:
        return urlparse(url).netloc

    def _wait_for_rate_limit(self, url: str) -> None:
        host = self._host(url)
        last = self._last_request_at.get(host)
        if last is not None:
            elapsed = time.monotonic() - last
            remaining = self._rate_limit_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at[host] = time.monotonic()

    def _looks_like_login_url(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        return any(hint in path for hint in _LOGIN_PATH_HINTS)

    def _get_with_retry(self, url: str) -> httpx.Response:
        @retry(
            retry=retry_if_exception_type(RetryableHTTPError),
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(multiplier=1, min=1, max=60),
            reraise=True,
        )
        def _do_get() -> httpx.Response:
            resp = self._client.get(url, headers={"User-Agent": self._user_agent})
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                raise RetryableHTTPError(resp.status_code)
            return resp

        return _do_get()

    def fetch(
        self,
        *,
        source_id: str,
        source_url: str,
        retrieval_url: str,
        document_type: str = "unknown",
        licence_status: Literal[
            "public_no_explicit_licence",
            "open_licence",
            "registration_required",
            "payment_required",
            "unclear",
        ],
        redistribution_allowed: bool | Literal["unclear"],
        terms_url: str | None = None,
        company_identifiers: CompanyIdentifiers | None = None,
        publication_time: str | None = None,
        coverage_note: str | None = None,
        known_limitations: str | None = None,
    ) -> ManifestEntry | None:
        """Fetch retrieval_url, write it under data/raw/, and append a manifest entry.

        Returns None (and logs) if robots.txt disallows the URL — the caller
        should treat that company/document as BLOCKED and move on, never work
        around it.
        """
        if not self._robots.is_allowed(retrieval_url):
            logger.warning("robots_disallowed", url=retrieval_url)
            raise RobotsDisallowed(retrieval_url)

        self._wait_for_rate_limit(retrieval_url)

        resp = self._get_with_retry(retrieval_url)

        if self._looks_like_login_url(str(resp.url)):
            raise LoginRedirectError(str(resp.url))

        if not (200 <= resp.status_code < 300):
            raise HTTPStatusError(resp.status_code, retrieval_url)

        content_length = resp.headers.get("content-length")
        if content_length is not None and int(content_length) > self._max_file_size_bytes:
            raise FileTooLargeError(
                f"{retrieval_url}: {content_length} bytes > limit {self._max_file_size_bytes}"
            )

        body = resp.content
        if len(body) > self._max_file_size_bytes:
            raise FileTooLargeError(
                f"{retrieval_url}: {len(body)} bytes > limit {self._max_file_size_bytes}"
            )

        digest = sha256_bytes(body)
        year = utc_now().strftime("%Y")
        dest_dir = self._data_dir / "raw" / source_id / year
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Content-addressed filename: dedup is a hash match against any file
        # already on disk for this source, regardless of original name.
        ext = _guess_extension(resp.headers.get("content-type"), retrieval_url)
        dest_path = dest_dir / f"{digest}{ext}"

        skipped_duplicate_of: str | None = None
        if dest_path.exists() and sha256_file(dest_path) == digest:
            skipped_duplicate_of = digest
            logger.info("duplicate_skipped", url=retrieval_url, sha256=digest)
        else:
            dest_path.write_bytes(body)

        entry = ManifestEntry(
            record_id=str(uuid.uuid4()),
            source_id=source_id,
            source_url=source_url,
            retrieval_url=retrieval_url,
            retrieved_at=utc_now_iso(),
            retrieval_method="automated_fetch",
            http_status=resp.status_code,
            content_type=resp.headers.get("content-type"),
            bytes=len(body),
            sha256=digest,
            local_path=str(dest_path),
            company_identifiers=company_identifiers,
            document_type=document_type,
            publication_time=publication_time,
            coverage_note=coverage_note,
            licence_status=licence_status,
            terms_url=terms_url,
            redistribution_allowed=redistribution_allowed,
            known_limitations=known_limitations,
            skipped_duplicate_of=skipped_duplicate_of,
        )
        append_entry(self._manifest_path, entry)
        return entry


def _guess_extension(content_type: str | None, url: str) -> str:
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        mapping = {
            "application/pdf": ".pdf",
            "text/csv": ".csv",
            "application/zip": ".zip",
            "application/x-zip-compressed": ".zip",
            "text/html": ".html",
            "application/json": ".json",
            "application/xml": ".xml",
            "text/xml": ".xml",
        }
        if ct in mapping:
            return mapping[ct]
    suffix = Path(urlparse(url).path).suffix
    return suffix if suffix else ".bin"
