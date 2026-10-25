"""Unit tests for reciprocal rank fusion and the point-in-time filter --
pure functions, no DB needed."""

from __future__ import annotations

import datetime as dt
import uuid

from ledgerlight.knowledge.retrieval import (
    BM25Index,
    ScoredChunk,
    _eligible_mask,
    reciprocal_rank_fusion,
)


def _uuid(seed: int) -> uuid.UUID:
    return uuid.UUID(int=seed)


def test_rrf_chunk_ranked_first_in_both_lists_wins() -> None:
    a, b, c = _uuid(1), _uuid(2), _uuid(3)
    lexical = [ScoredChunk(a, 10.0), ScoredChunk(b, 5.0), ScoredChunk(c, 1.0)]
    vector = [ScoredChunk(a, 0.9), ScoredChunk(c, 0.5), ScoredChunk(b, 0.1)]

    fused = reciprocal_rank_fusion(lexical, vector, top_k=3)
    assert fused[0].chunk_id == a


def test_rrf_chunk_absent_from_one_list_still_scores() -> None:
    a, b = _uuid(1), _uuid(2)
    lexical = [ScoredChunk(a, 10.0)]
    vector = [ScoredChunk(b, 0.9)]
    fused = reciprocal_rank_fusion(lexical, vector, top_k=10)
    assert {s.chunk_id for s in fused} == {a, b}


def test_rrf_score_is_independent_of_raw_score_scale() -> None:
    # BM25 scores and cosine similarities live on wildly different scales;
    # RRF must only care about rank order, not magnitude.
    a, b = _uuid(1), _uuid(2)
    lexical_small_scale = [ScoredChunk(a, 0.001), ScoredChunk(b, 0.0005)]
    lexical_large_scale = [ScoredChunk(a, 1_000_000.0), ScoredChunk(b, 500_000.0)]

    fused_small = reciprocal_rank_fusion(lexical_small_scale, top_k=2)
    fused_large = reciprocal_rank_fusion(lexical_large_scale, top_k=2)
    assert [s.chunk_id for s in fused_small] == [s.chunk_id for s in fused_large]


def test_rrf_respects_top_k() -> None:
    ranking = [ScoredChunk(_uuid(i), float(10 - i)) for i in range(5)]
    fused = reciprocal_rank_fusion(ranking, top_k=2)
    assert len(fused) == 2


# --- point-in-time filter -------------------------------------------------


def _index_with_known_at(
    known_ats: list[dt.datetime], company_sets: list[set[uuid.UUID]]
) -> BM25Index:
    chunk_ids = [_uuid(i) for i in range(len(known_ats))]
    return BM25Index(
        chunk_ids=chunk_ids,
        tokenized_corpus=[["x"] for _ in known_ats],
        known_at=known_ats,
        company_ids=company_sets,
    )


def test_point_in_time_filter_excludes_future_known_chunks() -> None:
    as_of = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    past = dt.datetime(2023, 1, 1, tzinfo=dt.UTC)
    future = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)

    index = _index_with_known_at([past, future, as_of], [set(), set(), set()])
    mask = _eligible_mask(index, as_of, company_id=None)
    assert mask == [True, False, True]  # future excluded; exactly as_of included


def test_point_in_time_filter_with_company_filter_combines_both_conditions() -> None:
    as_of = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    past = dt.datetime(2023, 1, 1, tzinfo=dt.UTC)
    future = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    company_a = _uuid(100)
    company_b = _uuid(200)

    index = _index_with_known_at(
        [past, past, future],
        [{company_a}, {company_b}, {company_a}],
    )
    mask = _eligible_mask(index, as_of, company_id=company_a)
    # chunk 0: past + company_a -> eligible
    # chunk 1: past + company_b (wrong company) -> not eligible
    # chunk 2: future (even though company_a) -> not eligible
    assert mask == [True, False, False]
