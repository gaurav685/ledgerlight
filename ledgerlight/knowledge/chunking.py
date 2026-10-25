"""Page-aware chunking: a chunk never crosses a page boundary, and its
char_start/char_end index into that page's document_pages.raw_text
exactly (round-trip tested -- see tests/test_chunking.py). Chunks are
created per document_version/page; re-running with the same
chunker_version is idempotent (skips pages that already have chunks at
that version)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.db.models import DocumentPage, DocumentVersion
from ledgerlight.knowledge.models import Chunk

CHUNKER_VERSION = "page-aware-para-1"

TARGET_CHUNK_CHARS = 1000
MAX_CHUNK_CHARS = 1400
OVERLAP_CHARS = 150

_PARA_SPLIT_RE = re.compile(r"\n\s*\n")


@dataclass
class ChunkSpan:
    char_start: int
    char_end: int
    text: str


def chunk_page_text(text: str) -> list[ChunkSpan]:
    """Pure function: splits on paragraph boundaries where possible,
    packing paragraphs up to TARGET_CHUNK_CHARS; a single paragraph
    longer than MAX_CHUNK_CHARS is hard-split with OVERLAP_CHARS overlap.
    Never crosses the page boundary -- `text` IS one page's raw_text."""
    if not text:
        return []

    paragraphs: list[tuple[int, int]] = []
    pos = 0
    for match in _PARA_SPLIT_RE.finditer(text):
        if match.start() > pos:
            paragraphs.append((pos, match.start()))
        pos = match.end()
    if pos < len(text):
        paragraphs.append((pos, len(text)))
    if not paragraphs:
        paragraphs = [(0, len(text))]

    spans: list[ChunkSpan] = []
    cur_start: int | None = None
    cur_end: int | None = None

    def flush() -> None:
        nonlocal cur_start, cur_end
        if cur_start is not None and cur_end is not None and cur_end > cur_start:
            spans.append(ChunkSpan(cur_start, cur_end, text[cur_start:cur_end]))
        cur_start = None
        cur_end = None

    for para_start, para_end in paragraphs:
        para_len = para_end - para_start

        if para_len > MAX_CHUNK_CHARS:
            flush()
            sub_pos = para_start
            while sub_pos < para_end:
                sub_end = min(sub_pos + TARGET_CHUNK_CHARS, para_end)
                spans.append(ChunkSpan(sub_pos, sub_end, text[sub_pos:sub_end]))
                if sub_end >= para_end:
                    break
                sub_pos = sub_end - OVERLAP_CHARS
            continue

        if cur_start is None:
            cur_start, cur_end = para_start, para_end
        elif (para_end - cur_start) <= TARGET_CHUNK_CHARS:
            cur_end = para_end
        else:
            flush()
            cur_start, cur_end = para_start, para_end

    flush()
    return spans


@dataclass
class ChunkingStats:
    pages_seen: int = 0
    chunks_created: int = 0
    pages_already_chunked: int = 0


def chunk_version(session: Session, version: DocumentVersion) -> ChunkingStats:
    stats = ChunkingStats()
    pages = session.scalars(select(DocumentPage).where(DocumentPage.version_id == version.id)).all()

    for page in pages:
        stats.pages_seen += 1
        existing = session.scalar(
            select(Chunk).where(
                Chunk.version_id == version.id,
                Chunk.page_number == page.page_number,
                Chunk.chunker_version == CHUNKER_VERSION,
            )
        )
        if existing is not None:
            stats.pages_already_chunked += 1
            continue

        for span in chunk_page_text(page.raw_text):
            session.add(
                Chunk(
                    version_id=version.id,
                    page_number=page.page_number,
                    char_start=span.char_start,
                    char_end=span.char_end,
                    text=span.text,
                    chunker_version=CHUNKER_VERSION,
                    known_at=version.known_at,
                )
            )
            stats.chunks_created += 1

    session.commit()
    return stats
