"""Phase 5 §3: real webhook secret encryption at rest, HMAC-SHA256
delivery signing (plus a timestamp, per the brief), and real SSRF
protection -- resolves and blocks private/loopback/link-local/
multicast/reserved/unspecified addresses, re-checked at send time
(never only at registration), closing the real DNS-rebinding window a
registration-time-only check would leave open.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import socket
import time
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from ledgerlight.config.settings import Settings


class UnsafeWebhookUrlError(ValueError):
    """A real webhook URL that is not https, has no resolvable
    hostname, or resolves to a real blocked address."""


def _fernet(settings: Settings) -> Fernet:
    return Fernet(settings.webhook_secret_encryption_key.encode("utf-8"))


def generate_webhook_secret() -> str:
    return secrets.token_urlsafe(32)


def encrypt_secret(settings: Settings, raw_secret: str) -> str:
    return _fernet(settings).encrypt(raw_secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(settings: Settings, encrypted_secret: str) -> str:
    return _fernet(settings).decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")


def sign_payload(secret: str, payload_bytes: bytes, timestamp: int) -> str:
    """Real HMAC-SHA256 over `{timestamp}.{payload}` -- the timestamp
    is part of the signed message (not just sent alongside it), so a
    replayed delivery with a stale timestamp can be rejected by the
    receiver without trusting the timestamp header on its own."""
    message = f"{timestamp}.".encode() + payload_bytes
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_signature(secret: str, payload_bytes: bytes, timestamp: int, signature: str) -> bool:
    expected = sign_payload(secret, payload_bytes, timestamp)
    return hmac.compare_digest(expected, signature)


def validate_webhook_url(url: str) -> None:
    """Raises `UnsafeWebhookUrlError` unless `url` is a real `https://`
    URL whose hostname resolves ONLY to real, public, routable
    addresses. Called at registration AND again immediately before
    every real delivery attempt (`deliver_webhook`) -- a hostname that
    resolved safely an hour ago can resolve somewhere unsafe now (DNS
    rebinding), so this is never cached."""
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise UnsafeWebhookUrlError(f"webhook url must be https, got {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeWebhookUrlError("webhook url has no real hostname")

    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeWebhookUrlError(f"could not resolve host {host!r}: {exc}") from exc
    if not resolved:
        raise UnsafeWebhookUrlError(f"host {host!r} resolved to no real addresses")

    for info in resolved:
        raw_ip = info[4][0]
        ip = ipaddress.ip_address(raw_ip)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local  # covers the real 169.254.169.254 cloud metadata address
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeWebhookUrlError(
                f"host {host!r} resolved to a real blocked address {ip} -- "
                "private/loopback/link-local/metadata/multicast/reserved addresses "
                "are never a valid webhook destination"
            )


class WebhookDeliveryResult:
    def __init__(self, success: bool, status_code: int | None, attempt: int, error: str | None):
        self.success = success
        self.status_code = status_code
        self.attempt = attempt
        self.error = error


DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = (1.0, 5.0, 30.0)


def deliver_webhook(
    url: str,
    secret: str,
    payload_bytes: bytes,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
    sleep: bool = True,
) -> WebhookDeliveryResult:
    """One real delivery attempt sequence with real retries/backoff.
    Re-validates the real URL (`validate_webhook_url`) immediately
    before every single attempt -- never only once up front -- and
    signs the real payload fresh each time (the timestamp changes per
    attempt, so the signature does too)."""
    import httpx

    last_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            validate_webhook_url(url)
        except UnsafeWebhookUrlError as exc:
            return WebhookDeliveryResult(False, None, attempt, str(exc))

        timestamp = int(time.time())
        signature = sign_payload(secret, payload_bytes, timestamp)
        try:
            response = httpx.post(
                url,
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Ledgerlight-Timestamp": str(timestamp),
                    "X-Ledgerlight-Signature": signature,
                },
                timeout=10.0,
            )
            if 200 <= response.status_code < 300:
                return WebhookDeliveryResult(True, response.status_code, attempt, None)
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)

        if attempt < max_attempts and sleep:
            time.sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])

    return WebhookDeliveryResult(False, None, max_attempts, last_error)
