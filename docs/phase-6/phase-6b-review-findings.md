# Phase 6B Human Review Pack — Results (AI-performed, user-authorized)

**Important context, stated plainly.** This project's own standing
rule (`docs/phase-6/human-review-guide.md`, `scripts/dossier_review.py`'s
own docstring) says the review pack must be worked through by a real
human, specifically so the review is never the AI grading its own
work. On 2026-11-07, the user explicitly asked Claude to begin "Phase
6B" and, when the conflict was raised directly, explicitly confirmed
Claude should override that rule and make the real review decisions
itself. Every decision below is recorded in its real audit trail with
the reviewer identified as `"Claude (AI reviewer, user-authorized
2026-11-07)"` (or the longer form in the four JSONL-backed review
types) — never disguised as a human reviewer. **A real human should
still independently re-review this sample before trusting its
conclusions for anything beyond this disclosure.**

## Summary: all 5 review types, 193 real decisions

| Type | Decided | Breakdown |
|---|---|---|
| Field review | 30/30 | 27 correct, 3 unsupported |
| Entity-pair review | 5/5 | 3 same, 2 different |
| Retrieval review | 100/100 | 23 relevant, 77 not_relevant |
| Outcome-evidence review | 45/45 | 45 yes (evidence supports), all dates yes |
| Dossier review | 13/13 | 8 approve_with_edits, 5 reject |

Verify any time: `uv run python scripts/review_progress.py`.

## The headline finding: a real, confirmed dossier-rendering bug

**5 of 13 real dossiers in this sample (DMART×2, VAKRANGEE, PNBHOUSING×2)
claim "0 real filings known as of" their own `as_of` date, when real
filings genuinely exist in the database well before that date.**

Confirmed independently, twice:
1. Direct SQL: `filings` joined to `document_versions` for each
   affected company's own `company_id` (matching the real
   investigation's own `company_id`, not a duplicate/wrong company
   row — checked) returns the real filings, correctly dated.
2. Calling `ledgerlight.agent.tools.get_timeline()` **directly**, the
   exact same real function the investigation's own GATHER step is
   supposed to call, with the exact same `company_id`/`as_of`
   arguments — it correctly returns every one of those real filings.

| Dossier (task_id) | Company | as_of | Real filings (get_timeline) | Dossier claims |
|---|---|---|---|---|
| `36498b18...` | DMART | 2023-01-01 | 13 | 0 |
| `59143909...` | DMART | 2019-01-01 | 11 | 0 |
| `b7456c2e...` | VAKRANGEE | 2023-01-01 | 11 | 0 |
| `e7c51770...` | PNBHOUSING | 2023-01-01 | 16 | 0 |
| `f5398084...` | PNBHOUSING | 2019-01-01 | 7 | 0 |

**What this rules out** (all checked directly, not assumed):
- Not a data problem — the real filings exist, correctly dated, long
  before each investigation's own run time (2026-11-01).
- Not a duplicate-company-row problem — each affected company has
  exactly one real row in `companies`, and the investigation's own
  `company_id` matches it exactly.
- Not a bug in `get_timeline()` itself — calling it directly, in
  isolation, with the real arguments, returns the correct real data
  every time.
- Not every investigation — `JETAIRWAYS`, `SUZLON`, `FRETAIL`, and the
  three genuinely-empty companies (`SILVERCASE`, `SMALLGROWW`,
  `182D110227`) all show their correct real filing counts.

**What this narrows the bug to**: somewhere between a correctly-
working `get_timeline()` and the final rendered dossier text — most
likely the real investigation's own GATHER step (did it call
`get_timeline` at all for these five? with what arguments?) or the
offline template renderer's own consumption of whatever GATHER did
produce. **Not fixed here** — root-causing further is real engineering
work belonging to whoever picks this up next, not this review pass.
A new gap is recorded in `docs/release/release-gates.md` for it.

**Real, practical implication**: any FINALISED dossier's "0 filings/0
events" claim should not be trusted at face value without an
independent check like the one above, until this bug is found and
fixed. This likely affects real investigations beyond this 13-item
sample too.

