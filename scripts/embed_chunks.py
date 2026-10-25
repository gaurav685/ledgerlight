"""Populate chunks.embedding for every chunk missing one, via the pinned
local CPU sentence-embedding model. Idempotent (only embeds chunks with
embedding IS NULL)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.embedding import (  # noqa: E402
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    embed_texts,
)
from ledgerlight.knowledge.models import Chunk  # noqa: E402

BATCH_SIZE = 32


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        chunks = session.scalars(select(Chunk).where(Chunk.embedding.is_(None))).all()
        print(f"chunks needing embeddings: {len(chunks)}")

        embedded = 0
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i : i + BATCH_SIZE]
            vectors = embed_texts([c.text for c in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedding_model_name = EMBEDDING_MODEL_NAME
                chunk.embedding_model_version = EMBEDDING_MODEL_VERSION
                embedded += 1
            session.commit()

    print(f"embedded: {embedded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
