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
below), and -- as of the 2026-10-31 fix below -- only counts a case as
an admission if at least one of its real discovered documents contains
genuine, textual admission-confirming language (a declared Section 14
moratorium, "CIRP was initiated", or "the petition IS/WAS admitted" in
that direction specifically). The earliest such *qualifying* document
is used as the admission proxy. A company with real IBBI documents but
none containing confirmed admission language gets **no outcome row at
all** — never defaulted to "admitted".

This can still be wrong in one disclosed way: an earlier, real
admission order exists but was not discovered at all. IBBI coverage,
even after the full-universe broadening (§3), is not a guaranteed-
complete archive of every order IBBI has ever issued — it is bounded by
what IBBI's own full-text search surfaces for a company's legal name.

**Real bug found and fixed during the original population (2026-10-30):**
grouping by the exact case-number STRING instead of a normalized form
caused DHFL's single real case (docket 4258/2019) to be split into 4
spurious admission events, because the case number was extracted with
different whitespace/truncation across DHFL's 4 real order documents.
Fixed by `_normalize_case_number()`. `IBBI_CIRP_ADMISSION` dropped from
33 to 20 rows project-wide; DHFL specifically dropped from 4 to 3.

**Two further real, more serious bugs found and fixed while rebuilding
after the full-universe IBBI crawl (2026-10-31):** broadening coverage
grew `IBBI_CIRP_ADMISSION` from 20 to a naive 101 rows -- but direct
inspection of real new rows found this heuristic was systematically
wrong for cases where the only discovered document was NOT itself an
admission order:
1. **"ABB India Limited"** (a real, large, listed, never-insolvent
   company) showed up as an admission purely because its one real
   discovered IBBI document is a Section 12A **withdrawal** order
   ("...seeking to dispose of C.P(IB) No.210/BB/2018, as withdrawn"),
   not an admission. Many of the broadened companies' discovered
   documents turned out to be petition-FILING notices, routine hearing/
   attendance sheets, or dismissal/withdrawal orders -- none of which
   confirm a real admission, since a filed petition can still be
   dismissed or withdrawn before ever being admitted.
2. A second false positive surfaced once the first fix was applied: a
   loose, non-directional "admitted ... Petition" match fired on real
   text like *"the Corporate Debtor ... admitted its liability to make
   the payment of the three outstanding invoices. 11. The Petitioner,
   therefore..."* -- the DEBTOR admitting a **debt**, with "Petition"
   merely appearing nearby in the next sentence, not the tribunal
   admitting the case. Fixed by requiring the strict, directional
   "Petition IS/WAS/STANDS admitted" form only.

Real, concrete validation after both fixes: DHFL's genuine admission
("the petition was admitted") still correctly matches; ABB is correctly
excluded entirely (no qualifying document); the debt-admission false
positive (AEPL) is correctly excluded; a case with multiple discovered
documents (ABINFRA) correctly falls back to its OTHER, genuinely
qualifying document once the false-positive one is excluded by the
guard. 6 regression tests encode all of these real, checked cases
(`tests/test_populate_outcomes.py`).

**Real final row count: 31** `IBBI_CIRP_ADMISSION` rows (down from the
naive, wrongly-inflated 101; up from the pre-crawl 20), after: the
full-universe IBBI crawl was honestly stopped with its coverage
recorded (`docs/modelling/data-quality.md`); `scripts/process.py`-
equivalent extraction ran on the new real documents; `link_filings.py`
and `populate_outcomes.py` were both re-run. 64 real IBBI cases were
found and correctly EXCLUDED for lacking confirmed admission language --
printed by the script itself, not hidden. Pooled `PRIMARY_DISTRESS`
positives (`IBBI_CIRP_ADMISSION` ∪ `RATING_DOWNGRADE_D`, by distinct
company): **31** -- right at the brief's own 30-positive floor for
"statistically inconclusive, no predictive-skill claim" (see
`docs/modelling/evaluation-protocol.md`).

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

Current real row count: **7,514** `SEVERE_DRAWDOWN` rows, as of the
2026-10-31 post-crawl rebuild (purely structured; no document evidence
applicable — see §4).

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

Current real row count: **835** `BHAVCOPY_DISAPPEARANCE` rows, as of
the 2026-10-31 post-crawl rebuild (purely structured; no document
evidence applicable — see §4).

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
- The full-universe IBBI crawl was **honestly stopped** (2026-10-31),
  not run to completion -- only ~2.75% of the real ~2,617-company
  universe was actually searched before the real throughput measured
  in this session (72 companies in ~3h42m of real elapsed run time)
  showed the original 1.5-3 hour estimate was wrong by roughly two
  orders of magnitude. Full, final coverage detail (including why it
  was stopped rather than completed) is recorded in
  `docs/modelling/data-quality.md`'s own dedicated section. The row
  counts above are the real, final counts after this stop and the
  subsequent rebuild -- not partial pending a future re-run, though a
  future session completing more of the universe would still find
  more real companies and should re-run `populate_outcomes.py` again.