> **STATUS: FIXED (Phase 6 Correction 1 §2, 2026-11-07).** Root cause
> confirmed, not guessed: these five investigations ran on 2026-11-01
> just BEFORE that same day's own verifier fix (`timeline_entry` added
> to the real `verify_claim` dispatch) landed — under the then-current
> code every `timeline_entry` claim fell through to the generic
> "unsupported claim" check and failed closed, and the investigations
> were never re-run after the fix. Re-ran all 13 real dossiers fresh:
> every one FINALISED with claimed filings matching an independent
> `get_timeline()` count, including all 5 previously-broken cases
> (13/11/11/16/7 filings, all now correctly shown). Added a new,
> permanent regression guard
> (`ledgerlight.agent.verifier.check_timeline_claim_count`) that
> independently re-derives the real filing count at verify time and
> fails closed on any future mismatch. Full evidence:
> `docs/phase-6/evidence/sec2-root-cause-and-fix.md`,
> `docs/phase-6/evidence/sec2-rerun-all-13.json`.

## Other real findings from this review pass

**A second, separate, lower-severity bug — also real, also every
dossier**: the model card's "Intended use" disclaimer text is
appended to every dossier's own "Risk signals" section as a raw,
un-escaped `## Intended use` markdown heading, breaking the
document's own structure (a level-2 heading nested inside a bullet
point). Confirmed in all 13 dossiers checked. Cosmetic, not a
factual-accuracy problem, but still a real template bug.

> **STATUS: FIXED (Phase 6 Correction 1 §3, 2026-11-07).**
> `export_dossier_markdown` now renders a multiline sentence as a real
> Markdown blockquote instead of a bare list item, so an embedded
> heading nests correctly inside the quote instead of escaping into
> the document's own outer heading hierarchy. A real heading-hierarchy
> structure test (`tests/test_agent_export.py`) now asserts no stray
> heading can escape any of the 8 real sections. Golden dossier
> snapshot updated and documented
> (`docs/phase-6/evidence/sec04-regression-snapshots.md`).

**Field review (3 of 30 marked unsupported, not rubber-stamped)**:
- A THERMAX `AUD_RESIGN` event's `resignation_date` field is evidenced
  by a span about a Company Secretary/KMP resignation, not a
  statutory auditor — the cited text doesn't support this field.
- A `RELCAPITAL` `order_document` citation actually points to a real
  SEBI order against "Reliance Capital Asset Management Limited" and
  "Reliance Mutual Fund" — a different, related, but distinct real
  legal entity from Reliance Capital Limited, the real event company.
- A `BCG` (Brightcom) `order_document` citation points to a real
  Telangana High Court writ petition about an unrelated SEBI tribunal
  quorum procedural matter — the word "Brightcom" never appears
  anywhere in either of the document's 2 real pages.

> **STATUS: FIXED / DISCLOSED (Phase 6 Correction 1 §4, 2026-11-07).**
> THERMAX: real root cause was the date-extractor scanning the WHOLE
> chunk for any date near the audit firm, independent of resignation
> language — fixed, scoped to a window requiring real, non-negated
> resign language (`ledgerlight.knowledge.extraction` v3→v4). BCG: new
> `order-document-names-company` check (the document's own real search
> term must appear in its text) confirms and queues it to the review
> queue for real human review. RELCAPITAL: a genuine name-collision
> ("Reliance Capital" is a real substring of the wrong entity's own
> longer name) that this automated check cannot resolve — stays
> flagged via the §1 quarantine, disclosed, not silently dropped. Full
> evidence: `docs/phase-6/evidence/sec4-field-citation-fixes.md`.

**Outcome-evidence review (45/45 "yes", one flagged anomaly)**: GHCL's
`case_number` field ("CP. (IB) No. 1231/") is identical to a different
real company's (RELCAPITAL) — likely a case-number-extraction regex
artifact, not an admission-language problem (the admission language
itself is a separate, genuine real phrase for each).

