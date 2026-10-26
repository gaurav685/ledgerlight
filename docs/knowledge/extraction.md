# Structured Extraction (Phase 2)

## Schemas

One Pydantic schema per non-deferred event type
(`ledgerlight/knowledge/extraction_schemas.py`), all fields optional
(`None` = not stated, never inferred) and `extra="forbid"` (a typo in an
extractor can't silently create an unvalidated field):
`AudResignFields`, `KmpExitFields`, `IdExitFields`, `PledgeUpFields`,
`RatingActFields`, `AuditQualFields`, `ForensicFields`,
`RptGrowthFields`, `ResultDelayFields`.

## Extractors

**Default: rule/pattern-based, fully offline.** One real worked
extractor exists in Phase 2: **AUD_RESIGN**
(`ledgerlight/knowledge/extraction.py::extract_aud_resign_fields`) — a
gazetteer of known audit-firm names matched against chunk text, plus a
date-pattern search for the resignation date, each with a cited span.

**Why only one.** The other 8 schemas exist and are tested, but
extracting their fields from this specific small real corpus needs
table/layout extraction (shareholding-pattern percentages, rating
rationale tables, RPT-note figures) beyond what this phase built.
Documented honestly here rather than stubbed with invented logic — see
the Phase 2 report's limitations section.

**Optional LLM extractor.** Gated on `LLM_PROVIDER` and an API key being
present in `.env`. If absent: "not run", never faked. See
`ledgerlight/knowledge/llm_extraction.py` (not implemented in this phase
— no LLM_PROVIDER key is configured; see the Phase 2 report §9).

## Evidence verification

Every extracted value is checked against its own cited span before
being trusted (`ledgerlight/knowledge/evidence.py`):

| Value shape | Rule |
|---|---|
| names/free text | normalized substring containment (case-insensitive, whitespace-collapsed) |
| dates | the span's own date(s), however formatted, must parse to the exact claimed date |
| numbers/percentages | numeric equality within an explicit tolerance (0.01) |

A value that fails is stored with `validation_status='failed'` — never
silently dropped, never promoted — and a `review_queue` item is created
instead. A value with no checkable text in its span is `'unverifiable'`
(e.g. a missing filing date), distinct from `'failed'` (a value that
actively contradicts its span).

**A real bug found and fixed:** the date parser stripped commas from a
candidate date string before matching, but the format list only had
comma-*requiring* patterns for month-name dates (`"%B %d, %Y"`), so
"April 28, 2018" never verified against itself. Fixed by adding the
comma-less equivalents (`"%B %d %Y"`, `"%b %d %Y"`) — see
`tests/test_evidence.py` for the regression tests.

## Real run

`scripts/extract.py` over the real corpus (chunks the rules-baseline
classifier flags as AUD_RESIGN): 6 candidate chunks → 4 events, 7
fields, **0 failed verifications, 0 review items** — every extracted
value genuinely appears in its cited span. Idempotent per
`(evidence_version_id, evidence_page)`.

## Adversarial robustness

`tests/test_extraction_adversarial.py` proves: injected instructions in
document text ("IGNORE ALL PREVIOUS INSTRUCTIONS...") produce no extra
fields and no behaviour change (the extractor is pure pattern-matching —
it has no instruction-following capability to hijack); a value an
extractor "invents" (not actually present in its span) is rejected by
evidence verification for all three value shapes.
