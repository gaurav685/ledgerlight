# Event Reliability Tiers

Every event record in this system carries a reliability tier:

- **VERIFIED**: the event itself is human-accepted gold
  (`label_source='human_reviewed'`, `review_status` in `accepted`/`corrected` --
  `rejected` items are not evidence for any class, see
  `docs/phase-2/phase-2-report.md` §19.2).
- **CANDIDATE**: detector output that has not been human-reviewed
  (`label_source='ai_assisted_unreviewed'`).

No event type may be described as **reliable** unless its gold-validation precision
(for the production classifier selected for that type, §1.3 of
`docs/phase-3/phase-3-report.md`) has a **lower 95% bootstrap confidence bound of at
least 0.7, with support of at least 10** gold-validation examples. This is a hard bar,
not a judgement call -- a type that misses it is reported as not yet reliable, however
promising its point estimate looks.

## Per-type gold-validation precision (production classifier per type, n=41 gold validation items)

$PRECISION_TABLE_PLACEHOLDER

## Which types meet the reliability bar

$RELIABILITY_VERDICT_PLACEHOLDER

## What this means downstream

Per Phase 3's feature policy (§4): the PRIMARY risk model may only use STRUCTURED and
RULE-VERIFIED features. EVENT-CANDIDATE features (anything built from an event that is
not VERIFIED) enter only in the ablation arm, explicitly labelled unverified, and can be
promoted to the primary feature set only for an event type that clears the reliability
bar above. As of this report, $PROMOTION_SUMMARY_PLACEHOLDER.
