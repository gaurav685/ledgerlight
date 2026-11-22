# Precision Review Results — KMP_EXIT, ID_EXIT, RPT_GROWTH

## Method

A fresh, untouched sample (`data/manifests/precision-review-v1.jsonl`,
sha256 `000785feeae4c339155d068650f89fa1e4c6b1cd17415cc072978ac05c4a0608`
-- verified to match the file on disk before this report was written),
sampled deterministically (seed 42) from the current, frozen production
detector's own output (`data/manifests/precision-review-v1-detector.json`
-- verified to still match the checked-out code/artifact before this
report was written: `rules_baseline` / `keyword-rule-baseline` v3 for
KMP_EXIT and ID_EXIT; `tfidf_lr` / `tfidf-logreg-event-classifier` v1
(`data/models/tfidf_lr_v1.pkl`) for RPT_GROWTH), excluding every item
already touched by a prior human decision (Phase 2 gold label set, the
frozen test split, items cited as worked examples in the hardening
docs, the Phase 6 AI-QA review pack). One real human reviewer
("Gaurav", confirmed present on all 28/28 decisions in
`docs/enhancements/precision-review/precision-review-audit.jsonl` --
no row is missing a reviewer) decided each item: correct / wrong-type /
not-an-event / skip.

## The real result

| event_type | N reviewed (skips excluded) | correct | wrong-type | not-an-event | precision | Wilson 95% CI | bootstrap 95% CI* |
|---|---|---|---|---|---|---|---|
| KMP_EXIT | 1 | 0 | 1 | 0 | 0.000 | [0.000, 0.794] | [0.000, 0.000] |
| ID_EXIT | 6 | 0 | 0 | 6 | 0.000 | [0.000, 0.390] | [0.000, 0.000] |
| RPT_GROWTH | 18 | 0 | 0 | 18 | 0.000 | [0.000, 0.176] | [0.000, 0.000] |

