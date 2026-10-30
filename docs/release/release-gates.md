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

**Status:** open, partially closed -- the 80-item sample is fully reviewed; real coverage
gaps remain where the corpus itself has no test/validation examples of a class.

The deterministic 80-item sample (`data/manifests/label-review-sample-42.jsonl`, seed 42) is
now fully reviewed: 50 accepted, 25 corrected, 2 rejected, 3 skipped (verified against the
database; see `docs/phase-2/phase-2-report.md` §19.1). This gave the `test` split its first
gold coverage (14 items: 9 `none`, 4 `AUD_RESIGN`, 1 `PLEDGE_UP`) and the `validation` split
41 gold items.

Measured silver-label error rates (§19.2 of the Phase 2 report) turned out to be real and, for
several classes, high: `ID_EXIT` 83.3%, `RPT_GROWTH` 66.7%, `PLEDGE_UP` 57.1% error, all with
real support (n>=6). `RATING_ACT` was never reviewed at all (0 items in `test`/`validation` to
pull from -- every `RATING_ACT` silver item landed in `dev`, which this sample's design
deliberately never draws new items from). `FORENSIC` similarly has 0 coverage reachable from
`test`/`validation`. `AUDIT_QUAL`, `KMP_EXIT`, `RESULT_DELAY` all remain at insufficient
support (n<5) even after this round.

**Closing this gap further requires**: acquiring more real `RATING_ACT`/`FORENSIC` corpus
documents whose silver proposals land in `test`/`validation` (no amount of review can create
coverage that doesn't exist in the corpus), and continued review to push
`AUDIT_QUAL`/`KMP_EXIT`/`RESULT_DELAY` past n=5. See
`docs/phase-2/phase-2-report.md` §19.4.2 for which event types are and aren't recommended as
reliable enough for Phase 3 consumption given the error rates measured so far.

## Gap: human spot-check of primary-outcome evidence completed before release

**Status:** open. **Deferred to:** Phase 6.

**What's missing:** every positive `IBBI_CIRP_ADMISSION` and `RATING_DOWNGRADE_D` row (the
primary outcome's two trigger types, see `docs/modelling/outcomes.md` §2) is listed with its
real evidence citation in `docs/modelling/outcome-evidence-review.csv`, but no human has
reviewed any row yet -- the `reviewer_verdict`/`reviewer_name`/`review_date`/`review_notes`
columns are all blank. `IBBI_CIRP_ADMISSION` detection is a disclosed heuristic (earliest order
per normalized case number), not a hand-verified legal classification; `RATING_DOWNGRADE_D` is
span-verified text-matched, not semantically verified.

**What this blocks:** treating the primary outcome label as ground truth for model training,
walk-forward evaluation, or release reporting. Until reviewed, every `PRIMARY_DISTRESS` positive
is a candidate, not a confirmed label.

**Closing this gap requires**: a human reviewer works through
`docs/modelling/outcome-evidence-review.csv` row by row, opens each cited `retrieval_url`/page/
span, and records a verdict, their name, and the review date in the corresponding columns. Must
not be done by Claude or any other AI agent -- same human-only restriction as gold-label review
elsewhere in this project (see the gap above). Must also be re-run against any new rows produced
once the full-universe IBBI discovery crawl (Phase 3 §3) finishes and is extracted.
