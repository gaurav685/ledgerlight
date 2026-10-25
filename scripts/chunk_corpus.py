"""Chunk every document_version that has pages (PDF/HTML -- bhavcopy ZIPs
have none). Idempotent per (version, chunker_version)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import DocumentVersion  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.chunking import chunk_version  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        versions = session.scalars(
            select(DocumentVersion).where(
                DocumentVersion.mime_type.in_(["application/pdf", "text/html"])
            )
        ).all()

        total_pages = 0
        total_chunks = 0
        total_already = 0
        for version in versions:
            stats = chunk_version(session, version)
            total_pages += stats.pages_seen
            total_chunks += stats.chunks_created
            total_already += stats.pages_already_chunked

    print(f"versions_processed: {len(versions)}")
    print(f"pages_seen: {total_pages}")
    print(f"chunks_created: {total_chunks}")
    print(f"pages_already_chunked: {total_already}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
