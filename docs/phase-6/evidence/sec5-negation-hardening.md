# Phase 6 Correction 1 §5 — negation and hypothetical handling

## The real finding that motivated this

Phase 6B's retrieval review flagged: "A THERMAX 'statutory auditor resignation'
query's own silver 'known-relevant' chunk literally reads 'There has been
**no** resignation of the statutory auditors during the year' — a real
silver-labeling false positive from keyword overlap without checking
negation." That chunk's own silver label comes from
`ledgerlight.knowledge.labeling`'s rule-based proposer (via
`build_silver_queries`, which just inherits whatever `LabelItem` the
proposer already produced — it has no logic of its own).

Developed and evaluated ONLY against the dev-split and gold-validation
split, per the brief's own explicit instruction — never against the frozen
test split (even though the original THERMAX finding's own retrieval item
happens to live on the test split; the negation chunk this fix is built
against is a **different**, real gold-reviewed chunk on the validation
split, and a real chunk on the dev split was also checked, see below).

## §5.1/§5.2 — the fix, and what it's built against

`ledgerlight.knowledge.evidence.is_negated_before` (new, shared): a
negating word ("no", "not", "nil", "never", "none") in the ~80 characters
immediately before a match, truncated at the nearest preceding sentence
boundary. Used by both real consumers:

1. **`ledgerlight.knowledge.labeling` (silver label proposer), v2 → v3**:
   `_aud_resign` and `_director_or_kmp_exit` now require a *non-negated*
   resign/cease match before counting it as evidence. Real gold
   dev/validation examples that motivated this:
   - Validation split: "(xviii) There has been no resignation of the
     statutory auditors during the year..." — a real CARO disclosure
     clause, gold-corrected from AUD_RESIGN to "none".
   - Validation split: "During the year under review, none of the
     Independent Directors of the Company have resigned before the
     expiry of their respective term(s)." — sits right next to a real,
     separate, gold-**accepted** ID_EXIT positive in the same chunk
     (Dr. Jairam Varadaraj / Nawshir Mirza's real tenure-completion
     departure) — confirms this negated phrasing is real and common in
     this corpus, not invented.

2. **`ledgerlight.knowledge.extraction` (the real AUD_RESIGN detector),
   v3 → v4**: the firm-anchored date window (§4's own fix) additionally
   requires a real, non-negated resign/cease word in that same window
   before extracting a date at all. Scanning the **whole real corpus**
   (2593 chunks) for what this actually changes found something bigger
   than negation alone: 40+ real chunks where a known audit-firm name
   merely co-occurs with an unrelated date — a signature block, a
   financial-statement note, a court-hearing date — with **no**
   "resign"/"cease" word anywhere in the chunk at all, previously still
   produced a `resignation_date`. Real example (Thermax's own audit-
   assurance signature block):
   ```
   For Price Waterhouse Chartered Accountants LLP
   Firm Registration Number: 012754N/500016
   Hirak Patwa
   Partner
   ...
   Date: July 04, 2025
   ```
   v3 extracted `resignation_date: "2025-07-04"` from this; v4 correctly
   extracts nothing (verified: no "resign"/"cease" anywhere in the
   chunk). The pure-negation case the brief names is also covered: "KPMG
   continues as our statutory auditor; there has been no resignation
   this year" with some unrelated nearby date no longer extracts that
   date either.

## §5.3 — re-evaluated on gold validation, before and after

Compared v2 (HEAD, pre-fix) against v3 (current) `propose_event_type`
head-to-head over the real, frozen 63-item gold dev/validation
`LabelItem` set:

```
BEFORE (v2): tp=4 fp=5 fn=8 tn=46  precision=0.444  recall=0.333
AFTER  (v3): tp=4 fp=5 fn=8 tn=46  precision=0.444  recall=0.333
0 errors fixed, 0 new errors introduced
```

**Honest result: zero measured change on this gold sample.** Investigated
why: the one gold item that looks like a textbook negation false positive
(the CARO clause above) was *already* rejected by v2's own, separate "a
date must exist somewhere in the chunk" requirement (`find_dates_in_text`
returns `[]` for that chunk — it has no date at all), independent of
negation. Confirmed via a second check: running v2-code and v3-code
head-to-head over **every one of the 2593 real chunks in the whole
corpus** (not just the 63 gold-reviewed ones) found zero chunks where the
label proposer's own prediction differs. The negation guard is real,
correct, and a genuine regression-safety improvement for the *label
proposer* specifically — it just doesn't change any currently-live
prediction, because v2's other independent requirements already happen to
exclude every negated occurrence present in this corpus today. A
preventative fix, not a retroactive one — reported honestly rather than
inflated.

The **extractor** fix (`extraction.py`, v3→v4) is a different story — see
the 40+ real chunks above, a genuine, measured, currently-live
improvement.

**Disclosed limitation found while validating this** (pre-existing in
§4's own v3 extractor fix, not introduced by §5): a real Vakrangee
covering letter has its date in the letterhead (top of a short, single-
topic page) and its firm/resign language later in the body, more than
`DATE_SEARCH_WINDOW_CHARS` (300) apart. Confirmed directly: running the
real current chunk for this exact page through both v3 and v4 gives
identical results — **neither** extracts a `resignation_date` from it
today. This is a real, disclosed gap in §4's own windowing design (not
something §5 made worse), flagged in `extraction.py`'s own
`DATE_SEARCH_WINDOW_CHARS` docstring for deliberate, separate follow-up
(widening the window risks reopening the original THERMAX "unrelated
date" bug it exists to prevent).

## §5.4 — re-ran the real pipeline

`python scripts/extract.py` (2026-11-07), under extractor v4:

```
chunks classified AUD_RESIGN by rules baseline: 6
chunks_processed: 6
chunks_already_extracted: 1
events_created: 5
fields_created: 9
fields_failed_verification: 0
review_items_created: 0
```

Real event counts by type, before → after:

| Event type | Before | After | Change |
|---|---|---|---|
| AUD_RESIGN | 12 | 17 | **+5** (new versions, `supersedes_event_id` set on the superseded rows — nothing deleted or overwritten) |
| SEBI_ORDER_AGAINST_COMPANY | 69 | 69 | 0 |
| IBBI_CIRP_ADMISSION | 31 | 31 | 0 |
| RATING_DOWNGRADE_D | 14 | 14 | 0 |
| BHAVCOPY_DISAPPEARANCE | 835 | 835 | 0 |
| SEVERE_DRAWDOWN | 7514 | 7514 | 0 |

Only AUD_RESIGN changed, as expected — this fix is scoped to that
detector alone. All 5 new events supersede a real prior event (never a
bare replacement); verified via `Event.supersedes_event_id`.

## §5.5 — retrieval labels proposed by AI stay silver

Already true architecturally, confirmed by direct code inspection, no
change needed: `ledgerlight.knowledge.retrieval_eval.build_silver_queries`
and `scripts/retrieval_review.py` never write to `LabelItem.label_source`
at all — they only *read* whatever a `LabelItem` already has. The only
code path that can ever set `label_source="human_reviewed"` is
`scripts/label_review.py`'s own human-review CLI (per
`ledgerlight.knowledge.labeling`'s own module docstring, unchanged by this
phase). A retrieval-proposed "known relevant" chunk inherits whatever
silver/gold status its underlying `LabelItem` already has — it can never
itself promote anything to gold.
