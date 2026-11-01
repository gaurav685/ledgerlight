"""Phase 5 §3: signed document links. Authorizes first (the real
`DocumentVersion` row must exist), then issues one real, time-limited
presigned GET URL -- never a public bucket, never longer than the
brief's own 5-minute ceiling (`ObjectStore.presigned_get_url` itself
places no cap; this module is where the real ceiling is enforced).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as DbSession

from ledgerlight.config.settings import Settings
from ledgerlight.db.models import DocumentVersion
from ledgerlight.storage.s3_store import ObjectStore

MAX_EXPIRES_IN_SECONDS = 300


class DocumentVersionNotFoundError(LookupError):
    pass


def issue_signed_url(
    settings: Settings,
    db: DbSession,
    document_version_id: uuid.UUID,
    expires_in_seconds: int = MAX_EXPIRES_IN_SECONDS,
) -> tuple[str, int]:
    """Returns `(url, real_expires_in_seconds)` -- the real,
    enforced TTL, capped at `MAX_EXPIRES_IN_SECONDS` regardless of
    what the caller asked for."""
    version = db.get(DocumentVersion, document_version_id)
    if version is None:
        raise DocumentVersionNotFoundError(f"document version {document_version_id} not found")
    real_expires_in = min(expires_in_seconds, MAX_EXPIRES_IN_SECONDS)
    store = ObjectStore(settings)
    url = store.presigned_get_url(version.object_key, expires_in_seconds=real_expires_in)
    return url, real_expires_in
