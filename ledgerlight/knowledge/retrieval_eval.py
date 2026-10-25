"""Retrieval evaluation: Recall@5, Recall@10 and MRR for lexical, vector
and hybrid search, against a set of (query, relevant_chunk_id) pairs.

The query set here is SILVER (ai_constructed_unreviewed) -- built
automatically from real non-'none' label proposals (see
ledgerlight.knowledge.labeling), not yet reviewed by a human. Per the
Phase 2 brief's human-gold-review checkpoint, this is reported as such;
promoting it to GOLD requires a human to review it via label-review (or
an equivalent manual pass), which this codebase cannot do on your
behalf. See docs/evaluation/phase-2-evaluation.md.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.models import Chunk, Filing, LabelItem
from ledgerlight.knowledge.retrieval import (
    BM25Index,
    ScoredChunk,
    hybrid_search,
    lexical_search,
    vector_search,
)

_EVENT_TYPE_QUERY_TEMPLATES: dict[str, str] = {
    "AUD_RESIGN": "statutory auditor resignation",
    "PLEDGE_UP": "promoter shareholding pledge increase",
    "KMP_EXIT": "key managerial personnel resignation",
    "ID_EXIT": "independent director resignation",
    "RATING_ACT": "credit rating downgrade or negative outlook",
    "RESULT_DELAY": "delay in filing financial results",
    "AUDIT_QUAL": "qualified or adverse audit opinion",
    "FORENSIC": "forensic audit ordered",
    "RPT_GROWTH": "related party transactions growth",
}


@dataclass
class GoldQuery:
    query: str
    relevant_chunk_id: UUID
    event_type: str
    as_of: dt.datetime
    company_id: UUID | None
    label_source: str = "ai_constructed_unreviewed"


def build_silver_queries(session: Session, limit: int = 30) -> list[GoldQuery]:
    rows = session.execute(
        select(LabelItem, Chunk.known_at)
        .join(Chunk, Chunk.id == LabelItem.chunk_id)
        .where(LabelItem.proposed_event_type_code != "none", LabelItem.chunk_id.is_not(None))
        .order_by(LabelItem.id)
    ).all()

    filings_by_version = {
        version_id: company_id
        for version_id, company_id in session.execute(
            select(Filing.version_id, Filing.company_id)
        ).all()
    }

    queries: list[GoldQuery] = []
    seen_event_types: set[str] = set()
    for item, known_at in rows:
        template = _EVENT_TYPE_QUERY_TEMPLATES.get(item.proposed_event_type_code)
        if template is None or item.chunk_id is None:
            continue
        queries.append(
            GoldQuery(
                query=template,
                relevant_chunk_id=item.chunk_id,
                event_type=item.proposed_event_type_code,
                as_of=known_at + dt.timedelta(days=1),
                company_id=filings_by_version.get(item.version_id),
            )
        )
        seen_event_types.add(item.proposed_event_type_code)
        if len(queries) >= limit:
            break
    return queries


@dataclass
class RetrievalMetrics:
    method: str
    n_queries: int
    recall_at_5: float
    recall_at_10: float
    mrr: float


def _rank_of(chunk_id: UUID, ranking: list[ScoredChunk]) -> int | None:
    for rank, scored in enumerate(ranking, start=1):
        if scored.chunk_id == chunk_id:
            return rank
    return None


def evaluate_all(
    session: Session, bm25_index: BM25Index, queries: list[GoldQuery]
) -> list[RetrievalMetrics]:
    def run_lexical(q: GoldQuery) -> list[ScoredChunk]:
        return lexical_search(bm25_index, q.query, q.as_of, q.company_id, top_k=10)

    def run_vector(q: GoldQuery) -> list[ScoredChunk]:
        return vector_search(session, q.query, q.as_of, q.company_id, top_k=10)

    def run_hybrid(q: GoldQuery) -> list[ScoredChunk]:
        return hybrid_search(session, bm25_index, q.query, q.as_of, q.company_id, top_k=10)

    results = []
    for name, fn in [
        ("lexical_bm25", run_lexical),
        ("vector", run_vector),
        ("hybrid_rrf", run_hybrid),
    ]:
        recall5 = recall10 = 0
        reciprocal_ranks = []
        for q in queries:
            ranking = fn(q)
            rank = _rank_of(q.relevant_chunk_id, ranking)
            if rank is not None and rank <= 5:
                recall5 += 1
            if rank is not None and rank <= 10:
                recall10 += 1
            reciprocal_ranks.append(1.0 / rank if rank is not None else 0.0)
        n = len(queries)
        results.append(
            RetrievalMetrics(
                method=name,
                n_queries=n,
                recall_at_5=recall5 / n if n else 0.0,
                recall_at_10=recall10 / n if n else 0.0,
                mrr=sum(reciprocal_ranks) / n if n else 0.0,
            )
        )
    return results
