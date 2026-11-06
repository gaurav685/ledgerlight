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

## Other real findings from this review pass

**A second, separate, lower-severity bug — also real, also every
dossier**: the model card's "Intended use" disclaimer text is
appended to every dossier's own "Risk signals" section as a raw,
un-escaped `## Intended use` markdown heading, breaking the
document's own structure (a level-2 heading nested inside a bullet
point). Confirmed in all 13 dossiers checked. Cosmetic, not a
factual-accuracy problem, but still a real template bug.

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

**Outcome-evidence review (45/45 "yes", one flagged anomaly)**: GHCL's
`case_number` field ("CP. (IB) No. 1231/") is identical to a different
real company's (RELCAPITAL) — likely a case-number-extraction regex
artifact, not an admission-language problem (the admission language
itself is a separate, genuine real phrase for each).

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

**Minor finding (2 of 13 dossiers)**: `FRETAIL` and `182D110227`
(both resumed, Version 2, `NEEDS_REVIEW`) show a phantom "1 CANDIDATE
event" in their summary that a fresh `get_events()` call no longer
finds — likely a stale artifact from the resume process, low severity,
noted in their own review decisions.

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
