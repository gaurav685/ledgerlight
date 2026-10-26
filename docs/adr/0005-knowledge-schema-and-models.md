# ADR 0005: Knowledge Schema and Model Choices (Phase 2)

## Status
Accepted (Phase 2).

## Context
Phase 2 needs a knowledge store (companies, filings, chunks, taxonomy,
events/fields, entities, review queue, labels, model registry) plus
real classification/extraction/entity-resolution/retrieval models,
without starting Phase 3's feature/score/outcome work.

## Decisions

### One database, one Alembic history
The Phase 2 schema (`ledgerlight/knowledge/models.py`) shares `Base`
with Phase 1's ingestion schema and lives in the same application
database and migration history. Dagster's own run/event storage stays
the one and only separate database, per ADR 0004 — there is no reason
to add a third database for Phase 2's tables, and doing so would make
cross-referencing (e.g. `event_fields.evidence_version_id` →
`document_versions.id`) require cross-database joins, which Postgres
doesn't support natively.

### `outcomes` and features/scores tables
Per the Phase 2 brief: "features and scores tables are created in Phase
3 together with their real definitions, not as empty placeholders."
`outcomes` is the one exception — its *schema* (table + constraints) is
created now because `events.id` is the FK target and the brief asked
for it explicitly, but **no rows are ever written to it in Phase 2**.
No features/scores table of any kind exists yet; it will be designed in
Phase 3 once real outcome definitions exist to design against, not
guessed at now.

### `label_items`/`label_item_fields` added beyond the brief's table list
The brief's §2 schema list doesn't name a labels table, but §4's
silver/gold annotation workflow and the label-review CLI need somewhere
to persist proposals, review decisions, and the dev/validation/test
split. Modelled after `events`/`event_fields`' own shape (same evidence
contract) rather than inventing a different pattern.

### Embedding model: `BAAI/bge-small-en-v1.5`
MIT licensed, 384-dim, runs on CPU in well under a second per chunk,
widely used and well-benchmarked for English retrieval. No GPU is
available in this environment, and the brief asks for a local CPU
model by name-example (`bge-small-en or similar`) — this is exactly
that example, not a substitution.

### Lexical search: real BM25, not `ts_rank`
`rank_bm25.BM25Okapi` over a persisted tokenized-corpus pickle. Chosen
over Postgres `ts_rank` because the brief explicitly requires the
ranking function actually called "BM25" to be true BM25, and flags
`ts_rank` as a *different* function that must never be mislabelled as
BM25. `chunks.tsv` (a `TSVECTOR` column) is still created, for any
future Postgres-side full-text filtering need, but no ranking in this
codebase is computed from it.

### Classification: DeBERTa-v3 zero-shot NLI, no fine-tuning
`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` (MIT licensed), via
`transformers`'s `zero-shot-classification` pipeline, CPU. Fine-tuning
was considered and explicitly rejected: the brief's own threshold for
even considering it is ≥50 positive examples per class; the real corpus's
largest non-'none' class (PLEDGE_UP) has 28. Attempting to fine-tune a
transformer on fewer than 30 examples per class would produce an
unreliable, overfit model and was correctly not attempted — see
`docs/evaluation/phase-2-evaluation.md`.

### Entity resolution: rapidfuzz, not a heavier library
`rapidfuzz.fuzz.token_sort_ratio` — fast, pure-C, no model download,
sufficient for name-similarity scoring at this corpus's scale. A
heavier approach (e.g. a learned matcher) isn't justified without
enough labelled mention-pairs to train or even properly evaluate one.

## Consequences
- Every Phase 2 table is queryable in the same database/transaction as
  Phase 1's ingestion data and Dagster-independent of Phase 1's
  separate-database decision.
- `outcomes` exists but is empty; any Phase 3 code reading it must
  handle zero rows correctly, not assume data exists.
- The classification and retrieval evaluation numbers in this phase are
  against SILVER labels only (see the Phase 2 report §13) — this is a
  known, explicitly reported limitation, not a model-choice problem.
