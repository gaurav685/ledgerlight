# Precision Review Results — KMP_EXIT, ID_EXIT, RPT_GROWTH

Real human review, `scripts/precision_review.py`, reviewer `Gaurav`,
28/28 items decided. Source: `data/manifests/precision-review-v1.jsonl`
(the fresh, excluded-against-every-prior-review sample built by
`scripts/build_precision_review_sample.py`; see
`docs/enhancements/precision-review/guide.md` for the per-type rules
used). Raw decisions: `docs/enhancements/precision-review/
precision-review-audit.jsonl`.

## The real result

| event_type | eligible (post-exclusion) | sampled | n scored (skips excluded) | correct | wrong-type | not-an-event | skipped | precision | 95% CI (Wilson) |
|---|---|---|---|---|---|---|---|---|---|
| KMP_EXIT | 2 | 2 | 1 | 0 | 1 | 0 | 1 | 0.000 | [0.000, 0.794] |
| ID_EXIT | 6 | 6 | 6 | 0 | 0 | 6 | 0 | 0.000 | [0.000, 0.390] |
| RPT_GROWTH | 293 | 20 | 18 | 0 | 0 | 18 | 2 | 0.000 | [0.000, 0.176] |

**Zero correct detections out of 25 scored items, across all three
types, on this fresh sample.** KMP_EXIT's one scored item was a real
event of a *different* type (wrong-type); every other scored item, for
both ID_EXIT and RPT_GROWTH, was not an event at all.

## Why Wilson, not this project's usual bootstrap

`ledgerlight.knowledge.classifier_eval.bootstrap_precision_ci` (seed 42,
2000 resamples) -- the method used everywhere else in this project for
a precision CI -- is degenerate at zero successes: resampling with
replacement from an all-failure sample always produces another
all-failure sample, so it reports `[0.000, 0.000]` regardless of `n`,
which understates real uncertainty at small `n` (most of all at
KMP_EXIT's `n=1`). The Wilson score interval for a single proportion
handles `p=0` correctly and is reported instead, specifically for this
boundary case. Both are point estimates of the same real 0/n result;
neither changes what was found.

## What this means

This is *worse* than the Phase 3 gold-validation estimate these
production methods were originally selected on
(`data/manifests/classifier-selection-gold-validation.json`:
KMP_EXIT 0.667 [0,1] n=3; ID_EXIT 0.333 [0,1] n=1; RPT_GROWTH 0.250
[0,0.5] n=3) -- and with far more real support this time (1, 6 and 18
scored items respectively, vs. 3, 1 and 3 before). None of the three
production detectors for these types cleared the reliability bar
before this review (`docs/modelling/event-reliability.md`); this fresh,
larger, untouched sample does not merely fail to clear it either -- it
measures 0 real precision on every item a human could actually score.

Consistent with this project's standing honest-scope position
(`docs/modelling/model-card.md`): no demonstrated predictive skill, no
event type in this corpus reliable enough for production use, and now
a real, disclosed precision measurement backing that up for these three
types specifically, not just an insufficient-support flag.

## Caveats, disclosed

- KMP_EXIT's `n=1` scored item is not a usable precision estimate on
  its own (hence the wide Wilson interval); the real finding here is
  the near-total absence of eligible KMP_EXIT candidates at all (2
  eligible after exclusion, out of the entire real corpus), not the
  single data point's precision.
- 3 of 28 sampled items were skipped by the reviewer (1 KMP_EXIT, 2
  RPT_GROWTH) and are excluded from every count above, per this
  project's standing convention that a skip is never evidence for or
  against a class (same rule `gold-labels-phase2.json` applies to
  `review_status='skipped'`).
- This sample excludes every item already touched by a prior human
  decision (Phase 2 gold set, frozen test split, hardening-doc-cited
  examples, Phase 6 AI-QA review pack) -- see the build step's own
  printed exclusion counts in the `enhancement: precision-review`
  commit. It cannot be re-used to evaluate a changed detector; the
  detector-freeze guard test
  (`tests/test_precision_review.py::test_detector_freeze_matches_current_code_and_artifact`)
  will fail loudly if one tries.
