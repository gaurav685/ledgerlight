# Outcome Definitions (Phase 3 §3)

Status: active. Spec version `outcomes-1.0`, frozen 2026-10-31.

Machine-readable spec: `data/modelling/outcomes-v1.0.json`.
sha256 of that file (store this value in `model_registry` for every
experiment that trains or evaluates against these outcomes):

```
d879a2874d063b0025820ce52223e443b5b14d7c8746aa8d9e3117e4f3503e1b
```

Event taxonomy backing these outcomes: `data/taxonomy/outcomes-v1.0.yaml`
(loaded via `make outcomes-taxonomy-load`). Population script:
`scripts/populate_outcomes.py`. This taxonomy is deliberately separate
from the governance red-flag taxonomy (`taxonomy-v1.0.yaml`) — these
event types are realized outcome triggers, not disclosure red flags.

## 1. Horizon

H = 12 months. Every outcome below is evaluated over a forward-looking
12-month window from a given `as_of` date.

## 2. Primary outcome

**PRIMARY_DISTRESS**: severe credit or insolvency distress within 12
months after `as_of`. Fires if either of these real, evidenced event
types occurs in the window:

- `IBBI_CIRP_ADMISSION`
- `RATING_DOWNGRADE_D`

Event date (for horizon placement) = the earliest trustworthy `known_at`
across the trigger's supporting evidence. For both trigger types this
is the document's own `published_at`, per
`ledgerlight.db.temporal.compute_known_at`'s `RELIABLE_PUBLISHED_AT_SOURCES`
set (`ibbi`, `care` are both members) — not the date this project
happened to fetch the document.

### 2.1 IBBI_CIRP_ADMISSION

A National Company Law Tribunal order admitting a company into
Corporate Insolvency Resolution Process under the Insolvency and
Bankruptcy Code, evidenced by a real IBBI order document auto-linked to
the company (Phase 3 §2.3/§2.4's per-company IBBI discovery, broadened
in §3 from the 15-company SEED-track universe to every currently-listed
company via NSE's own equity master CSVs).

**Detection is a disclosed heuristic, not a hand-verified legal
classification of every order.** `scripts/populate_outcomes.py`'s
`populate_ibbi_admissions` groups a company's real IBBI order documents
by case number (extracted via `_CASE_NUMBER_PATTERN`, normalized via
`_normalize_case_number` to the leading digit run — see the DHFL bug
below) and treats the EARLIEST-dated order found for a given case as
the admission proxy, since the initiating order in a CIRP case is
typically its earliest.

This can be wrong in two disclosed ways:
- An earlier, real admission order exists but was not discovered. IBBI
  coverage, while broadened to the full currently-listed universe, is
  not a guaranteed-complete archive of every order IBBI has ever
  issued — it is bounded by what IBBI's own full-text search surfaces
  for a company's legal name.
- The earliest-found order for a case is itself a pre-admission
  procedural order (e.g. an interim application), not the admission
  order itself.

**Real bug found and fixed during population (2026-10-30):** grouping
by the exact case-number STRING instead of a normalized form caused
DHFL's single real case (docket 4258/2019) to be split into 4 spurious
admission events, because the case number was extracted with different
whitespace/truncation across DHFL's 4 real order documents (`"CP (IB)
No. 4258/"`, `"CP(IB)No. 4258/"`, `"CP (IB) No. 4258/2019"`, and one
regex miss → `None`). Fixed by `_normalize_case_number()`, which
extracts the first ≥2-digit run, collapsing all four real variants to
`"4258"`. Re-run confirmed: `IBBI_CIRP_ADMISSION` dropped from 33 to 20
rows project-wide; DHFL specifically dropped from 4 to 3 (the remaining
2 rows are real, distinct documents with a disclosed, separate
limitation: 2 of DHFL's real order documents simply do not match
`_CASE_NUMBER_PATTERN` within the first 2000 characters searched — a
regex-recall gap, not a grouping/correctness bug). Evidence:
`docs/phase-3/evidence/populate-outcomes-run1.log` (buggy, 33 rows) vs
`docs/phase-3/evidence/populate-outcomes-run2-fixed.log` (fixed, 20
rows).

Current real row count: **20** `IBBI_CIRP_ADMISSION` rows, as of the
2026-10-30 fixed run. This is explicitly **partial**: the §3
full-universe IBBI discovery crawl (`scripts/ibbi_universe_discovery.py`)
was still running as of this writing (2,617 currently-listed companies
to check at IBBI's own per-company rate limit; IBBI document count had
grown from the SEED-track baseline of 55 to 64 at the last check before
this document was written). `populate_outcomes.py` must be re-run once
(a) that crawl finishes and (b) `scripts/process.py` has extracted text
for whatever new IBBI documents it found — `populate_ibbi_admissions`
joins against `DocumentPage`, so an un-extracted document is invisible
to it even if fetched.

