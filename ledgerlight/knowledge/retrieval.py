"""Hybrid retrieval: true BM25 (rank_bm25, a persisted index -- NOT
Postgres ts_rank, which is a different ranking function and is never
called "BM25" anywhere in this codebase or its docs) for lexical search,
a local CPU sentence-embedding model (pgvector cosine distance) for
vector search, and reciprocal rank fusion (RRF) for hybrid. A
point-in-time filter (known_at <= as_of) and an optional company filter
are applied to the CANDIDATE POOL before top-k selection in every mode --
see docs/knowledge/retrieval.md.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.embedding import embed_query
from ledgerlight.knowledge.models import Chunk, Filing

BM25_INDEX_PATH = Path("data/indexes/bm25_index.pkl")
RRF_K = 60


@dataclass
class ScoredChunk:
    chunk_id: UUID
    score: float


@dataclass
class BM25Index:
    chunk_ids: list[UUID]
    tokenized_corpus: list[list[str]]
    known_at: list[datetime]
    company_ids: list[set[UUID]]


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def build_bm25_index(session: Session, path: Path = BM25_INDEX_PATH) -> int:
    """Persists a real BM25 index (rank_bm25.BM25Okapi is rebuilt from
    the pickled tokenized corpus at query time -- pickling the BM25Okapi
    object itself is avoided since rank_bm25's internal state is a thin,
    easily-rebuilt wrapper and pickling the raw corpus is more robust
    across rank_bm25 versions)."""
    rows = session.execute(select(Chunk.id, Chunk.text, Chunk.known_at, Chunk.version_id)).all()

    filings_by_version: dict[UUID, set[UUID]] = {}
    for version_id, company_id in session.execute(
        select(Filing.version_id, Filing.company_id)
    ).all():
        filings_by_version.setdefault(version_id, set()).add(company_id)

    chunk_ids: list[UUID] = []
    tokenized_corpus: list[list[str]] = []
    known_at: list[datetime] = []
    company_ids: list[set[UUID]] = []

    for chunk_id, text, chunk_known_at, version_id in rows:
        chunk_ids.append(chunk_id)
        tokenized_corpus.append(_tokenize(text))
        known_at.append(chunk_known_at)
        company_ids.append(filings_by_version.get(version_id, set()))

    index = BM25Index(chunk_ids, tokenized_corpus, known_at, company_ids)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(index, f)
    return len(chunk_ids)


def load_bm25_index(path: Path = BM25_INDEX_PATH) -> BM25Index:
    with open(path, "rb") as f:
        index = pickle.load(f)  # noqa: S301 -- our own trusted local artifact
    if not isinstance(index, BM25Index):
        raise TypeError(f"{path}: expected a BM25Index pickle, got {type(index)!r}")
    return index


def _eligible_mask(index: BM25Index, as_of: datetime, company_id: UUID | None) -> list[bool]:
    mask = []
    for chunk_known_at, chunk_companies in zip(index.known_at, index.company_ids, strict=True):
        if chunk_known_at > as_of:
            mask.append(False)
            continue
        if company_id is not None and company_id not in chunk_companies:
            mask.append(False)
            continue
        mask.append(True)
    return mask


def lexical_search(
    index: BM25Index, query: str, as_of: datetime, company_id: UUID | None = None, top_k: int = 10
) -> list[ScoredChunk]:
    from rank_bm25 import BM25Okapi

    bm25 = BM25Okapi(index.tokenized_corpus)
    scores = bm25.get_scores(_tokenize(query))

    eligible = _eligible_mask(index, as_of, company_id)
    scored = [
        ScoredChunk(index.chunk_ids[i], float(scores[i]))
        for i in range(len(index.chunk_ids))
        if eligible[i]
    ]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:top_k]


def vector_search(
    session: Session, query: str, as_of: datetime, company_id: UUID | None = None, top_k: int = 10
) -> list[ScoredChunk]:
    query_vec = embed_query(query)

    stmt = select(Chunk.id, Chunk.embedding.cosine_distance(query_vec).label("distance")).where(
        Chunk.embedding.is_not(None), Chunk.known_at <= as_of
    )
    if company_id is not None:
        stmt = stmt.where(
            Chunk.version_id.in_(select(Filing.version_id).where(Filing.company_id == company_id))
        )
    stmt = stmt.order_by("distance").limit(top_k)

    rows = session.execute(stmt).all()
    return [
        ScoredChunk(cast(UUID, chunk_id), 1.0 - float(cast(float, distance)))
        for chunk_id, distance in rows
    ]


def reciprocal_rank_fusion(
    *rankings: list[ScoredChunk], k: int = RRF_K, top_k: int = 10
) -> list[ScoredChunk]:
    """Standard RRF: score(d) = sum over rankings containing d of
    1 / (k + rank), rank 1-based. Never depends on the underlying scores'
    scale, only each ranking's order -- so BM25 scores and cosine
    similarities combine without needing calibration."""
    fused: dict[UUID, float] = {}
    for ranking in rankings:
        for rank, scored in enumerate(ranking, start=1):
            fused[scored.chunk_id] = fused.get(scored.chunk_id, 0.0) + 1.0 / (k + rank)
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    return [ScoredChunk(chunk_id, score) for chunk_id, score in ordered[:top_k]]


def hybrid_search(
    session: Session,
    bm25_index: BM25Index,
    query: str,
    as_of: datetime,
    company_id: UUID | None = None,
    top_k: int = 10,
) -> list[ScoredChunk]:
    lexical = lexical_search(bm25_index, query, as_of, company_id, top_k=max(top_k, 20))
    vector = vector_search(session, query, as_of, company_id, top_k=max(top_k, 20))
    return reciprocal_rank_fusion(lexical, vector, top_k=top_k)
