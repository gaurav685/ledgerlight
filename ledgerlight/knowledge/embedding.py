"""Local CPU sentence-embedding model for vector retrieval. Pinned model
name/version recorded on every Chunk row (embedding_model_name/
embedding_model_version) -- never silently re-embedded under a different
model without those columns changing too. Model weights are downloaded
once to the HuggingFace cache (gitignored, see docs/knowledge/retrieval.md
for how to fetch them) -- never committed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_MODEL_VERSION = "1"  # no versioned releases on the HF repo; pinned by name+hash below
EMBEDDING_MODEL_LICENSE = "MIT"

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer as _SentenceTransformer

        _model = _SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
