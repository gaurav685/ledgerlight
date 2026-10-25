"""Link document_versions to companies (Filing rows), and backfill
BSE_CODE company_identifiers from document metadata where a company is
already resolvable by NSE_SYMBOL (bootstrapped from bhavcopy). CIN is not
recorded anywhere in the real corpus -- not fabricated here.

Link method/confidence:
- document_metadata: the acquisition pipeline recorded an nse_symbol/
  bse_code directly on the `documents` row (Phase 1's CompanyIdentifiers
  metadata) -- confidence 1.0, matched against company_identifiers'
  validity window as of the version's known_at.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentVersion
from ledgerlight.knowledge.models import CompanyIdentifier, Filing


@dataclass
class LinkFilingsStats:
    filings_created: int = 0
    filings_already_present: int = 0
    bse_codes_backfilled: int = 0
    unresolved: list[str] = field(default_factory=list)


def _resolve_company_by_identifier(
    session: Session, identifier_type: str, value: str, as_of: dt.date
) -> CompanyIdentifier | None:
    candidates = session.scalars(
        select(CompanyIdentifier).where(
            CompanyIdentifier.identifier_type == identifier_type, CompanyIdentifier.value == value
        )
    ).all()
    for candidate in candidates:
        if candidate.valid_from is not None and as_of < candidate.valid_from:
            continue
        if candidate.valid_to is not None and as_of >= candidate.valid_to:
            continue
        return candidate
    return None


def link_filings(session: Session) -> LinkFilingsStats:
    stats = LinkFilingsStats()

    rows = session.execute(
        select(DocumentVersion, Document)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            (Document.nse_symbol.is_not(None)) | (Document.bse_code.is_not(None)),
            Document.source_id != "nse_archives",
        )
    ).all()

    for version, document in rows:
        as_of = version.known_at.date()
        company_identifier = None

        if document.nse_symbol:
            company_identifier = _resolve_company_by_identifier(
                session, "NSE_SYMBOL", document.nse_symbol, as_of
            )

        if company_identifier is None and document.bse_code:
            company_identifier = _resolve_company_by_identifier(
                session, "BSE_CODE", document.bse_code, as_of
            )

        if company_identifier is None:
            stats.unresolved.append(f"{document.source_id}:{document.source_key}")
            continue

        company_id = company_identifier.company_id

        if document.bse_code:
            existing_bse = _resolve_company_by_identifier(
                session, "BSE_CODE", document.bse_code, as_of
            )
            if existing_bse is None:
                session.add(
                    CompanyIdentifier(
                        company_id=company_id,
                        identifier_type="BSE_CODE",
                        value=document.bse_code,
                        valid_from=None,
                        valid_to=None,
                        source_version_id=version.id,
                        note="backfilled from document metadata (Phase 1 acquisition)",
                    )
                )
                stats.bse_codes_backfilled += 1

        existing_filing = session.scalar(
            select(Filing).where(Filing.version_id == version.id, Filing.company_id == company_id)
        )
        if existing_filing is not None:
            stats.filings_already_present += 1
            continue

        session.add(
            Filing(
                version_id=version.id,
                company_id=company_id,
                link_method="document_metadata",
                confidence=1.0,
            )
        )
        stats.filings_created += 1

    session.commit()
    return stats
