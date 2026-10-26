# Red-Flag Taxonomy v1.0

Source of truth: `data/taxonomy/taxonomy-v1.0.yaml`, loaded into
`taxonomy_versions`/`event_types` by `scripts/taxonomy_load.py` —
**never hand-inserted**. This document is a human-readable summary of
that file; if the two ever disagree, the YAML is authoritative.

A red flag is an analytical signal, not proof of misconduct or of
future default. Every event type below describes a disclosure pattern
that warrants further human review; none of them, alone or in
combination, is a finding against any company, director, or officer.
Event/field descriptions use neutral language throughout ("disclosed",
"reported", "stated") — never "fraudulent" or similar.

## Changelog

**v1.0** (2026-10-26) — promoted from the Phase 0 draft
(`docs/data/taxonomy-v0.1.md`) to this machine-readable file:
- PLEDGE_UP's threshold made precise and boundary-tested.
- RESULT_DELAY's deadlines sourced from SEBI LODR Regulation 33(3)(a)
  (45 days, Q1–Q3) and 33(3)(d) (60 days, annual) — see citation below.
- RPT_GROWTH kept as the Phase 0 draft's placeholder, explicitly flagged
  as not empirically calibrated.
- AUDIT_QUAL's emphasis-of-matter explicitly separated from
  qualified/adverse/disclaimer.
- GUIDANCE_MISS defined but marked `detection_approach: deferred_phase3`.

**v0.1** (2026-10-24) — initial Phase 0 draft.

## RESULT_DELAY deadline citation

Verified against two independent sources, not assumed from memory:

- **SEBI's own Master Circular** `SEBI/HO/CFD/PoD2/CIR/P/2023/120`
  (`sebi.gov.in/sebi_data/attachdocs/jul-2023/1689087475880.pdf`):
  "Regulation 33(3)(d) ... states that the listed entity shall file
  audited annual results within 60 days from the end of the financial
  year ... Further, the listed entity shall submit the audited or
  limited reviewed financial results in respect of the last quarter
  along-with the results for the entire financial year" — i.e. Q4
  rides with the annual 60-day deadline, never a separate 45-day one.
- A secondary legal explainer (thefootnotes.in, "Regulation 33 of SEBI
  LODR: Results Format, 45-Day Deadline, Who Signs") corroborates:
  Regulation 33(3)(a) gives 45 days for Q1–Q3; there is "no separate
  45-day Q4 filing".

## The 10 event types

| Code | Detection approach | Required fields |
|---|---|---|
| AUD_RESIGN | text_classifier | audit_firm, resignation_date |
| PLEDGE_UP | rule_over_structured_data | as_of_date, promoter_holding_pct, pledged_pct_of_promoter_holding, previous_as_of_date, previous_pledged_pct_of_promoter_holding |
| KMP_EXIT | text_classifier | person_name, designation, effective_date |
| ID_EXIT | text_classifier | person_name, effective_date |
| RATING_ACT | rule_over_structured_data | agency, instrument, previous_rating, new_rating, action_type, action_date |
| RESULT_DELAY | rule_over_structured_data | period, deadline, actual_filing_date |
| AUDIT_QUAL | both | opinion_type, period, basis_text_span |
| FORENSIC | text_classifier | auditor_appointed, scope, date |
| RPT_GROWTH | rule_over_structured_data | counterparty, amount, period, previous_amount, previous_period |
| GUIDANCE_MISS | **deferred_phase3** | guided_metric, guided_value, actual_value, guidance_date, actual_period |

Full definitions, optional fields, severity rules and exact thresholds
are in `data/taxonomy/taxonomy-v1.0.yaml` — see
`ledgerlight/knowledge/taxonomy.py` for the three thresholds implemented
as real, boundary-tested code (PLEDGE_UP, RESULT_DELAY, RPT_GROWTH) and
`ledgerlight/knowledge/evidence.py`/`extraction_schemas.py` for how
AUDIT_QUAL's emphasis-of-matter exclusion is enforced in code.

GUIDANCE_MISS is defined here for taxonomy completeness only — no Phase
2 code path classifies, extracts, or scores it. Detection is explicitly
Phase 3 scope.

## Silver vs. gold labels

Every label this phase produces automatically (the keyword-rule
proposer, `ledgerlight.knowledge.labeling`) is **SILVER**
(`label_source=ai_assisted_unreviewed`). Only a human running
`scripts/label_review.py` can promote a label to **GOLD**
(`label_source=human_reviewed`) — no automated process in this codebase
ever sets that value. See `docs/phase-2/phase-2-report.md` §13 for the
human-gold-review checkpoint and the exact command/counts to run it.
