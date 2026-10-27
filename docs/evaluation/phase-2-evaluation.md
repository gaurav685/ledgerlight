# Phase 2 Evaluation

Metrics below are marked **SILVER** (`label_source=ai_assisted_unreviewed`) or **GOLD**
(`label_source=human_reviewed`, set only by a human running `scripts/label_review.py` --
never by this tool). Gold now exists for **event classification only**: Gaurav reviewed 80
items (verified against the real database, not taken on claim) -- 50 accepted, 25 corrected,
2 rejected, 3 skipped. Field-level, entity-pair, and retrieval-query gold still don't exist
(no review mechanism for them has ever been built -- see "Entity resolution" and "Retrieval"
below, and `docs/release/release-gates.md`).

## Gold evaluation (event classification)

**Silver-label error rate** (all 77 decided items, any split): **35.1%** overall
(bootstrap 95% CI [24.7%, 45.5%], 10,000 resamples, seed 42). Per-class:

| class | decided | errors | rate | 95% CI | note |
|---|---|---|---|---|---|
| none | 41 | 4 | 0.098 | [0.024, 0.195] | |
| RPT_GROWTH | 12 | 8 | 0.667 | [0.417, 0.917] | |
| PLEDGE_UP | 7 | 4 | 0.571 | [0.143, 0.857] | |
| ID_EXIT | 6 | 5 | 0.833 | [0.500, 1.000] | |
| AUD_RESIGN | 6 | 2 | 0.333 | [0.000, 0.667] | |
| AUDIT_QUAL | 2 | 2 | 1.000 | -- | insufficient support (n<5) |
| FORENSIC | 1 | 1 | 1.000 | -- | insufficient support (n<5) |
| KMP_EXIT | 1 | 0 | 0.000 | -- | insufficient support (n<5) |
| RESULT_DELAY | 1 | 1 | 1.000 | -- | insufficient support (n<5) |
| RATING_ACT | 0 | 0 | n/a | -- | insufficient support (never reviewed) |

Dominant error pattern: the keyword-rule proposer over-fires false positives on positive
classes (`ID_EXIT`, `RPT_GROWTH`, `PLEDGE_UP`, `AUDIT_QUAL` are all majority-wrong, nearly all
corrected to `none`); `none` itself is well-calibrated. Full confusion table and discussion:
`docs/phase-2/phase-2-report.md` §19.2.

**Classifier gold metrics, frozen TEST split (n=14, never tuned on):**

| method | macro_f1 | 95% CI |
|---|---|---|
| rules_baseline | 0.635 | [0.432, 1.000] |
| tfidf_lr | 0.283 | [0.111, 0.544] |
| deberta_zero_shot | 0.472 | [0.417, 1.000] |

Gold test classes: `none` (9), `AUD_RESIGN` (4), `PLEDGE_UP` (1, insufficient support). Every
other class has 0 gold positives in test. Full per-class tables:
`docs/phase-2/phase-2-report.md` §19.3.

**Classifier gold metrics, validation-split gold subset (n=41, the items Gaurav actually
reviewed -- separate from and smaller than the full 111-item mixed silver+gold validation
split used for production selection below):**

| method | macro_f1 |
|---|---|
| rules_baseline | 0.312 |
| tfidf_lr | 0.195 |
| deberta_zero_shot | 0.399 |

On this thin gold-only subset `deberta_zero_shot` edges out `rules_baseline` -- **production
classifier selection is not changed** on this evidence: the full 111-item validation split
(the documented, reproducible selection mechanism) still selects `rules_baseline`, and
switching mechanisms on a thin, differently-distributed 41-item subset would itself be a form
of tuning-on-a-subset. Documented, not silent -- see
`docs/phase-2/phase-2-report.md` §19.3.

**The silver-vs-gold gap, demonstrated concretely:** once real gold corrections entered the
validation split (41 of 111 items), `rules_baseline`'s validation macro_f1 collapsed from
**1.000 (pure silver, perfectly circular) to 0.441** -- the clearest evidence in this project
for why silver metrics were never reported as real accuracy.

## Label counts

241 label items total (`scripts/labels_propose.py`). 80 are now **GOLD**
(`label_source=human_reviewed`, via `scripts/label_review.py` -- see
`docs/phase-2/phase-2-report.md` §19.1 for the exact decision/split breakdown), 161 remain
silver/pending.

By proposed event type, at proposal time (silver label counts, unchanged since labelling):

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

By final (corrected-where-applicable) event class, gold items only (n=75, excludes 2
rejected + 3 skipped):

| final_class | count |
|---|---|
| none | 58 |
| AUD_RESIGN | 5 |
| RPT_GROWTH | 4 |
| KMP_EXIT | 4 |
| PLEDGE_UP | 3 |
| ID_EXIT | 1 |

## Split (company + time, never random)

13 groups (companies/sources), 114 dev / 111 validation / 14 test (dev and validation each
lost one item: a dev `FORENSIC` and a validation `none` proposal were both reviewer-rejected
and are now correctly excluded by `load_split`) — see `docs/phase-2/phase-2-report.md` for
the full per-group breakdown and why the split is imbalanced (one company's 217-page annual
report dominates one group; not forced to look even).

## Classification -- current production selection (mixed silver+gold validation, n=111)

This is what `scripts/evaluate.py` actually uses to select the production classifier: the
full validation split, where 41 of 111 items are now gold-corrected and the rest remain
silver. Macro_f1 by method, **current** (after the gold-dev retrain, §19.4.3 of the Phase 2
report):

