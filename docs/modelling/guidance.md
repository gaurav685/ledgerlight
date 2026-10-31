# Guidance (Phase 3 §5)

Status: assessed, **limits stated**. Exit gate 5 (brief §14): "Guidance extraction and
matching work with span verification. `GUIDANCE_MISS` boundaries are tested. The
credibility series is produced, **or limits are stated**."

Full real-evidence writeup, methodology, and the per-example document/page/char-span
citations: `docs/modelling/guidance-extraction-assessment.md`.

## Summary

Searched all 4,759 real pages in the entire document corpus (every document type, not
only `investor_presentation`) for quantitative, management-stated, forward-looking
guidance language before writing any extraction code -- verify before building. Result:
**0 real matches.** 64 raw keyword hits, every one either the unrelated ICAI "Guidance
Note" auditing-standard phrase, generic CSR language, or a false positive from generic
"we expect" phrasing (CARE's own analyst commentary, SEBI procedural correspondence) --
none a management-issued statement with a value and a future period.

No `GUIDANCE_MISS` extraction machinery, matching logic, or credibility series was built.
There is nothing real in this corpus for it to run against. This is tracked as an open
gap in `docs/release/release-gates.md`, not silently closed.
