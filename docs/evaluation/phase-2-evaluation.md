# Phase 2 Evaluation

All metrics below are computed against **SILVER** labels
(`label_source=ai_assisted_unreviewed`) unless marked GOLD. No gold
labels exist yet — see §13 (human-gold-review checkpoint) of
`docs/phase-2/phase-2-report.md` for the exact command and item counts
to review them.

## Label counts (silver)

241 silver label items over the real corpus, from
`scripts/labels_propose.py`:

| event_type | count |
|---|---|
| PLEDGE_UP | 28 |
| RPT_GROWTH | 22 |
| AUDIT_QUAL | 8 |
| AUD_RESIGN | 6 |
| ID_EXIT | 6 |
| FORENSIC | 7 |
| RATING_ACT | 4 |
| RESULT_DELAY | 4 |
| KMP_EXIT | 2 |
| none | 154 |

**GOLD label counts: 0** (pending human review).

## Split (company + time, never random)

13 groups (companies/sources), 115 dev / 112 validation / 14 test — see
`docs/phase-2/phase-2-report.md` for the full per-group breakdown and
why the split is imbalanced (one company's 217-page annual report
dominates one group; not forced to look even).

## Classification (silver, validation then once on test)

See `docs/phase-2/phase-2-report.md` §7 for the full per-class
precision/recall/F1/support tables and confusion matrices for all three
methods (rules baseline, TF-IDF+LR, DeBERTa zero-shot) — printed there
with raw command output, not summarized here. Headline finding: the
rules baseline trivially scores macro_f1=1.0 on validation, because it
IS the function that generated the silver labels in the first place —
reported as a known circularity, not real accuracy, until gold review
exists.

**Fine-tuning decision:** not attempted. Brief's own threshold is ≥50
positives/class to even consider it; the real corpus's largest
non-'none' class (PLEDGE_UP) has 28.

## Extraction (AUD_RESIGN, the one real worked extractor)

4 events, 7 fields, **0 failed verifications** against real spans.
Exact-match/normalized-match/coverage metrics against gold fields: not
computed — no gold-labelled fields exist yet (same human-review
dependency as classification).

## Entity resolution

Real bootstrap run: 12 company entities, 1 audit_firm entity, 3 mentions
all correctly resolved to the one real audit firm (2 via normalized-name
exact match, 1 via first-seen bootstrap). Pairwise precision/recall/F1
against exact-match-only: not computed — no labelled mention-pairs
(silver or gold) exist yet; the real corpus's entity surface is too thin
(effectively one audit firm, 12 companies with no real name variants
observed) to build a meaningful pair set from without inventing cases.
Documented as **not run**, not fabricated.

## Retrieval

30-query SILVER set, `scripts/retrieval_eval.py`:

| method | n | Recall@5 | Recall@10 | MRR |
|---|---|---|---|---|
| lexical (BM25) | 30 | 0.567 | 0.667 | 0.330 |
| vector | 30 | 0.333 | 0.467 | 0.210 |
| hybrid (RRF) | 30 | 0.533 | 0.633 | 0.258 |

## Limitations

- All metrics above are silver-label self-consistency checks, not true
  accuracy — gold review is pending (§13).
- Entity-resolution and extraction-field evaluation against gold are
  not run at all, for lack of any gold pairs/fields yet.
- The corpus is small (237 base documents, 2,591 chunks, 468 document
  versions) — per-class counts for 6 of 9 non-deferred event types are
  under 10, too small for any calibration curve or confidence interval.
