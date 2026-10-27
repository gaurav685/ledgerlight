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

Real result, `scripts/select_classifiers.py` against gold validation items only (hardened
detector, after §1.4; raw predictions:
`docs/phase-3/evidence/select-classifiers-raw-predictions.json`; full per-class JSON:
`data/manifests/classifier-selection-gold-validation.json`):

| event_type | gold-validation support | selected method | precision | precision 95% CI | meets bar? |
|---|---|---|---|---|---|
| AUD_RESIGN | 0 | -- | -- | -- | no (no gold-validation data) |
| PLEDGE_UP | 0 | -- | -- | -- | no (no gold-validation data; also never proposed from free text, §1.4) |
| KMP_EXIT | 3 | rules_baseline | 0.667 | [0.000, 1.000] | no (support < 10) |
| ID_EXIT | 1 | rules_baseline | 0.333 | [0.000, 1.000] | no (support < 10) |
| RATING_ACT | 0 | -- | -- | -- | no (no gold-validation data) |
| RESULT_DELAY | 0 | -- | -- | -- | no (no gold-validation data) |
| AUDIT_QUAL | 0 | -- | -- | -- | no (no gold-validation data) |
| FORENSIC | 0 | -- | -- | -- | no (no gold-validation data) |
| RPT_GROWTH | 3 | tfidf_lr | 0.250 | [0.000, 0.500] | no (support < 10) |
| *none* (background class, not a red-flag event type) | 34 | deberta_zero_shot | 0.892 | [0.784, 0.974] | n/a -- not an event type |

`none`'s precision happens to clear the numeric bar (lower bound 0.784 >= 0.7 with
support 34 >= 10), but it is excluded from this framework on purpose: it is the
background/negative class, not a red-flag event type, and "reliably recognizing nothing
happened" is not the same claim as "reliably recognizing a specific governance event."

## Which types meet the reliability bar

**None.** Every one of the 9 real event types has either 0 gold-validation support
(`AUD_RESIGN`, `PLEDGE_UP`, `RATING_ACT`, `RESULT_DELAY`, `AUDIT_QUAL`, `FORENSIC`) or
support under the required 10 (`KMP_EXIT`: 3, `ID_EXIT`: 1, `RPT_GROWTH`: 3). This is a
direct, honest consequence of this corpus's size and the company+time split -- 41 gold
items in `validation` is not enough to give every class real coverage, and `RATING_ACT`/
`AUDIT_QUAL`/`FORENSIC`/`RESULT_DELAY`/`AUD_RESIGN`/`PLEDGE_UP` all happen to have their
gold items concentrated in `dev`/`test` rather than `validation` specifically. No type's
point estimate is treated as "basically reliable" just because the sample is thin --
the bar is a hard support-and-interval requirement, not a judgement call, and it is not
met.

## Stored events: tier and a real, gold-confirmed false positive

All 7 stored `AUD_RESIGN` events (4 `detector_version=1`, 3 `detector_version=2`
superseding 3 of the 4 originals -- see `ledgerlight/knowledge/extraction_pipeline.py`'s
module docstring and §1.4 of `docs/phase-3/phase-3-report.md`) are the only events in
this database. Checking each one's source chunk against the real gold-review record:

- **3 are VERIFIED**: their source (version, page) matches a gold-reviewed `label_items`
  row with `review_status` in `accepted`/`corrected` for `AUD_RESIGN` itself -- the real
  Vakrangee Price Waterhouse & Co resignation, recorded three times across slightly
  different chunks/pages of the same filing. Each has both `audit_firm` and
  `resignation_date`, both `validated`.
- **1 (the original v1-only event, `9f8f00a6-...`) is a demonstrated false positive, not
  a statistical estimate**: its source chunk is the Thermax KMP-roster-table row "Ms.
  Janhavi Khele - Company Secretary (Resigned w.e.f. April 18, 2025)" -- gold review
  explicitly corrected this chunk's proposal from `AUD_RESIGN` to `KMP_EXIT`. The event
  itself only ever had a `resignation_date` field (no `audit_firm` at all), which is
  exactly what the v1-to-v2 extraction-pipeline fix (§1.4) now refuses to materialize as
  an event. The old row is not deleted (immutability) but is flagged in `review_queue`
  (`item_type='event'`, `reason_code='gold_review_contradicts_classification'`) and has
  no `detector_version=2` successor.
- The 3 new `detector_version=2` events are the same 3 VERIFIED facts, re-extracted under
  the hardened gate, each linking `supersedes_event_id` back to its v1 predecessor.

Tagged as CANDIDATE (not yet gold-reviewed): 0 -- every event in this small corpus
happens to have a gold-reviewed source, purely because the 80-item review sample
(Phase 2 §18/§19) deliberately oversampled `AUD_RESIGN`-adjacent items. This will not
remain true once more detector output accumulates without matching review.

## What this means downstream

Per Phase 3's feature policy (§4): the PRIMARY risk model may only use STRUCTURED and
RULE-VERIFIED features. EVENT-CANDIDATE features (anything built from an event that is
not VERIFIED) enter only in the ablation arm, explicitly labelled unverified, and can be
promoted to the primary feature set only for an event type that clears the reliability
bar above. **As of this report, no event type clears that bar, so no EVENT-CANDIDATE
feature is eligible for promotion to the primary feature set** -- every governance-event
feature in the SEED track (§4) must be built and reported as EVENT-CANDIDATE/unverified,
shown with its tier, never as if it were reliable ground truth.
