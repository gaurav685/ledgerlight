"""Tests for ledgerlight.api.webhooks -- Phase 5 §3/§9. Pure unit
tests for encryption, HMAC signing, and SSRF URL validation against
IP-literal/localhost hosts (no real network needed -- resolving those
is instant and local). One real-DNS case is `@pytest.mark.network`.
Delivery (`deliver_webhook`) is tested with `respx`, never a real
outbound HTTP call.
"""

from __future__ import annotations

import socket

import pytest
import respx
from httpx import Response

from ledgerlight.api import webhooks
from ledgerlight.config.settings import load_settings


@pytest.fixture
def settings():  # type: ignore[no-untyped-def]
    return load_settings()


def test_encrypt_decrypt_roundtrip(settings) -> None:  # type: ignore[no-untyped-def]
    secret = webhooks.generate_webhook_secret()
    encrypted = webhooks.encrypt_secret(settings, secret)
    assert encrypted != secret
    assert webhooks.decrypt_secret(settings, encrypted) == secret


def test_sign_and_verify_payload() -> None:
    secret = "a-real-test-secret"
    payload = b'{"hello":"world"}'
    signature = webhooks.sign_payload(secret, payload, 1700000000)
    assert webhooks.verify_signature(secret, payload, 1700000000, signature)


def test_verify_signature_fails_for_a_different_timestamp() -> None:
    secret = "a-real-test-secret"
    payload = b'{"hello":"world"}'
    signature = webhooks.sign_payload(secret, payload, 1700000000)
    assert not webhooks.verify_signature(secret, payload, 1700000001, signature)


def test_verify_signature_fails_for_a_tampered_payload() -> None:
    secret = "a-real-test-secret"
    signature = webhooks.sign_payload(secret, b'{"hello":"world"}', 1700000000)
    assert not webhooks.verify_signature(secret, b'{"hello":"evil"}', 1700000000, signature)


# --- SSRF protection (real, local DNS resolution -- no network marker needed) --


def test_validate_webhook_url_rejects_plain_http() -> None:
    with pytest.raises(webhooks.UnsafeWebhookUrlError, match="https"):
        webhooks.validate_webhook_url("http://example.com/hook")


def test_validate_webhook_url_rejects_loopback() -> None:
    with pytest.raises(webhooks.UnsafeWebhookUrlError):
        webhooks.validate_webhook_url("https://127.0.0.1/hook")


def test_validate_webhook_url_rejects_localhost() -> None:
    with pytest.raises(webhooks.UnsafeWebhookUrlError):
        webhooks.validate_webhook_url("https://localhost/hook")


def test_validate_webhook_url_rejects_the_real_cloud_metadata_address() -> None:
    with pytest.raises(webhooks.UnsafeWebhookUrlError):
        webhooks.validate_webhook_url("https://169.254.169.254/latest/meta-data")


def test_validate_webhook_url_rejects_a_private_rfc1918_address() -> None:
    with pytest.raises(webhooks.UnsafeWebhookUrlError):
        webhooks.validate_webhook_url("https://10.0.0.5/hook")


def test_validate_webhook_url_rejects_no_hostname() -> None:
    with pytest.raises(webhooks.UnsafeWebhookUrlError):
        webhooks.validate_webhook_url("https:///hook")


@pytest.mark.network
def test_validate_webhook_url_accepts_a_real_public_https_host() -> None:
    webhooks.validate_webhook_url("https://www.google.com/hook")


def test_validate_webhook_url_catches_dns_rebinding_between_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 5 §9's own named DNS-rebinding case: a host resolves to a
    real, safe public address the FIRST time it's checked (e.g. at
    registration), then an attacker repoints its DNS to a private
    address before the real send happens. Re-resolution at send time
    -- never a cached result -- must catch this."""
    calls = {"n": 0}

    def fake_getaddrinfo(host: str, port: int | None) -> list[tuple[object, ...]]:
        calls["n"] += 1
        addr = "93.184.216.34" if calls["n"] == 1 else "10.0.0.5"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    webhooks.validate_webhook_url(
        "https://rebinding-test.example.com/hook"
    )  # registration-time: safe
    with pytest.raises(webhooks.UnsafeWebhookUrlError):
        webhooks.validate_webhook_url(
            "https://rebinding-test.example.com/hook"
        )  # send-time: rebound


@respx.mock
def test_deliver_webhook_blocks_a_retry_rebound_mid_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same DNS-rebinding scenario, but through the real
    `deliver_webhook` retry loop: attempt 1 resolves safely and a real
    (mocked) HTTP call goes out; the host rebinds to a private address
    before attempt 2, which must be blocked WITHOUT a second real HTTP
    call ever being attempted -- proving the re-check runs fresh on
    every single attempt, not once per `deliver_webhook` call."""
    route = respx.post("https://rebinding-retry-test.example.com/hook").mock(
        return_value=Response(500)
    )
    calls = {"n": 0}

    def fake_getaddrinfo(host: str, port: int | None) -> list[tuple[object, ...]]:
        calls["n"] += 1
        addr = "93.184.216.34" if calls["n"] == 1 else "10.0.0.5"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    result = webhooks.deliver_webhook(
        "https://rebinding-retry-test.example.com/hook",
        "secret",
        b"{}",
        max_attempts=3,
        sleep=False,
    )
    assert not result.success
    assert result.attempt == 2
    assert result.error is not None and "blocked address" in result.error
    assert route.call_count == 1  # only the first, pre-rebinding attempt ever sent


# --- delivery (mocked HTTP via respx, never a real outbound call) -------------


@respx.mock
def test_deliver_webhook_succeeds_on_a_real_2xx_response() -> None:
    route = respx.post("https://1.1.1.1/hook").mock(return_value=Response(200))
    result = webhooks.deliver_webhook("https://1.1.1.1/hook", "secret", b"{}", sleep=False)
    assert result.success
    assert result.attempt == 1
    assert route.called


@respx.mock
def test_deliver_webhook_retries_on_failure_then_succeeds() -> None:
    route = respx.post("https://1.1.1.1/hook").mock(side_effect=[Response(500), Response(200)])
    result = webhooks.deliver_webhook("https://1.1.1.1/hook", "secret", b"{}", sleep=False)
    assert result.success
    assert result.attempt == 2
    assert route.call_count == 2


@respx.mock
def test_deliver_webhook_fails_after_max_attempts() -> None:
    respx.post("https://1.1.1.1/hook").mock(return_value=Response(500))
    result = webhooks.deliver_webhook(
        "https://1.1.1.1/hook", "secret", b"{}", max_attempts=2, sleep=False
    )
    assert not result.success
    assert result.attempt == 2
    assert result.error == "HTTP 500"


def test_deliver_webhook_never_sends_to_an_unsafe_url() -> None:
    """validate_webhook_url is re-checked right before sending, not
    only at registration -- a URL that is unsafe NOW fails closed
    without any real HTTP call ever being attempted."""
    result = webhooks.deliver_webhook("http://127.0.0.1/hook", "secret", b"{}", sleep=False)
    assert not result.success
    assert result.error is not None and "https" in result.error
