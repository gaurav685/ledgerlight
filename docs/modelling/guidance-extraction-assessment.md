# Guidance Extraction Assessment (Phase 3 §5)

Status: assessed, limits stated. Exit gate 5 (brief §14): "Guidance extraction and
matching work with span verification. GUIDANCE_MISS boundaries are tested. The
credibility series is produced, **or limits are stated**." This document states those
limits, with real evidence, per the brief's own explicit fallback.

## What §5 and `GUIDANCE_MISS` require

Per `data/taxonomy/taxonomy-v1.0.yaml`'s `GUIDANCE_MISS` entry: "Management's previously
disclosed guidance (revenue, margin, volume, etc., stated on an earnings call or in an
investor presentation) is missed by a material margin in the subsequent actual results."
`required_fields: [guided_metric, guided_value, actual_value, guidance_date,
actual_period]`. Building this requires a real source of quantitative, forward-looking
statements attributable to company management, with a stated value and a future period --
not generic language, not a third party's own commentary.

## Method

Searched the entire real document corpus -- every `DocumentPage.raw_text` row across
every document type, not just `investor_presentation` -- for two keyword groups:

1. Generic: `guidance|we expect|we anticipate|targets? (revenue|growth|margin)|
   management expects|outlook for (FY|fiscal)|revenue guidance|expects? (revenue|growth)
   of` (case-insensitive).
2. The non-generic subset of (1) with the literal word "guidance" excluded, to separate
   genuine forward-statement language from false positives.

4,759 real pages were scanned (every page in the corpus as of this assessment).

## Result

**64 total keyword hits. 0 are a real, management-stated, quantitative forward-looking
statement with a value and a future period.**

- 58 of the 64 "guidance" hits are the literal phrase "Guidance Note" -- an auditing
  standard issued by the ICAI (Institute of Chartered Accountants of India), referenced in
  the two real annual reports' auditor's report sections (e.g. "the Guidance Note on Audit
  of Internal Financial Controls over Financial Reporting"), or generic CSR language
  ("career guidance", "guidance and necessary resources"). None states a forward metric.
- The remaining 6 hits (the non-generic "we expect" / "target growth" group) are, by
  direct inspection of each one's real page text:

| Document | Page | Chars | Cited text (≤15 words) | Why it is not real guidance |
|---|---|---|---|---|
| `31032021100427_LIC_Housing_Finance_Limited.pdf` (CARE rating rationale) | 2 | 2754-2763 | "ed by ~14.84% CAGR. We expect that LICHFL would have to raise equity funds in" | CARE's own analyst expectation about the company, not management's guidance; no stated value or period |
| `PNB%20Housing%20Finance%20Ltd-04-29-2019.pdf` (CARE rating rationale) | 2 | 2426-2439 | "ls, while achieving target growth. This is important in view of the increasing sha" | Vague ("target growth"), no number, and CARE's rationale language, not company-issued guidance |
| `1686654004950_1.pdf` (SEBI order) | 10 | 1449-1458 | "he Code of Conduct. We expect minimum level of supervision from every Stock Ex" | SEBI's own regulatory expectation of an exchange, unrelated to company financial guidance |
| `1583922229307.pdf` (SEBI order) | 94 | 690-699 | "us know by when can we expect these and the cost involved (stamp duty etc.)" | Procedural correspondence quoted in an order; about document delivery, not guidance |
| `1583922229307.pdf` (SEBI order) | 161 | 543-552 | "iscipline At CG, we expect our employees to guard the Company's financial cr" | An internal code-of-conduct policy clause, not a forward financial statement |
| `1376302960170.pdf` (SEBI order) | 3 | 1006-1015 | "iod of three weeks. We expect the Board to dispose of this matter within a" | SEBI procedural language about its own order timeline |

Every one of the 6 is a false positive from the generic "we expect" phrasing matching
unrelated regulatory, procedural, or third-party-analyst text -- none is management's own
stated quantitative guidance.

## Why this corpus has none

This project's real document acquisition (Phase 0/1) was scoped to compliant structured
and semi-structured sources: bhavcopy, CARE rating rationales, NCLT/IBBI orders, SEBI
orders, shareholding patterns, and a handful of company-site disclosures (auditor
resignation letters, one investor presentation, two annual reports). None of these is the
natural home for forward guidance -- that lives in earnings-call transcripts and dedicated
guidance press releases, which this project never identified a compliant bulk source for
and therefore never acquired (see `docs/data/source-inventory.md`). The single real
`investor_presentation` document in the corpus was checked directly: it contains no
guidance keyword hit at all.

## Decision

**Do not build GUIDANCE_MISS extraction machinery.** There is nothing real for it to run
on. Building a detector, a matching pipeline, or a credibility series against zero real
positive examples would mean either fabricating synthetic guidance statements (prohibited
by this project's ground rules) or shipping untested code with no way to verify it against
a single real case -- consistent with the financial-features exclusion decision in §4.3,
built on the same principle: don't build extraction machinery that has nothing to run on.

**Exit gate 5 status: limits stated.** `GUIDANCE_MISS` remains defined in the taxonomy
(`detection_approach: deferred_phase3`, unchanged) for a future phase if a compliant
guidance-statement source (e.g. exchange-filed investor-presentation PDFs at scale, or a
compliant earnings-call-transcript archive) is identified and acquired. No `GuidanceMiss`
feature, event, or outcome row exists in this project as of Phase 3, and none should be
assumed to.
