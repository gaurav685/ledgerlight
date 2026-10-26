# Hybrid Retrieval (Phase 2)

## Chunking

Page-aware (`ledgerlight/knowledge/chunking.py`): a chunk never crosses
a page boundary, `char_start`/`char_end` round-trip exactly to the
page's `document_pages.raw_text` (tested), `chunker_version` recorded.
Real run: 536 pages → 2,591 chunks.

## Lexical: true BM25

`rank_bm25.BM25Okapi`, a persisted index at `data/indexes/bm25_index.pkl`
(rebuildable, gitignored — run `python scripts/build_bm25_index.py`).
**This is named honestly as BM25 throughout this codebase and its docs
— it is never conflated with Postgres `ts_rank`, which is a different
ranking function this project doesn't use for lexical search**, even
though `chunks.tsv` (a `TSVECTOR` column) exists for potential
Postgres-side full-text filtering.

## Vector

A local CPU sentence-embedding model, `BAAI/bge-small-en-v1.5` (MIT
licensed, 384-dim), via `sentence-transformers`. Fetched automatically
on first use into the OS-default Hugging Face cache
(`~/.cache/huggingface/hub`, outside this repo) -- nothing to gitignore
inside the repo for it; re-fetching on a new machine needs only network
access to huggingface.co the first time a script imports this module. Model name/version are
recorded on every `chunks` row (`embedding_model_name`/
`embedding_model_version`) so a future re-embed under a different model
is traceable, not silent. Stored in `pgvector` (`Vector(384)`), queried
via cosine distance. Real run: all 2,591 chunks embedded.

## Hybrid: reciprocal rank fusion

`reciprocal_rank_fusion` (k=60, the standard default) combines the
lexical and vector rankings by rank position only — never by raw score
magnitude, so BM25 scores and cosine similarities combine without
needing calibration (tested: identical rank orders fuse identically
regardless of the underlying scores' scale).

## Point-in-time filter

`known_at <= as_of` (plus an optional company filter) is applied to the
**candidate pool before top-k selection** in every mode — a chunk whose
owning document version wasn't yet known as of the query's `as_of` date
is excluded before ranking ever runs, not filtered out of an
already-ranked top-k. Tested explicitly
(`tests/test_retrieval.py::test_point_in_time_filter_excludes_future_known_chunks`).

## Evaluation

A 30-query **SILVER** (`ai_constructed_unreviewed`) set, built
automatically from real non-'none' label proposals (each query is a
short natural-language description of an event type; the "relevant"
chunk is the real chunk that proposal came from) —
`ledgerlight/knowledge/retrieval_eval.py`. Promoting this to GOLD
requires a human review pass; see the Phase 2 report §13.

Real result (`scripts/retrieval_eval.py`), reported for all three per
the brief's explicit instruction, even though hybrid isn't best here:

| method | n | Recall@5 | Recall@10 | MRR |
|---|---|---|---|---|
| lexical (BM25) | 30 | 0.567 | 0.667 | 0.330 |
| vector | 30 | 0.333 | 0.467 | 0.210 |
| hybrid (RRF) | 30 | 0.533 | 0.633 | 0.258 |

Lexical BM25 wins outright on this corpus. A plausible reason: the
silver queries are short, keyword-shaped event descriptions (e.g.
"statutory auditor resignation") that match the real disclosure text's
own vocabulary closely, which favours exact-term lexical matching over
semantic embedding similarity; hybrid sits between the two rather than
improving on the better single method, since RRF can only help when the
two rankings disagree in complementary ways, not when one is
consistently stronger across the whole query set.
