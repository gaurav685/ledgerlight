# LEDGERLIGHT — ENHANCEMENT 1: GOVERNANCE EVENT STUDY (MARKET REACTION)

Saved verbatim from the user's brief, 2026-11-13. Branch
`enhancement/event-study`, created from
`phase-6/integrated-validation-release` HEAD (commit `0345a43`).

---

Branch enhancement/event-study from the current phase-6 HEAD.

GIT POLICY: commit locally only. No remote, no push, no tags. All earlier ground rules apply:
- no fabrication, no sudo, point-in-time integrity
- neutral language, not investment advice
- ABSOLUTE RESTRICTION: no Claude, Anthropic or AI co-author, contributor, bot or attribution trailer

Save this brief to docs/enhancements/event-study/brief.md, and track progress in progress.md alongside it.

## Goal

Measure abnormal stock returns around governance and credit events across the NSE universe, with a methodology pre-registered before any results are computed. This complements the inconclusive 5-company risk model with a large-sample, statistically testable result.

## 1. PRE-REGISTRATION (freeze before computing ANY returns)

Write docs/enhancements/event-study/spec.md plus a machine-readable spec. Store the spec's sha256 in model_registry. Never edit the spec after results exist. A revised spec is a new version, and both are reported.

Event types. Use ONLY reliable sources:
- CARE rating downgrades, split by severity (e.g., within investment grade, crossing into sub-investment grade, to default D), rule-extracted and span-verified
- rating upgrades (as a contrast)
- SEBI final or interim orders against the company or its promoters (auto-linked entities only)
- IBBI CIRP admissions (auto-linked, verified)
- VERIFIED-tier governance events only, if enough exist; EVENT-CANDIDATE events are excluded from the primary results

Event date:
- the public-announcement date from known_at (IST), mapped to the first trading session at or after it
- intraday timing is unknown, so day 0 and day +1 are both included in the main window

Market model:
- estimation window [-250, -30] trading days, with at least 120 valid days required
- market return: a value-weighted index built from bhavcopy traded value (document this; shares outstanding are unavailable), plus an equal-weighted index as a robustness check

Windows:
- CAR[-1,+1] as the primary window
- CAR[0,+5], CAR[-10,+10], CAR[-30,-1] (pre-event drift), CAR[+2,+60] (post-event drift)

Filters:
- minimum liquidity (e.g., traded on at least 80% of estimation days)
- exclude events with another included event for the same company within ±10 days (confounding)
- exclude suspended or illiquid stocks
- report how many events each filter removes

Tests:
- cross-sectional t-test
- the BMP standardized test (robust to event-induced variance)
- the Corrado rank test (non-parametric)
- calendar-time clustering check: a Kolari–Pynnönen adjustment, or report the clustered dates
- multiple testing: report Holm-adjusted p-values across event types and windows

Placebo:
- random pseudo-event dates for the same firms (matched by year), repeated about 1,000 times
- the real CAR must be compared against the placebo distribution

## 2. IMPLEMENTATION

- A module ledgerlight/research/event_study.py:
  - point-in-time correct
  - uses price_bars and the outcomes/events tables
  - deterministic seeds
- Persist results: an event_study_runs table (spec hash, data snapshot hash, git SHA, metrics) and per-event abnormal returns, via an Alembic migration.
- Commands:
  - event-study run --spec <path>
  - event-study report
- A Dagster asset, run manually only.

Tests:
- abnormal return arithmetic on a hand-computed synthetic fixture
- trading-day alignment, including holidays and weekends
- estimation-window sufficiency
- the confounding filter
- the BMP and rank test statistics against reference values
- placebo determinism
- the spec-hash freeze guard (results cannot be written under a spec edited after the first run)

## 3. OUTPUTS

docs/enhancements/event-study/report.md, auto-generated:
- event counts per type and filter stage
- a CAR table per type and window: mean, median, t, BMP, rank p, Holm-adjusted p, N
- CAAR plots from day -30 to +60 per event type (PNG files, small)
- placebo comparison
- robustness checks: equal-weighted versus value-weighted market; with and without the confounding filter
- limitations: the market-index construction, CARE-only rating coverage, survivorship (include delisted firms), thin trading
- a plain-English summary with no causal or trading claims

Also:
- API endpoint: /v1/research/event-study, returning the latest run summary, read-only
- UI: a "Market reaction" panel on the company page showing that company's events with their CAR versus the type average, plus a research page with the CAAR charts
- disclaimers throughout

## 4. VERIFY AND COMMIT

1. Run lint, typecheck, the tests (unit plus a small integration run), pre-commit run --all-files and gitleaks.
2. Print raw output for: the spec hash, event counts per filter stage, the CAR tables and the placebo results.
3. Commit with "enhancement:" prefixed messages.
   - Verify with: git log -n 6 --format='%H%n%an <%ae>%n%B---'
4. Refresh the bundle: ../ledgerlight-backups/ledgerlight-enh1.bundle, with git bundle verify.

Report results honestly. If no effect is significant after correction, say so. Stop after Enhancement 1.
