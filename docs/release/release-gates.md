# Release Gates

Tracks known gaps that block (or partially block) treating Ledgerlight's
output as release-ready, independent of the per-phase exit-gate tables
in each phase report. A gap listed here stays listed until the work
that closes it actually lands -- this file is not a status dashboard
that gets marked "done" on a promise.

## Gap: no review infrastructure for field/entity-pair/retrieval-query gold labels

**Status:** open. **Deferred to:** Phase 6.

**What's missing:** `label_item_fields` (the table for field-level gold
review) has a schema but 0 rows -- nothing has ever written to it. There
is no table at all for labelled entity-mention-pairs or for a reviewed
retrieval-query set. Only event-level review (`label_items`, via
`scripts/label_review.py`) has ever been built or exercised.

**What this blocks:** gold evaluation for anything other than event
classification. Specifically:
- **Extraction** (exact-match/normalized-match accuracy, coverage, and
  verification-failure rate per field) has no gold field values to
  compare against, however many event-level gold labels exist.
- **Entity resolution** (pairwise precision/recall/F1 for the full
  method vs. exact-match-only) has no labelled mention-pairs, gold or
  silver, to evaluate against at all.
- **Retrieval** (Recall@5/Recall@10/MRR against a human-reviewed query
  set) currently only has an `ai_constructed_unreviewed` silver query
  set (see `docs/knowledge/retrieval.md`) -- there is no mechanism for
  a human to review or correct a retrieval query's relevance judgement.

**First seen:** Phase 2 report §17.1/§17.2 (gold-evaluation completion
pass) and §18.3 (this review-sample change). Not built as part of
either of those changes -- explicitly out of scope by instruction both
times.

**Closing this gap requires** (not built, scoped here only): a
`label_item_fields`-reviewing CLI path (currently schema-only); a
labelled-mention-pair table plus a review CLI for it; a
reviewed-retrieval-query table plus a review CLI for it. Each needs the
same silver/gold discipline as `label_items` -- `label_source`,
`reviewer`, `reviewed_at` -- and the same human-only restriction on who
may set `label_source='human_reviewed'`.

## Gap: event-level gold coverage is thin and uneven

**Status:** open, actively being filled.

As of this entry: 38 human-reviewed event items (26 accepted, 10
corrected, 2 rejected), 0 of them in the `test` split. Four event
classes (`ID_EXIT`, `RATING_ACT`, `RESULT_DELAY`, `AUDIT_QUAL`) had 0
gold items; two more (`KMP_EXIT`, `FORENSIC`) have 0 coverage reachable
from the `test`/`validation` splits at all (every silver item of those
classes landed in `dev` when the original split was built). A
deterministic 80-item sample (`data/manifests/label-review-sample-42.jsonl`,
seed 42) was built to target at least 4 reviewed items per class where
test/validation items exist -- see
`docs/phase-2/phase-2-report.md` §18 for the exact composition and
which classes still can't reach the minimum from this corpus's data.

**Closing this gap requires** a human actually reviewing the 42 new
items in the sample (and, ideally, acquiring more real `RATING_ACT`/
`FORENSIC` test/validation examples, since no amount of review can
create coverage that doesn't exist in the corpus).