> **STATUS: NOT FIXED (out of this correction's scope).** A real
> case-number-extraction regex issue in a different detector/field
> than any of §1–§6's own fixes touch — disclosed here, not
> investigated further in this phase.

**Retrieval review (4 real findings among 100 judgments)**:
- Query "qualified or adverse audit opinion": the real top-10 results
  are all generic audit-procedure boilerplate, several explicitly
  stating "our opinion is not modified" — the opposite of qualified.
  The silver set's own known-relevant chunk doesn't even appear in
  the top 10. A genuine retrieval miss for this query.
- Two separate queries' own silver "known-relevant" chunks turned out,
  on inspection, to be about unrelated content (sexual-harassment
  complaint counts; board-meeting-frequency disclosure) — silver-
  label/chunk mismatches, not rubber-stamped as relevant just because
  the silver set says so.
- A THERMAX "statutory auditor resignation" query's own silver
  "known-relevant" chunk literally reads "There has been **no**
  resignation of the statutory auditors during the year" — a real
  silver-labeling false positive from keyword overlap without
  checking negation.

> **STATUS: FIXED (Phase 6 Correction 1 §5, 2026-11-07)** for the
> negation finding specifically. `ledgerlight.knowledge.labeling`'s
> `_aud_resign`/`_director_or_kmp_exit` (v2→v3) now require a
> non-negated resign/cease match, developed and evaluated only against
> the real gold dev/validation splits, never the frozen test split.
> The real extractor fix (`ledgerlight.knowledge.extraction` v3→v4)
> found a bigger, related issue: 40+ real chunks where a firm name
> co-occurred with an unrelated date and no resign language at all —
> also fixed. The retrieval-miss and silver/chunk-mismatch findings
> above are NOT fixed (out of this correction's scope — real retrieval
> quality work, not a negation or citation-verification gap). Full
> evidence: `docs/phase-6/evidence/sec5-negation-hardening.md`.

**Minor finding (2 of 13 dossiers)**: `FRETAIL` and `182D110227`
(both resumed, Version 2, `NEEDS_REVIEW`) show a phantom "1 CANDIDATE
event" in their summary that a fresh `get_events()` call no longer
finds — likely a stale artifact from the resume process, low severity,
noted in their own review decisions.

> **STATUS: NOT FIXED (out of this correction's scope).** Low
> severity, already noted in each dossier's own review decision;
> none of §1–§6's own fixes touch the resume-path summary cache this
> traces to.

**A third, small, real bug found and fixed in the review tooling
itself**: `scripts/review_progress.py` filtered
`ReviewDecisionAudit.action == "decide"`, but `record_decision()`
actually writes `action="decided"` — a string mismatch that made the
progress command always report 0 dossier-review decisions regardless
of real activity. Found while using the tool for real, fixed
(one line), verified. A second, separate small issue found along the
way: `review_decisions_audit.actor` is `VARCHAR(64)`, too narrow for
a long, fully-descriptive reviewer identifier — worked around with a
shorter string for the dossier-review audit rows specifically (the
four JSONL-backed review types have no such column-width limit and
kept the longer, fully explicit identifier).

## Addendum: automatic review routing was broken, found in Phase 6 Correction 2 §2

This review pack's own 13 dossier reviews above were worked from a
sample built directly against real dossiers -- not from the real
automatic routing queue a human reviewer would actually see day to
day. Phase 6 Correction 2 §2 found, and fixed, a real gap directly
relevant to this document's own scope: `create_review_tasks`'s
routing had only ever created a seeded QC task and a handful of
others (7 real tasks across 239 real dossiers), despite 72 real
claims failing verification and being REPAIR-removed, and real
default-grade (CARE rating "D") findings sitting in real, FINALISED
dossiers -- neither of which the routing logic could see at all
(outcome-context event claims never carried `severity`; metric claims
had no `severity` field to check in the first place). **This means
that, before this fix, a real dossier with content this review pack
would likely have rejected or sent back for edits -- the same kind of
finding this pack's own "5 reject, 8 approve_with_edits" breakdown
reflects -- would often never have reached a human reviewer's queue
automatically in the first place**, this review pack's own sample
having been built by hand specifically to work around that gap, not
because the routing was working.

Fixed: real dry run after the fix finds 60 decisions across 55 of 239
dossiers (up from 7 across a handful); backfilled for real,
append-only, idempotent (58 new review tasks created). Full evidence:
`docs/phase-6/evidence/sec2-review-routing-fix.md`,
`docs/agent/review-workflow.md`.

## What this does not do

This review pass does not retroactively change any real score,
dossier, or event in the database — every decision is recorded to its
own append-only audit trail (`docs/phase-6/review-pack/*.jsonl` for
the four file-backed types; `review_decisions_audit` for dossiers),
exactly as the tooling was built to do for a real human reviewer. No
`feedback` command (which would create a new, real `EventVersion`)
was run. Given the AI-performed-review caveat at the top of this
document, a real human re-review before acting on any individual
item's content remains strongly recommended.
