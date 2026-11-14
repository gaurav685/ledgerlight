# LEDGERLIGHT — ENHANCEMENT 1 CORRECTION: CORPORATE-ACTION ADJUSTMENT AND EVENT COVERAGE

Saved verbatim, 2026-11-13. Branch `enhancement/event-study` (continued).

---

Branch: enhancement/event-study. GIT POLICY: local commits only; no remote, push or tags. All ground rules apply, including the ABSOLUTE RESTRICTION on AI attribution. Print RAW evidence for every step.

## 1. CORPORATE-ACTION ADJUSTMENT (affects the core project, not just the event study)

1. Verify the method empirically before using it.
   - On days where the bhavcopy previous-close field differs from the prior session's close for the same ISIN, compute the factor = prev_close(t) / close(t-1).
   - Check it against at least 5 well-known, publicly documented splits or bonuses in the data. Cite each public source (exchange or company announcement) and give the expected ratio.
   - If the bhavcopy field does NOT reliably reflect adjustments, say so, and propose the best legitimate alternative instead (e.g., corporate-action announcements from AVAILABLE sources). Do not guess factors.
2. Implement adjusted prices:
   - Store adjustment factors in a new table with evidence (date, ISIN, factor, method, the source rows).
   - Provide an adjusted-price view or function. Raw price_bars stay immutable.
   - Point-in-time rule: a factor is known only from its ex-date onward. Historical features at as_of must use adjustments known by as_of (document how backward adjustment is handled without leaking).
   - Tests: factor detection, a split, a bonus, no false positives on ordinary large moves (circuit limits), and point-in-time behaviour.
3. Data-quality report: the number of corporate actions detected by year, and a list of residual suspicious jumps (e.g., |daily return| > 40% with no detected action), for review.

## 2. RE-RUN THE CORE RISK MODEL ON ADJUSTED PRICES

1. Rebuild the STRUCTURED price features from adjusted prices under a new feature_set_version. Keep the old version.
2. Re-run backtest, leakage-check, ablation and the point-in-time proof. The outcome spec hash stays unchanged.
3. Print old versus new pooled metrics with intervals, and update the model card and data-quality.md. Expect the results to remain inconclusive; report them honestly either way.

## 3. EVENT-STUDY COVERAGE FUNNEL

For each event type, print the funnel:
- raw candidates in the source
- span-verified
- entity auto-linked to a listed ISIN
- has price data around the event
- estimation window sufficient
- liquidity filter passed
- confounding filter passed
- final N

Then identify the biggest legitimate losses and recover the fixable ones:
- Entity linking:
  - measure the recall of auto-linking for CARE rationales and SEBI orders on a sample
  - improve deterministic linking (ISIN/symbol mentions in the document text, name normalization)
  - links below the auto-link threshold are still never used
- Rating coverage: check whether other rating agencies are marked AVAILABLE in sources.yaml and not yet ingested (ICRA and CRISIL stay excluded). Ingest them under the existing rules if so.
- CARE rationale coverage: report the dates covered versus the dates available. Run further ingestion if gaps are fixable within rate limits.
Report each change's effect on N.

## 4. EVENT STUDY v2 (new pre-registered spec version)

1. Create spec v2. The ONLY changes allowed:
   - adjusted prices
   - improved linking and coverage
   - excluding residual possible-corporate-action events from the primary analysis (reported separately)
   Windows, tests and filters stay unchanged. Store the new hash.
2. Re-run, and report v1 and v2 side by side: the funnel, the CAR tables (mean, median, t, BMP, rank, Holm p, N), the placebo percentiles, and the CAAR plots.
3. State plainly whether any effect survives correction. If N is still too small for conclusions, say so, with the counts.

## 5. VERIFY AND COMMIT

1. Run lint, typecheck, the tests, pre-commit run --all-files and gitleaks.
2. Commit with "enhancement:" prefixed messages.
   - Verify with: git log -n 8 --format='%H%n%an <%ae>%n%B---'
3. Refresh and verify ../ledgerlight-backups/ledgerlight-enh1.bundle.
4. Update docs/enhancements/event-study/report.md, progress.md and release-gates.md (add the corporate-action finding and its fix).

Stop after this.
