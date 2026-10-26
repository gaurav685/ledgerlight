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

Validation (n=112), macro_f1 by method:

| method | macro_f1 | note |
|---|---|---|
| rules_baseline | 1.000 | circular -- it IS the function that generated the silver labels |
| tfidf_lr | 0.243 | trained on `dev` (115 items), independent of the proposer |
| deberta_zero_shot | 0.175 | zero-shot NLI, no fine-tuning, worse than both others on this corpus |

**Selected production classifier (by validation macro_f1): `rules_baseline`**
— selected mechanically by the evaluation script, but flagged explicitly
as a circularity, not a real accuracy claim, pending gold review.

Test (n=14, reported once, selected method only): `rules_baseline_TEST`
macro_f1 = 1.000 (4 AUD_RESIGN, 2 PLEDGE_UP, 1 ID_EXIT, 7 none, all
correct) -- same circularity caveat applies.

DeBERTa confidence distribution on validation: min=0.159, max=0.874,
mean=0.343. Per-class calibration not computed -- sample sizes (2-28
positives) are too small for a reliable curve.

Full per-class precision/recall/F1/support tables and confusion
matrices for all three methods are in
`docs/phase-2/phase-2-report.md` §7b/§7c, with the raw command output in
`docs/phase-2/evidence/evaluate-run-final.log`.

**Fine-tuning decision:** not attempted. Brief's own threshold is ≥50
positives/class to even consider it; the real corpus's largest
non-'none' class (PLEDGE_UP) has 28.

**Reproducibility:** `rules_baseline` and `tfidf_lr` are both fully
deterministic (pure pattern matching; TF-IDF + `LogisticRegression`
with a fixed `random_state=42` and the deterministic `lbfgs` solver) --
re-running the validation evaluation for both reproduced byte-identical
metrics (`docs/phase-2/evidence/evaluate-reproducibility-check.log`).
`deberta_zero_shot` is frozen-weight, non-stochastic greedy inference,
so it is expected to reproduce identically too, but was not re-run a
second time given its real cost in this environment (~1.5 hours after
fixing the `TOKENIZERS_PARALLELISM` bug below) -- disclosed as a
pragmatic, not a correctness, limitation.

**Real bug found and fixed during this evaluation run:** with
`TOKENIZERS_PARALLELISM` unset, the DeBERTa zero-shot pipeline's
Rust tokenizer spawned a multiprocessing worker that resolved to an
unrelated Python 3.11 interpreter on this machine, turning the expected
~20-minute run into a 13+ hour stall. Fixed in
`ledgerlight/knowledge/classifier.py` by setting
`TOKENIZERS_PARALLELISM=false` before constructing the pipeline; see
`docs/phase-2/phase-2-report.md` §1 and §10.

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
