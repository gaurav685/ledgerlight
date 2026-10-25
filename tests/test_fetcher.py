from __future__ import annotations

import ssl
from pathlib import Path

import httpx
import respx

from ledgerlight.acquisition.fetcher import (
    FileTooLargeError,
    HTTPStatusError,
    PoliteFetcher,
    RobotsDisallowed,
)

PDF_URL = "https://example.test/filings/report.pdf"
PDF_URL_COPY = "https://example.test/filings/report-mirror.pdf"
ROBOTS_URL = "https://example.test/robots.txt"


def _make_fetcher(tmp_path: Path, **overrides: object) -> PoliteFetcher:
    kwargs: dict[str, object] = dict(
        contact_email="test@example.com",
        data_dir=tmp_path / "data",
        manifest_path=tmp_path / "data" / "manifests" / "test.jsonl",
        rate_limit_seconds=0.0,
        max_retries=2,
        max_file_size_bytes=10_000,
    )
    kwargs.update(overrides)
    return PoliteFetcher(**kwargs)  # type: ignore[arg-type]


def _common_fetch_kwargs() -> dict[str, object]:
    return dict(
        source_id="example",
        source_url=PDF_URL,
        retrieval_url=PDF_URL,
        document_type="annual_report",
        licence_status="public_no_explicit_licence",
        redistribution_allowed="unclear",
    )


@respx.mock
def test_robots_disallow_is_honoured(tmp_path: Path) -> None:
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /filings/\n")
    )
    get_route = respx.get(PDF_URL)

    with _make_fetcher(tmp_path) as fetcher:
        try:
            fetcher.fetch(**_common_fetch_kwargs())
            raised = False
        except RobotsDisallowed:
            raised = True

    assert raised
    assert not get_route.called  # never even attempted the disallowed URL


@respx.mock
def test_429_triggers_backoff_then_succeeds(tmp_path: Path) -> None:
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(404))
    route = respx.get(PDF_URL)
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(200, content=b"pdf-bytes", headers={"content-type": "application/pdf"}),
    ]

    with _make_fetcher(tmp_path) as fetcher:
        entry = fetcher.fetch(**_common_fetch_kwargs())

    assert route.call_count == 2
    assert entry is not None
    assert entry.http_status == 200
    assert entry.bytes == len(b"pdf-bytes")


@respx.mock
def test_hash_is_recorded_and_file_written(tmp_path: Path) -> None:
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(404))
    respx.get(PDF_URL).mock(
        return_value=httpx.Response(
            200, content=b"hello-world", headers={"content-type": "application/pdf"}
        )
    )

    with _make_fetcher(tmp_path) as fetcher:
        entry = fetcher.fetch(**_common_fetch_kwargs())

    assert entry is not None
    import hashlib

    assert entry.sha256 == hashlib.sha256(b"hello-world").hexdigest()
    assert Path(entry.local_path).exists()
    assert Path(entry.local_path).read_bytes() == b"hello-world"


@respx.mock
def test_duplicate_content_is_skipped(tmp_path: Path) -> None:
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(404))
    respx.get(PDF_URL).mock(
        return_value=httpx.Response(
            200, content=b"same-bytes", headers={"content-type": "application/pdf"}
        )
    )
    respx.get(PDF_URL_COPY).mock(
        return_value=httpx.Response(
            200, content=b"same-bytes", headers={"content-type": "application/pdf"}
        )
    )

    manifest_path = tmp_path / "data" / "manifests" / "test.jsonl"
    with _make_fetcher(tmp_path, manifest_path=manifest_path) as fetcher:
        first = fetcher.fetch(**_common_fetch_kwargs())
        second = fetcher.fetch(
            **dict(_common_fetch_kwargs(), retrieval_url=PDF_URL_COPY, source_url=PDF_URL)
        )

    assert first is not None and second is not None
    assert second.skipped_duplicate_of == first.sha256
    assert first.local_path == second.local_path


@respx.mock
def test_oversized_file_is_rejected(tmp_path: Path) -> None:
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(404))
    big_body = b"x" * 50_000
    respx.get(PDF_URL).mock(
        return_value=httpx.Response(
            200,
            content=big_body,
            headers={"content-type": "application/pdf", "content-length": str(len(big_body))},
        )
    )

    with _make_fetcher(tmp_path, max_file_size_bytes=1_000) as fetcher:
        raised = False
        try:
            fetcher.fetch(**_common_fetch_kwargs())
        except FileTooLargeError:
            raised = True

    assert raised


@respx.mock
def test_404_is_not_written_to_disk_or_manifest(tmp_path: Path) -> None:
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(404))
    respx.get(PDF_URL).mock(return_value=httpx.Response(404, text="not found"))

    manifest_path = tmp_path / "data" / "manifests" / "test.jsonl"
    with _make_fetcher(tmp_path, manifest_path=manifest_path) as fetcher:
        raised = False
        try:
            fetcher.fetch(**_common_fetch_kwargs())
        except HTTPStatusError as exc:
            raised = True
            assert exc.status_code == 404

    assert raised
    assert not manifest_path.exists()
    assert list((tmp_path / "data" / "raw").glob("**/*")) == []


def test_client_verifies_tls_certificates(tmp_path: Path) -> None:
    """Regression guard: vakrangee.in's incomplete cert chain was fixed by
    switching to truststore, never by disabling verification. This must
    never silently become `verify=False` / `CERT_NONE` again."""
    with _make_fetcher(tmp_path) as fetcher:
        verify = fetcher._client._transport._pool._ssl_context  # type: ignore[attr-defined]
        assert isinstance(verify, ssl.SSLContext)
        assert verify.verify_mode == ssl.CERT_REQUIRED
        assert verify.check_hostname is True
