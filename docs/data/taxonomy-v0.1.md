# Ledgerlight Red-Flag Taxonomy — v0.1 (DRAFT)

**This is a draft for Phase 0 feasibility planning only.** The formal,
versioned taxonomy — with precise, reviewed thresholds and edge-case rules
— is implemented in Phase 2. Nothing here should be treated as final.

**A red flag is an analytical signal, not proof of misconduct or of future
default.** Every category below describes a disclosure pattern that
warrants further human review; none of them, alone or in combination, is a
finding against any company, director, or officer.

## Categories

### AUD_RESIGN — Statutory auditor resignation
An auditor (statutory or otherwise required by listing regulations) resigns
or is not re-appointed outside the normal rotation/AGM cycle. Draft
threshold: resignation disclosed via exchange filing (BSE/NSE Reg 30) with
an effective date more than 60 days before the next scheduled AGM, OR any
resignation citing inability to complete audit procedures.

### PLEDGE_UP — Promoter pledge increase
Promoter/promoter-group pledge (encumbrance) of shares rises materially.
**Threshold specified in the Phase 0 brief**: pledge rises by at least 5
percentage points of promoter holding in a quarter-over-quarter comparison,
**or** cumulative pledge crosses 50% of promoter holding.

### KMP_EXIT — Key managerial personnel exit
A KMP (CEO, CFO, Company Secretary, Whole-time Director, etc., as defined
under the Companies Act / SEBI LODR) resigns or is removed outside a
disclosed succession plan. Draft threshold: disclosed exit with no named
successor within the same filing, or exit disclosed less than 30 days after
appointment.

### ID_EXIT — Independent director exit
An independent director resigns before completing their term, especially
when citing governance concerns in the resignation letter (SEBI LODR
requires such letters to be disclosed). Draft threshold: any independent
director resignation where the disclosed reason is not "personal reasons"
or "other commitments" alone — i.e. the letter cites a substantive concern.

### RATING_ACT — Adverse rating action
A credit rating agency downgrades, places on "negative watch," or
withdraws (other than at the issuer's request with no other negative
qualifier) a rating. Draft threshold: any downgrade of one or more notches,
or a watch/outlook change to negative.

### RESULT_DELAY — Delayed financial results
Quarterly or annual results are not disclosed within the SEBI
LODR-mandated deadline. Draft threshold: filing date exceeds the regulatory
deadline by more than 1 calendar day (any delay is itself a disclosure
event under LODR).

### AUDIT_QUAL — Audit qualification / adverse opinion
The statutory auditor's report contains a qualified, adverse, or disclaimer
of opinion, or an "emphasis of matter" paragraph relating to going concern.
Draft threshold: any qualification, adverse opinion, disclaimer, or
going-concern emphasis-of-matter in the audit report accompanying annual or
quarterly results.

### FORENSIC — Forensic audit ordered or disclosed
A forensic audit of the company (or a subsidiary) is ordered by the board,
a regulator, or a lender consortium, and disclosed. Draft threshold: any
such disclosure, regardless of whether findings are later published.

### RPT_GROWTH — Related-party transaction growth
Related-party transactions grow disproportionately relative to revenue or
total transactions. Draft threshold (placeholder, needs Phase 2 review):
RPT value as a share of revenue increases by more than 5 percentage points
year-over-year, or RPT value more than doubles year-over-year in absolute
terms.

### GUIDANCE_MISS — Guidance vs. actual miss
Management's previously disclosed guidance (revenue, margin, volume, etc.,
as stated on an earnings call or in an investor presentation) is missed by
a material margin in the subsequent actual results. Draft threshold
(placeholder): actual result misses the low end of disclosed guidance by
more than 10%, or guidance is revised downward more than once in a trailing
12-month window.

## Open questions for Phase 2

- Several thresholds above (RPT_GROWTH, GUIDANCE_MISS, and the AUD_RESIGN /
  KMP_EXIT "days" cutoffs) are placeholders, not derived from any observed
  distribution of real filings — Phase 0 did not have access to enough
  BSE/NSE announcement data (both BLOCKED; see
  `docs/data/source-inventory.md`) to calibrate them empirically.
- Category boundaries overlap in practice (e.g. a KMP_EXIT letter can also
  be an ID_EXIT if the KMP is also an independent director) — Phase 2
  should define precedence/co-occurrence rules.
