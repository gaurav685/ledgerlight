"""Phase 5 §3: the signed-document-link endpoint. Document versions
are real, global reference data (no RLS) -- gated behind
VIEW_DOSSIER, since the only real reason a tenant user needs a raw
document link is to inspect cited evidence."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from ledgerlight.api import audit, rbac
from ledgerlight.api.deps import Identity, get_db, require_permission
from ledgerlight.api.documents import DocumentVersionNotFoundError, issue_signed_url
from ledgerlight.api.schemas import SignedDocumentLinkOut
from ledgerlight.config.settings import load_settings

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.get("/{document_version_id}/signed-url", response_model=SignedDocumentLinkOut)
def get_signed_document_url(
    document_version_id: uuid.UUID,
    identity: Identity = Depends(require_permission(rbac.VIEW_DOSSIER)),
    db: DbSession = Depends(get_db),
) -> SignedDocumentLinkOut:
    settings = load_settings()
    try:
        url, expires_in = issue_signed_url(settings, db, document_version_id)
    except DocumentVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Real local dev without S3 credentials configured -- never a 500
        # that looks like a server bug; this is a real config gap.
        raise HTTPException(
            status_code=503, detail=f"object storage not configured: {exc}"
        ) from exc

    audit.write_audit_log(
        db,
        identity.tenant_id,
        "document_link_issued",
        actor_user_id=identity.user_id,
        actor_api_key_id=identity.api_key_id,
        target_type="document_version",
        target_id=str(document_version_id),
    )
    return SignedDocumentLinkOut(url=url, expires_in_seconds=expires_in)