Required fields on the `Event`: `case_number`, `order_date`,
`retrieval_url`. Evidence: exactly one `EventField` citing the real
`DocumentVersion` id, page, and character span of the matched case
number.

### 2.2 RATING_DOWNGRADE_D

A credit rating agency assigns a "D" (default) rating symbol to any
instrument of the company, in a real, span-verified extracted
document. CARE is the only AVAILABLE rating agency for this project —
ICRA is BLOCKED by a bot-mitigation challenge and CRISIL is excluded by
its own stated exclusion terms (`docs/data/source-inventory.md`).

Detected by `populate_rating_downgrade_d` via a literal, case-insensitive
regex (`_RATING_D_PATTERN`) over extracted `DocumentPage` text for CARE
source documents, matching phrasing such as "CARE D", "rated D", or
"downgraded to D". **The matched page and character span are recorded
as the evidence citation — never inferred without that span**, per the
brief's own requirement that a rating symbol and date must both be
present in the cited text.

Current real row count: **14** `RATING_DOWNGRADE_D` rows, as of the
2026-10-30 run. This is also explicitly partial, for a different
reason than §2.1: CARE rationale discovery (Phase 3 §2.2) was driven by
the 15-company SEED-track universe, not the full currently-listed
universe. §3's broadening decision (user-directed) was scoped to IBBI
discovery only — CARE discovery was not broadened in the same step.
Extending CARE discovery to the full universe is listed as unfinished
work below, not silently assumed complete.

Required fields: `rating_symbol`, `rating_date`, `agency`,
`retrieval_url`. Evidence: exactly one `EventField` per outcome.

## 3. Secondary outcomes

These are reported alongside the primary outcome but are not part of
its OR-combination. Each is its own `outcome_type` row.

### 3.1 SEVERE_DRAWDOWN

Fires when a company's trailing 12-month return, at a given month-end
`as_of`, is at least X percentage points below that month's
cross-sectional median return across the real EQ-series universe
trading that month (an excess/relative-drawdown definition, not an
absolute one — this avoids conflating a single company's bad month with
a market-wide downturn).

**X = -48.69 percentage points.** This is the real p5 of the pooled,
empirical, cross-sectional 12-month excess-return distribution computed
by `scripts/compute_drawdown_threshold.py` directly from `price_bars`
(EQ series only), 2016-01 through 2026-10, 117 usable months, 149,285
observations, with a 10-day tolerance window for the prior-year lookup
date. This value is NOT assumed or round-numbered — it is the actual
computed percentile, reported to 2 decimal places as the script printed
it.

**Disclosed contamination and mitigation.** `price_bars` is not
corporate-action/split-adjusted in this project. Three gold ETFs
(GOLDSHARE, HDFCMFGETF, BSLGOLDETF) show ~99% apparent "drawdowns" that
are a real 2021 100:1 unit-value restructuring, not economic loss —
confirmed by direct inspection of their raw price series, not assumed.
Mitigated two ways, both applied and both disclosed:
1. `_looks_like_etf()`: a symbol-substring heuristic (`ETF`, `BEES`,
   `GOLDSHARE`, `LIQUID`, `GOLD`, `SILVER`) that excludes known ETF-like
   tickers from the threshold computation. This is a heuristic, not a
   security-type lookup — it can both over- and under-exclude.
2. `WINSORIZE_ABS_RETURN = 0.90`: any |return| above 90% is capped at
   90% before computing percentiles, bounding the influence of any
   remaining unflagged outlier.

Both the raw (unfiltered, unwinsorized) and filtered percentiles are
reported side by side in the script's own output and the commit that
introduced it — raw p5 was -55.73pp vs filtered p5 of -48.69pp. The
filtered value is the one used as X here; the raw value is kept in the
evidence log for transparency, not discarded.

Current real row count: **7,462** `SEVERE_DRAWDOWN` rows (purely
structured; no document evidence applicable — see §4).

### 3.2 SEBI_ORDER_AGAINST_COMPANY

Fires when a real SEBI final or interim order exists, auto-linked to
the company per Phase 3 §2.3/§2.4's per-company SEBI discovery. SEBI's
own search already confirms the order names the company; this project
does not further distinguish an order against the company itself from
one against its promoters — the taxonomy treats both as this one
outcome, and that collapsing is a deliberate scope decision, not an
oversight.

Current real row count: **69** `SEBI_ORDER_AGAINST_COMPANY` rows.

### 3.3 BHAVCOPY_DISAPPEARANCE

Fires when a company that was trading in `price_bars` (EQ series) stops
appearing, with a gap of at least 90 days (`min_gap_days`) before the
end of this project's bhavcopy coverage and no later re-appearance.

