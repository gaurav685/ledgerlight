# Phase 6 Correction 2 §3 — dossier rendering defects

## §3.1 — "Unknown company" in the Sources section

### Root cause, confirmed not guessed

`ledgerlight/agent/render.py`'s `_resolve_source_citations` built every
Sources-section title as:

```python
title = f"{company_name_raw or 'Unknown company'}: {document_type}"
```

`company_name_raw` is `Document.company_name_raw` -- a Phase 1
ingestion-time field that is almost always `NULL` in this corpus
(confirmed in Phase 6 Correction 1 §4 work). A real scan of the live
database confirmed the real scope of the bug:

```
total real dossiers (any version) with 'Unknown company': 53
latest-version-only dossiers with 'Unknown company': 50
```

### The fix

The company name is now resolved via the real `filings` link
(`Filing.version_id -> Filing.company_id -> Company.display_name`),
scoped to the dossier's own `company_id` -- exactly as the brief
specifies ("resolve the company name via the filing's company link").
`company_name_raw` is kept only as a fallback for a document version
with no real filing link, and the investigation's own already-resolved
`company_name` is a further fallback ahead of the literal string
"Unknown company", which is now reached only if neither resolves at
all.

`_resolve_source_citations`'s SQL gained a `LEFT JOIN filings f ON
f.version_id = dv.id AND f.company_id = :company_id` and `LEFT JOIN
companies c ON c.id = f.company_id`, selecting `c.display_name`.
`render_offline` gained a required `company_id: uuid.UUID` parameter,
threaded through from `state_machine._render`'s 3 real call sites
(DRAFT, VERIFY resume, REPAIR) and `qc_seed.seed_flawed_dossier` --
every real caller already had `company_id` in scope.

### Real before/after, re-rendering an actually-affected real dossier

Investigation `00d87822-4c1a-437b-9e91-f70f71e46043` (PNBHOUSING),
whose persisted dossier shows the bug:

```
OLD: Unknown company: rating_rationale (care, 2018-07-05): "1 CARE Ratings Limited Press Release PNB Housing Finance Ltd July 06, 2018 Ratings Facilities"
NEW: PNBHOUSING: rating_rationale (care, 6 July 2018 (IST)): "1 CARE Ratings Limited Press Release PNB Housing Finance Ltd July 06, 2018 Ratings Facilities"
```

For this specific company, the real `filings` table has no row at all
linking these document versions (`f.company_id IS NULL` for both),
and `company_name_raw` is also `NULL` -- so the name is resolved via
the 3rd-tier fallback, the investigation's own `company_name`, which
is still correct and is never the literal "Unknown company" anymore.

To confirm the *primary* path (the real `filings` link itself, as the
brief asked for) is exercised and correct, a separate real
investigation whose evidence versions DO have a real `filings` row
was re-rendered (DMART, investigation
`59472ee4-5d02-445c-b5cf-892ce0112d9c`):

```
DMART: rating_rationale (care, 16 April 2013 (IST)): "Press Release April 16, 2013 CARE ASSIGNS ‘CARE AA-’ RATING TO THE PROPOSED SECURED NCD"
```

Here `filings.company_id` resolves to the same company the
investigation is about, and `companies.display_name` ("DMART") is
used directly -- the primary, filing-link-based path.

## §3.2 — Asia/Kolkata (IST) prose dates

### The fix

A new `_format_ist_date` helper in `render.py` converts a real UTC
instant (from `Claim.payload["known_at"]`, or a `document_versions`
`published_at`/`known_at` column) to its Asia/Kolkata calendar date
for prose only, e.g. `"4 June 2019 (IST)"`. Applied in
`event_claim_sentence`, `care_rating_claim_sentence`, the chronology
sentence loop, and the Sources citation date. No stored/exported
value changes: `Claim.payload["known_at"]` and every DB timestamp stay
UTC ISO 8601 -- only the prose-sentence string construction reads
differently.

Real sample from the DMART re-render above:

```
A real care:rating_rationale filing was known as of 7 February 2017 (IST).
A real care:rating_rationale filing was known as of 29 May 2017 (IST).
A real care:rating_rationale filing was known as of 18 July 2017 (IST).
```

### A real regression this surfaced, found and fixed

`tests/test_agent_state_machine.py::test_rerunning_a_previously_broken_real_dossier_shows_real_filings`
(5 real seed companies) started failing after this change:
`final_status` flipped from `FINALISED` to `NEEDS_REVIEW` for all 5.

Root cause: `ledgerlight/agent/verifier.py`'s
`check_sentence_values_in_claims` enforces that every number in a
rendered sentence exists somewhere in its mapped claim's own payload,
by regex-scanning both the sentence and the payload's raw ISO-string
fields for digits. The regex's own quirk (`-?\d+` greedily consumes a
leading `-` from an ISO date like `2019-06-04`, extracting `-6` and
`-4`, not `6` and `4`) happened to still match the *old* prose
(`known as of 2019-06-04T00:00:00+00:00`, the raw ISO string itself),
but not the *new* prose (`4 June 2019 (IST)`, whose `4` has no leading
minus sign) -- a real false-positive "number not found" failure,
exhausting all repair rounds into `NEEDS_REVIEW`.

Fixed in `_flatten_payload_numbers`: a payload string that parses as a
real UTC datetime now also contributes its Asia/Kolkata day/month/year
to the recognised-numbers set, so the new IST-rendered prose numbers
are correctly recognised as belonging to the claim -- without
weakening the check (it still fails if a truly unrelated number
appears). Confirmed fixed:

```
5 passed, 5 deselected in 51.94s  (DMART/VAKRANGEE/PNBHOUSING x2 -- all FINALISED again)
```

## §3.3 — golden snapshots, agent-eval, dossier structure tests

**Golden snapshot (`tests/fixtures/regression_snapshots.json`):
confirmed, with real evidence, that no update is needed.** The
`dossier` entry's `test_dossier_hash_matches_golden` hashes
`export_dossier_markdown` of an *already-persisted* real dossier row
(GENSOL, investigation `a1d93092-6a23-41a0-b3e2-afd6f0dcce68`) -- it
reads `Dossier.sections` as already stored in the database and never
calls `render_offline` again, so it is structurally decoupled from
this fix (which only changes what a *future* render produces).
Directly confirmed against the real frozen row: its stored markdown
contains neither "Unknown company" nor any `(IST)` date (it predates
this fix and this specific company's documents were not affected by
the company-name bug in the first place) -- hash unchanged,
byte-for-byte:

```
test_dossier_hash_matches_golden: PASSED (unchanged sha256)
```

The other 5 golden entries (extraction, events/tiers, entity links,
feature values, score) are unrelated to the renderer and are
unaffected by construction. All 6 regression-snapshot tests pass.

**agent-eval** (`scripts/agent_eval.py`, SEED + UNIVERSE tracks, real
DB, real investigations run fresh against this fixed code):

```
Real investigations run: 60
Status breakdown: SEED:FINALISED 30, UNIVERSE:FINALISED 30
Total claims in final dossiers: 740
Total claims removed in REPAIR: 72
Unsupported-claim leakage into a final dossier: 0
```

Leakage is 0, as required. All 60 real investigations FINALISED (none
NEEDS_REVIEW), confirming the §3.2 verifier regression above is fully
fixed, not merely patched for the 5 previously-failing test cases.

**Dossier structure tests** (`tests/test_agent_export.py`): 7 passed.
**Render tests** (`tests/test_agent_render.py`): 3 passed (updated to
pass the new `company_id` parameter). Full affected-suite re-run
(`test_agent_render.py`, `test_agent_review.py`, `test_agent_claims.py`,
`test_agent_state_machine.py`, `test_api_review.py`,
`test_agent_export.py`, `test_agent_verifier.py`,
`test_agent_qc_seed.py`, `test_agent_adversarial.py`): 84 passed, 0
failed.
