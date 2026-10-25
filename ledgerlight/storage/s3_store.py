"""Generic S3-compatible object storage — no Garage-specific calls.

Content-addressed, immutable keys: raw/<sha256[:2]>/<sha256><ext>. Never
overwrites; an object already present with the same hash is skipped.
Swapping Garage for AWS S3 (or anything else S3-compatible) later is a
configuration change only — this module never references Garage.
"""

from __future__ import annotations

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from ledgerlight.common.hashing import sha256_bytes
from ledgerlight.config.settings import Settings


class HashMismatchError(RuntimeError):
    """Raised if the object read back after upload doesn't hash-match."""


class ObjectStore:
    def __init__(self, settings: Settings) -> None:
        if not settings.s3_access_key_id or not settings.s3_secret_access_key:
            raise RuntimeError(
                "S3 credentials not configured — run scripts/garage_provision.py "
                "(or set LEDGERLIGHT_S3_ACCESS_KEY_ID/LEDGERLIGHT_S3_SECRET_ACCESS_KEY "
                "for a non-Garage S3 provider)."
            )
        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=f"http://{settings.s3_endpoint}",
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(signature_version="s3v4"),
            region_name=settings.s3_region,
        )

    @staticmethod
    def object_key(sha256: str, ext: str) -> str:
        ext = ext if ext.startswith(".") else f".{ext}" if ext else ""
        return f"raw/{sha256[:2]}/{sha256}{ext}"

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise

    def put_content_addressed(self, body: bytes, sha256: str, ext: str) -> tuple[str, bool]:
        """Upload body under its content-addressed key. Returns (key, was_new).

        If an object already exists at that key, it is never re-uploaded
        (the key is content-addressed, so existing content is by
        definition identical) — was_new is False in that case.
        """
        key = self.object_key(sha256, ext)
        if self.exists(key):
            return key, False

        self._client.put_object(Bucket=self._bucket, Key=key, Body=body)

        readback = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        actual = sha256_bytes(readback)
        if actual != sha256:
            raise HashMismatchError(f"{key}: expected {sha256}, got {actual} after upload")

        return key, True

    def get(self, key: str) -> bytes:
        body: bytes = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        return body

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)
