# Precision Review v2 — Detector Fix, and Why There Is Nothing Left to Sample

## What changed, and why

Real human review of the v1 sample
(`docs/enhancements/precision-review/results.md`) found two
generalizable bugs, both fixed and disclosed here (never tuned on
evaluation data without saying so, same house convention as
`AUD_RESIGN`'s TEST-split disclosure in `labeling.py`):

1. **KMP_EXIT wrong-type** (`ledgerlight/knowledge/labeling.py`
   `PROPOSER_VERSION` 3→4): `_director_or_kmp_exit`'s character-window
   branch checked "some role near some resign" and "some name near
   some resign" *independently*, never that the role and the resign
   described the SAME person. Fixed: the role's nearest name and the
   resign's nearest name must now be the same name
   (`_same_person_resign_and_role`).
2. **ID_EXIT not-an-event, 6/6** (same version bump): a single real
   departure, disclosed once, recurs as a footnote-marker citation
   (`#Name ceased...`) across unrelated tables elsewhere in the same
   annual report. Fixed: the resigning/ceasing person's name must not
   be immediately preceded by a footnote marker (`_is_footnote_marker_prefixed`).
3. **RPT_GROWTH, 18/18 not-an-event**
   (`ledgerlight/knowledge/classifier.py`,
   `tfidf_lr_predict_rpt_growth_filtered`, filter version 1): `tfidf_lr`
   is a bag-of-words classifier with no quantified-amount requirement.
   Its RPT_GROWTH predictions are now ANDed with
   `labeling.rpt_growth_evidence_bar` -- the SAME rule `rules_baseline`
   already enforced, applied to `tfidf_lr`'s output for the first time.
   Not a new rule invented from the reviewed sample; its first
   application to a classifier that lacked it.

## Validated before adoption, full real corpus (2595 chunks)

| | before | after | change |
|---|---|---|---|
| KMP_EXIT (rules_baseline) | 5 | 3 | -2 |
| ID_EXIT (rules_baseline) | 10 | 6 | -4 |
| RPT_GROWTH (tfidf_lr) | 318 | 1 | -317 |

- The known false positives from v1's review were re-run against the
  new code: the 1 KMP_EXIT wrong-type item and 4 of 6 ID_EXIT
  not-an-event items now predict differently (no longer KMP_EXIT/
  ID_EXIT); all 18 RPT_GROWTH not-an-event items are now suppressed.
- Every real gold-validation/frozen-test KMP_EXIT and ID_EXIT true
  positive available was re-checked individually: **zero regressions**.
- 2 of the 6 ID_EXIT false positives are **not** fixed by this change
  (`59e248e5-...`, `2e212c99-...`) -- a different bug (an *enterprise*
  "ceasing" to be a related party, textually adjacent to an unrelated
  director's name, misread as that director ceasing office). Disclosed
  as a known residual gap, not chased further on 2 items -- fixing it
  would need company-name disambiguation, a materially bigger change
  than this round's scope.
- New regression tests: `tests/test_labeling.py` (4 new cases: the real
  KMP_EXIT/ID_EXIT false-positive patterns, and their "still matches"
  counterparts), `tests/test_classifier.py` (4 new cases for the
  RPT_GROWTH filter). Full suite: 442 unit + 377 integration passed, 0
  failed, after this change.

## The real result: v2's sample is empty

| event_type | eligible (post-exclusion) | sampled |
|---|---|---|
| KMP_EXIT | 0 | 0 |
| ID_EXIT | 0 | 0 |
| RPT_GROWTH | 0 | 0 |

Exclusions for v2 are v1's exclusions **plus a new source**: every
chunk already shown to a reviewer in a prior precision-review round
(`data/manifests/precision-review-v*.jsonl` -- "fresh" means never
shown before, in this round or any earlier one). v1's 28 sampled items
account for 28 of the 127 total excluded chunks this round.

After the fix, the entire real corpus has only 3 KMP_EXIT, 6 ID_EXIT
and 1 RPT_GROWTH chunk still flagged at all -- and every single one of
them is already excluded: either it is one of the handful of items
Phase 2/3 used for gold validation or classifier selection, or it is
one of the 28 items v1 already showed a human reviewer. **There is
nothing left in this corpus, under this detector, that a human has not
already seen.**

## What this means

This is not a dead end in the fix -- it is the real, honest size of
this corpus's signal for these three types. Fixing the two real bugs
found in v1 did not reveal a larger pool of genuine candidates; it
revealed that almost nothing in this tiny corpus (2595 chunks, a
handful of companies) survives a correctly-applied evidence bar for
KMP_EXIT, ID_EXIT or RPT_GROWTH. Getting a real, larger, fresh
precision estimate for these three types now requires **more real
documents** (more companies, more filings) -- not more detector
hardening, and not a smaller/laxer sample. Recorded here as the actual
next step, not resolved unilaterally.

v1's real result stands unchanged and is still the only measured
precision available: 0/25 correct (`docs/enhancements/precision-review/
results.md`). v2 produces no new precision number -- there was nothing
to measure against.
