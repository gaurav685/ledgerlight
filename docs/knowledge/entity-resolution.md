# Entity Resolution (Phase 2)

`ledgerlight/knowledge/entity_resolution.py`. Matching runs in a fixed
order, never skipped:

1. **Deterministic identifiers** — ISIN, CIN, DIN, ICAI firm
   registration number, NSE symbol (with its validity period via
   `company_identifiers`). An identifier match is checked first and
   wins outright if unambiguous.
2. **Normalization rules** (`normalize_name`) — strips legal suffixes
   (Ltd/Limited/Pvt/LLP/& Co/Chartered Accountants), honorifics
   (Mr/Mrs/Ms/Dr), punctuation, and collapses whitespace, case-
   insensitively. An exact match after normalization wins if
   unambiguous.
3. **Similarity scoring with blocking** (rapidfuzz `token_sort_ratio`,
   blocked by `entity_type`) — only reached if neither earlier stage
   resolved the mention.

## Thresholds

Tuned on validation pairs (the real Vakrangee/CG Power/audit-firm
examples surfaced while building this, plus synthetic boundary cases in
`tests/test_entity_resolution.py`):

- **auto-link**: fuzzy score ≥ 92
- **review**: 75 ≤ fuzzy score < 92 — queued, never auto-linked
- **reject**: fuzzy score < 75 — no link, no review item

Nothing below the auto-link threshold is ever auto-merged.

## Conflicts

`detect_identifier_conflict` flags the case where the *same* identifier
value (e.g. a DIN) is already associated with an entity whose display
name doesn't match (normalized) the newly claimed name — a real
corporate-filings risk (two different people's details attached to one
DIN by a typo, or the same DIN spelled two ways). Always queued
(`review_queue`, `reason_code=identifier_name_conflict`), never
auto-merged.

## Merges

`entity_merges` is reversible: `merge_entities` records
`source_entity_id`/`target_entity_id`/`reason`/`actor`;
`unmerge_entities` sets `reversed_at`/`reversed_by`. Nothing is ever
deleted. Attempting to unmerge an already-reversed merge raises.

## Real run and findings

`scripts/resolve_entities.py` bootstraps real entities from Phase 2's
own output: 12 company-type entities (from the 22 real filings'
distinct companies) and 1 audit_firm-type entity. 3 real audit_firm
mentions (all "Price Waterhouse & Co Chartered Accountants LLP") — the
first bootstraps the entity (`method=manual`), the next two correctly
resolve to the *same* entity via normalized-name exact match
(`method=normalized_name`, `score=100`), demonstrating the
matching-order precedence for real, not just in a unit test. Idempotent.

**Two real bugs found while testing this:**
1. A `\b` regex word-boundary anchor placed immediately before `&`
   (`r"\b& co\.?\b"`) can never match, because `&` and the space before
   it are both non-word characters — there's no word/non-word
   transition for `\b` to anchor on. "Price Waterhouse & Co Chartered
   Accountants LLP" was normalizing to `"price waterhouse co"`, not
   `"price waterhouse"`. Fixed by dropping the leading `\b`.
2. A test asserted that `"Vakrangee Ltd"` vs `"Vakrangee Limited"`
   should match via the *fuzzy* stage — wrong: both normalize to
   `"vakrangee"` and correctly short-circuit at the normalized-name
   stage instead, which is the matching order working as designed.
   Fixed the test's example, not the code.

## Validated symbol/name change over time

CG Power (ISIN `INE067A01029`) is the real worked example for §7's
"validate symbol and name changes for at least one seed company over
time" requirement: `company_identifiers` shows `CROMPGREAV` valid
2017-01-05 → 2017-03-20, then `CGPOWER` valid 2017-03-20 → present —
the real Crompton Greaves → CG Power corporate rename, recovered
directly from bhavcopy data, not synthesized. See
`docs/phase-2/phase-2-report.md` for the raw query output.

## Evaluation

No labelled mention-pairs exist yet to compute pairwise precision/
recall/F1 against exact-match-only, since that requires either a
human-reviewed (gold) pair set or a larger real corpus with enough
natural name-variation to build a meaningful silver set from. This is
reported honestly as **not run** rather than fabricated — see the
Phase 2 report's limitations section and exit-gate table (gate 6 is
marked with this caveat).
