# Phase 6 Correction 1 §4 — field citation mismatches

## 3 real findings (from Phase 6B field review, now quarantined per §1)

| Field | Company | Problem |
|---|---|---|
| `resignation_date` | THERMAX | cited span is a Company Secretary/KMP resignation, not the statutory auditor |
| `order_document` | RELCAPITAL | cites a real SEBI order against a distinct, related legal entity ("Reliance Capital Asset Management Limited"/"Reliance Mutual Fund"), not Reliance Capital Limited |
| `order_document` | BCG (Brightcom) | cites a real but wholly unrelated Telangana HC writ petition — "Brightcom" never appears in it |

## THERMAX — root cause and fix

`extract_aud_resign_fields` (`ledgerlight/knowledge/extraction.py`) searched the
**whole chunk** for the first date-shaped string, independent of where (or
whether) the audit firm was mentioned. A chunk that also named an unrelated
KMP resignation picked up that date instead.

Fix: the date search now only looks within `DATE_SEARCH_WINDOW_CHARS` (300)
of the real firm match; no firm match, no date claim at all (matches this
module's own "never infer" rule). Bumped `EXTRACTOR_VERSION` to `"3"` so
`extraction_pipeline.py`'s existing supersession mechanism (new
Event+EventField, `supersedes_event_id` set, old row kept — never
overwritten) picks up and re-extracts every previously-ingested AUD_RESIGN
chunk under the fixed logic on the next real run.

Regression tests (`tests/test_extraction_adversarial.py`):
- `test_resignation_date_ignores_an_unrelated_date_far_from_the_firm_mention`
- `test_resignation_date_still_found_near_the_real_firm_mention`

## RELCAPITAL / BCG — root cause

Both `order_document` citations trace to the SAME real upstream bug, found
in `data/manifests/live_ingestion.jsonl`'s own `coverage_note`: these SEBI
documents were found via **SEBI's own title/keyword search** for a seed
company name ("Reliance Capital", "Brightcom Group") — a loose substring/
title match, not a real entity-level link. The resulting `Filing` row
still got `link_method="document_metadata"`, `confidence=1.0`, because the
*document's own* `bse_code`/`nse_symbol` fields were themselves stamped
from that same original (wrong) keyword match — the "corroborating"
metadata is circular, not independent.

- BCG: the search term "Brightcom Group" never appears anywhere in the
  document's real text at all (confirmed by direct reading).
- RELCAPITAL: the search term "Reliance Capital" is a real, genuine
  substring of the wrong entity's own longer name ("Reliance Capital Asset
  Management Limited") — a real name-collision no literal containment
  check can resolve.

## New verification layer: `ledgerlight/knowledge/field_citation_checks.py`

Three new, independent checks (never mutate `EventField.validation_status`
— that column is append-only history; failures route to the review queue
as new rows instead, per §4's own "nothing is overwritten"):

1. `verify_span_within_document` — the cited char range must really fit
   inside the cited page's real text. A zero-width span (char_start ==
   char_end) is a deliberate "whole document is the evidence" marker for
   every `SEBI_ORDER_AGAINST_COMPANY` `order_document` field (see
   `scripts/populate_outcomes.py`'s own docstring) — `unverifiable`, not a
   defect.
2. `verify_field_type_matches_schema` — the field's value must match the
   type its own event type's schema declares
   (`ledgerlight.knowledge.extraction_schemas.EVENT_TYPE_SCHEMAS`). The 3
   outcome-taxonomy event types have no declared schema at all — a real,
   disclosed gap, returned as `unverifiable`, never silently "validated".
3. `verify_order_document_names_company` — the real search term that found
   a `SEBI_ORDER_AGAINST_COMPANY` document must appear in the document's
   own real text (tried with normal whitespace, then with all whitespace
   stripped — real NCLT/SEBI PDF extraction sometimes drops spaces between
   words entirely, e.g. "INTHEMATTEROFM/S.BGRENERGYSYSTEMSLIMITED";
   without the stripped fallback this check produced confirmed false
   positives against real, correct citations).

**Deliberately scoped** to `SEBI_ORDER_AGAINST_COMPANY`'s `order_document`
field only (see `scripts/reverify_event_fields.py`). Trying rule 3 against
`IBBI_CIRP_ADMISSION`'s `admission_language` corpus produced 2 more
confirmed false positives from real legal-name punctuation variants this
check cannot resolve — "Krebs Bio-Chemicals & Industries Limited" vs a
recorded seed name of "Krebs Biochemicals and Industries Limited";
"Diamond Power & Infrastructure Ltd." vs "Diamond Power Infrastructure
Limited" — both verified by reading the real document text. Disclosed
limitation, not silently suppressed.

## Real sweep over all 134 stored `event_fields`

`python scripts/reverify_event_fields.py --apply` (2026-11-07):

```
field_type:unverifiable: 114   (no schema for the 3 outcome event types)
field_type:validated: 20
order_document_identity:failed: 1    (BCG — the real finding)
order_document_identity:unverifiable: 65
order_document_identity:validated: 68
span_bounds:unverifiable: 69   (all zero-width order_document spans)
span_bounds:validated: 65

--- 1 new review_queue item(s) created ---
  SEBI_ORDER_AGAINST_COMPANY:order_document failed order_document_identity
  -- event_field 155e1cf6-39cc-4dd6-b171-a568abef6157 (BCG)
```

Re-ran with `--apply` a second time: 0 new items (idempotent — no
duplicate for the same field+rule). Verified via
`scripts/review_queue.py list --item-type event_field`:

```
1 open item(s)
  id=b1d38de3-f741-4d99-8619-1379d445e455 type=event_field
  reason=correction1_sec4_order_document_identity priority=2
  ref=155e1cf6-39cc-4dd6-b171-a568abef6157
```

RELCAPITAL's own field is NOT newly flagged by this automated sweep (the
name-collision limitation above) — it stays exactly where §1's quarantine
already put it: `docs/phase-6/review-pack/field-review-audit.jsonl`, item
`11278fe7-1ae9-4f96-97db-82d4d3e11dce`, decision `unsupported`,
PENDING_HUMAN_REVIEW, never counted toward any gold metric.

Zero new `span_bounds` or `field_type` failures across all 134 real rows
— both are now permanent regression guards, not retroactive findings.

## Regression tests

- `tests/test_field_citation_checks.py` (18 tests): pure unit tests for
  `verify_field_type_matches_schema`; DB-integration tests for
  `verify_span_within_document` (in-bounds / out-of-bounds / zero-width /
  missing page) and `verify_order_document_names_company` (present /
  the real BCG case / the real BGR-Energy whitespace-artifact case / no
  pages); `seed_name_for_retrieval_url` against the real, frozen
  BCG/RELCAPITAL manifest entries.
- `tests/test_extraction_adversarial.py`: the 2 THERMAX regression tests
  above.
- Fixed a real, newly-exposed test fragility while running the full
  suite: `tests/test_knowledge_pipeline_integration.py`'s
  `test_full_pipeline_on_small_real_subset_produces_events_fields_entities`
  asserted the **global** `review_queue` had zero open `event_field`
  items — true before this section's real BCG review item existed, false
  after. Rescoped the assertion to the fields that specific test run
  itself created, matching its own stated intent.

All green: `test_knowledge_pipeline_integration.py`,
`test_extraction_adversarial.py`, `test_extraction_schemas.py`,
`test_prompt_injection_separation.py`, `test_field_citation_checks.py`,
`test_review_queue.py`.