| method | macro_f1 | note |
|---|---|---|
| rules_baseline | 0.441 | down from 1.000 pre-gold -- see "silver-vs-gold gap" above |
| tfidf_lr | 0.202 | retrained on gold-corrected `dev`; see before/after below |
| deberta_zero_shot | 0.402 | unaffected by retraining (not trained) |

**Selected production classifier (by validation macro_f1): `rules_baseline`** (0.441,
unchanged from before the gold review -- still the best of the three on the full validation
split, by a much smaller margin than the old, circular 1.000 made it look).

Test (n=14, reported once, selected method only): `rules_baseline_TEST` macro_f1 = 0.635 (4/4
`AUD_RESIGN` correct, 1/1 `PLEDGE_UP` correct, 7/9 `none` correct, 2 `none` misclassified) --
**this is the real, gold number**, not the old circular 1.000; see "Gold evaluation" above for
the full breakdown and the equivalent `tfidf_lr`/`deberta_zero_shot` test numbers.

**Historical, superseded numbers** (pure silver, before any human review -- kept for the
retraining before/after record, `docs/phase-2/phase-2-report.md` §19.4.3): validation (n=112)
`rules_baseline`=1.000, `tfidf_lr`=0.243, `deberta_zero_shot`=0.175; test (n=14)
`rules_baseline_TEST`=1.000. Raw logs: `docs/phase-2/evidence/evaluate-run-final.log`.

**Retraining impact, isolated from the label changes** (same current validation labels, old
model vs new model): `tfidf_lr` macro_f1 0.199 -> 0.202, a negligible (+0.003) change --
21 dev-split gold corrections moved the model only marginally; most of the 0.243 -> ~0.2 drop
above is the validation *labels* changing (silver mislabels corrected by review), not the
retrained model regressing. Full reasoning: `docs/phase-2/phase-2-report.md` §19.4.3.

DeBERTa confidence distribution on validation: min=0.159, max=0.874,
mean=0.344. Per-class calibration not computed -- sample sizes (2-28
positives) are too small for a reliable curve.

Full per-class precision/recall/F1/support tables and confusion matrices: historical
(pre-review) numbers in `docs/phase-2/phase-2-report.md` §7b/§7c
(`docs/phase-2/evidence/evaluate-run-final.log`); current (post-gold-retrain) numbers in
`docs/phase-2/phase-2-report.md` §19.4.3
(`docs/phase-2/evidence/evaluate-run-after-gold-corrections.log`).

**Fine-tuning decision:** not attempted. Brief's own threshold is ≥50
positives/class to even consider it; the real corpus's largest
non-'none' class (PLEDGE_UP) has 28.

**Reproducibility:** confirmed for all three methods. `rules_baseline` and `tfidf_lr` are
fully deterministic (pure pattern matching; TF-IDF + `LogisticRegression` with a fixed
`random_state=42` and the deterministic `lbfgs` solver) -- re-running the validation
evaluation for both reproduced byte-identical metrics
(`docs/phase-2/evidence/evaluate-reproducibility-check.log`). A full second run of
`evaluate.py` including `deberta_zero_shot` (frozen weights, non-stochastic greedy inference)
was also completed and diffed against the first full run: every metric, confusion matrix, and
the production-classifier selection are byte-identical; the only diff line is the
weight-loading progress bar's own throughput readout, a timing artifact, not a metric
(`docs/phase-2/evidence/evaluate-full-rerun-diff.log`).

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
computed — `label_item_fields` has 0 rows (no field-level review mechanism exists at all, not
just unused). **DEFERRED_TO_PHASE_6**, see `docs/release/release-gates.md`.

## Entity resolution

Real bootstrap run: 12 company entities, 1 audit_firm entity, 3 mentions
all correctly resolved to the one real audit firm (2 via normalized-name
exact match, 1 via first-seen bootstrap). Pairwise precision/recall/F1
against exact-match-only: not computed — no entity-pair review table exists at all (not just
no labelled pairs); the real corpus's entity surface is too thin
(effectively one audit firm, 12 companies with no real name variants
observed) to build a meaningful pair set from without inventing cases either way.
**DEFERRED_TO_PHASE_6**, see `docs/release/release-gates.md`.

## Retrieval

30-query SILVER set, `scripts/retrieval_eval.py`:

| method | n | Recall@5 | Recall@10 | MRR |
|---|---|---|---|---|
| lexical (BM25) | 30 | 0.567 | 0.667 | 0.330 |
| vector | 30 | 0.333 | 0.467 | 0.210 |
| hybrid (RRF) | 30 | 0.533 | 0.633 | 0.258 |

No reviewed-query mechanism exists to promote any of these to gold -- queries are
`ai_constructed_unreviewed` silver only. **DEFERRED_TO_PHASE_6**, see
`docs/release/release-gates.md`.

## Limitations

- Event classification now has real gold metrics (test n=14, validation-gold-subset n=41),
  with real, sometimes-high error rates and some classes still at insufficient support
  (`RATING_ACT` never reviewed at all; `AUDIT_QUAL`/`FORENSIC`/`KMP_EXIT`/`RESULT_DELAY` all
  n<5) -- see "Gold evaluation" above.
- Extraction (field-level), entity resolution (pairwise), and retrieval (query-level) gold
  evaluation have no review mechanism at all yet, not just no reviewed items --
  **DEFERRED_TO_PHASE_6**, `docs/release/release-gates.md`.
- The corpus is small (237 base documents, 2,591 chunks, 468 document
  versions) — per-class counts for most non-`none` event types remain
  under 10 reviewed items, too small for a reliable calibration curve; confidence intervals
  are reported instead where support allows (n>=5), and "insufficient support" is stated
  honestly where it doesn't.