**Explicitly disclosed as noisy.** This project has no compliant
corporate-actions source. A benign disappearance — a merger, a scheme
of arrangement, a voluntary delisting — cannot be distinguished from a
distress-driven one at this event's own detection step. This outcome is
therefore a coarse market-observable PROXY, not a distress
confirmation, and must be read that way in any downstream analysis or
model that consumes it.

Current real row count: **801** `BHAVCOPY_DISAPPEARANCE` rows (purely
structured; no document evidence applicable — see §4).

## 4. Evidence requirements by tier

Per the project's existing reliability-tier discipline
(`ledgerlight.db.temporal` / detector hardening), document-evidenced
outcomes get real `EventField` citations and purely-structured outcomes
do not, because `EventField`'s `evidence_version_id` /
`evidence_page` / `evidence_char_start` / `evidence_char_end` columns
are all `NOT NULL` — there is no document to cite for a numeric signal
computed directly from `price_bars`.

| Outcome type | Evidence |
|---|---|
| `IBBI_CIRP_ADMISSION` | 1 `EventField` citing a real `DocumentVersion`, page, char span |
| `RATING_DOWNGRADE_D` | 1 `EventField` citing a real `DocumentVersion`, page, char span |
| `SEBI_ORDER_AGAINST_COMPANY` | 1 `EventField` citing a real `DocumentVersion`, page, char span |
| `SEVERE_DRAWDOWN` | none — numeric values live directly in `Outcome.outcome_value` JSONB |
| `BHAVCOPY_DISAPPEARANCE` | none — numeric values live directly in `Outcome.outcome_value` JSONB |

Every positive `IBBI_CIRP_ADMISSION` and `RATING_DOWNGRADE_D` row (the
primary outcome's own trigger types) is listed, with its evidence
citation, in `docs/modelling/outcome-evidence-review.csv` for the
human spot-check this project's release gates require before any
model trained against this outcome ships (see
`docs/release/release-gates.md`). That review has not happened yet as
of this writing — the taxonomy file says so explicitly, and this
document does not claim otherwise.

## 5. Censoring

Censoring is handled explicitly. **A company is never silently labelled
a negative for the primary outcome just because no trigger was
observed before this project's data ends.**

- **Unknown trading stop.** If `BHAVCOPY_DISAPPEARANCE` fires for a
  company, every `as_of` window that extends past that company's last
  trade date plus `min_gap_days` (90 days) is RIGHT-CENSORED for the
  primary outcome, not a confirmed negative. A company that stops
  trading could have gone through an undiscovered insolvency process,
  been quietly acquired, or simply gone dark in this project's own data
  — none of those is evidence of "no distress." Any walk-forward
  evaluation that uses such a window MUST exclude it or explicitly flag
  it as censored; it must never be imputed as a hard 0.
- **End-of-window observation.** If an `as_of`'s 12-month forward
  window extends past the end of this project's real data coverage
  (currently 2026-10-30 for `price_bars`; per-source coverage end dates
  for CARE/IBBI/SEBI are in `docs/phase-3/phase-3-report.md` §2), that
  window is also RIGHT-CENSORED. The absence of an observed trigger
  before data collection ends is not evidence of a true negative — a
  real trigger could exist after the data's own coverage ends and
  simply not yet be observed by this project.

Both rules are encoded in the machine-readable spec
(`data/modelling/outcomes-v1.0.json`, `censoring_policy` block) so that
any future feature/label-building script can read them programmatically
rather than re-deriving this logic from prose.

## 6. Known coverage gaps (disclosed, not hidden)

- IBBI discovery, even after §3's broadening, only covers companies
  currently listed as of the NSE equity master snapshot used by
  `scripts/ibbi_universe_discovery.py`, plus the 15 SEED-track
  companies individually (which include some already-delisted names
  like DHFL). Companies delisted before this spec's freeze date, beyond
  those 15, are UNCHECKED for `IBBI_CIRP_ADMISSION` — not
  confirmed-negative.
- CARE rating discovery remains scoped to the 15-company SEED-track
  universe only; it was not broadened to the full universe in this
  pass. `RATING_DOWNGRADE_D` is therefore only meaningfully checked for
  those 15 companies as of this spec's freeze date.
- Both gaps mean the current `PRIMARY_DISTRESS` outcome is reliable as
  a label for the SEED-track universe and for whichever UNIVERSE-track
  companies IBBI's own search happens to surface, but is NOT yet a
  complete universe-wide ground truth. This must be accounted for in
  any walk-forward evaluation split and reported as a limitation, not
  smoothed over.
- The full-universe IBBI crawl was still running when this document was
  written; the row counts above will change on re-run and must be
  refreshed (and this document updated) once it completes and its
  output is extracted.