\* `ledgerlight.knowledge.classifier_eval.bootstrap_precision_ci` (this
project's usual method, seed 42, 2000 resamples) is degenerate at zero
successes -- resampling with replacement from an all-failure sample
always produces another all-failure sample, so it reports `[0.000,
0.000]` regardless of `n`. Reported for comparison, per the task's own
request, but Wilson is the real-uncertainty estimate here; this is
disclosed, not a discrepancy to resolve.

**Zero correct detections out of 25 scored items, across all three
types.**

Companies represented (reviewed items only; skipped items' companies in
parentheses):

- KMP_EXIT: THERMAX x1 (skipped: BCG x1)
- ID_EXIT: THERMAX x6
- RPT_GROWTH: THERMAX x6, BCG x6, CGPOWER x4, GENSOL x2 (skipped:
  CGPOWER x2)

## Reliability bar verdict

Bar (`docs/modelling/event-reliability.md`): support >= 10 **and**
lower 95% bound >= 0.7 (this project's own bootstrap method, per that
doc's definition).

| event_type | support | lower 95% bound | verdict |
|---|---|---|---|
| KMP_EXIT | 1 | 0.000 | **FAIL** (support < 10; bound < 0.7) |
| ID_EXIT | 6 | 0.000 | **FAIL** (support < 10; bound < 0.7) |
| RPT_GROWTH | 18 | 0.000 | **FAIL** (bound < 0.7) |

**None pass.** No promotion-criteria documentation is added to
`docs/modelling/event-reliability.md` this step (the task's own
condition for that was a PASS). No change made to the primary risk
model.

## Error analysis

**No reviewer notes were recorded** -- every decision in the audit log
has `"note": null`, including the 3 skips. There is nothing to quote
from the reviewer. The patterns below come from this session's own
read-only inspection of the real chunk text behind each decided item
(via `Chunk.text`, same database the sample was built from) -- stated
plainly as that, not as the reviewer's reasoning. No code changed as a
result; recorded here as future work requiring a new sample, per the
task's own instruction.

**KMP_EXIT wrong-type (n=1, THERMAX).** The chunk lists plain
"Director... resigned" language (e.g. "Mr. Nawshir Mirza... Director of
the Company resigned w.e.f. July 22, 2024") without the whole-time-KMP
role specificity the taxonomy requires. The same person is confirmed
elsewhere in the corpus as a Non-Executive **Independent** Director who
ceased office -- i.e. a real event, but ID_EXIT, not KMP_EXIT.
`rules_baseline`'s resign/cease trigger matched on generic "Director"
language without checking role specificity strongly enough here.

**ID_EXIT not-an-event (n=6, all THERMAX).** Every one of the 6 is an
incidental footnote or cross-reference to the *same* single real
independent-director departure (Nawshir Mirza / Jairam Varadaraj,
ceased 21 July 2024), recurring across unrelated tables elsewhere in
the same annual report: a remuneration/sitting-fee footnote, a
related-party-disclosure list, a board skill-matrix, a director
appointment-date table, an attendance table. This is exactly the
residual limitation already disclosed in
`ledgerlight/knowledge/labeling.py`'s own module docstring --
"distinguishing 'dedicated disclosure' from 'incidental mention in an
unrelated table' needs document-level context this rule-based detector
doesn't have." This sample is the first real measurement of how much
that gap costs in practice: 6/6 of ID_EXIT's real-world flags in this
sample were exactly that gap, not a new failure mode.

**RPT_GROWTH not-an-event (n=18, THERMAX/BCG/CGPOWER/GENSOL).** Two
distinct sub-patterns, not one:
- Generic corporate-governance boilerplate with no RPT amounts at all
  (director remuneration policy, directors'-responsibility statement,
  e-voting/PAN-KYC procedural circulars, a CG compliance certificate,
  CG report headers, a code of conduct, a board skill-matrix
  narrative, an NGRBC penalty-disclosure table) -- lexical overlap with
  RPT-adjacent committee/disclosure vocabulary triggers the bag-of-
  words `tfidf_lr` classifier despite no quantified multi-period amount
  anywhere in the chunk. Seen in THERMAX and BCG items.
- SEBI/forensic-investigation narrative text, specific to CGPOWER and
  GENSOL's real distress/fraud-investigation filings (disputed
  inter-company fund transfers, a named individual's denial of
  investigation findings, forged lender conduct letters). These
  chunks genuinely discuss "transactions" in a forensic/legal-narrative
  sense -- lexically RPT-adjacent, but not the taxonomy's quantified
  2-period-amount comparison. A second, distinct false-positive driver
  from the boilerplate pattern above, concentrated in the two
  companies in this sample with real fraud-investigation history.

## Limitations

- **Precision only.** Recall is not measured by this review -- the
  sample is drawn from the detector's own positive flags; it says
  nothing about real events the detector missed entirely.
- **Small N**, most of all for KMP_EXIT (`n=1` after exclusion -- the
  real finding there is the near-total absence of eligible candidates,
  2 out of the entire corpus, not the single data point's precision).
- **Single reviewer.** No inter-rater reliability check; one person's
  judgment throughout.

## Resume-safe one-line summaries

- KMP_EXIT detector precision 0.000 (Wilson 95% CI 0.000-0.794, n=1,
  human-reviewed, held-out sample)
- ID_EXIT detector precision 0.000 (Wilson 95% CI 0.000-0.390, n=6,
  human-reviewed, held-out sample)
- RPT_GROWTH detector precision 0.000 (Wilson 95% CI 0.000-0.176, n=18,
  human-reviewed, held-out sample)

## Context: compared to the original gold-validation estimate

This is *worse* than the Phase 3 gold-validation estimate these
production methods were originally selected on
(`data/manifests/classifier-selection-gold-validation.json`: KMP_EXIT
0.667 [0,1] n=3; ID_EXIT 0.333 [0,1] n=1; RPT_GROWTH 0.250 [0,0.5] n=3)
-- and with far more real support this time (1, 6 and 18 scored items
respectively, vs. 3, 1 and 3 before). None of the three production
detectors for these types cleared the reliability bar before this
review (`docs/modelling/event-reliability.md`); this fresh, larger,
untouched sample does not merely fail to clear it either -- it measures
0 real precision on every item a human could actually score. Consistent
with this project's standing honest-scope position
(`docs/modelling/model-card.md`): no demonstrated predictive skill, no
event type in this corpus reliable enough for production use.

## Caveats, disclosed

- 3 of 28 sampled items were skipped by the reviewer (1 KMP_EXIT, 2
  RPT_GROWTH) and are excluded from every count above, per this
  project's standing convention that a skip is never evidence for or
  against a class (same rule `gold-labels-phase2.json` applies to
  `review_status='skipped'`).
- This sample excludes every item already touched by a prior human
  decision. It cannot be re-used to evaluate a changed detector; the
  detector-freeze guard test
  (`tests/test_precision_review.py::test_detector_freeze_matches_current_code_and_artifact`)
  will fail loudly if one tries.
