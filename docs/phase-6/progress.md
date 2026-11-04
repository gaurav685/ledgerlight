# Phase 6A Progress

Read `docs/phase-6/brief-6a.md` first (the complete, verbatim brief), then
this file, before resuming any session. Branch
`phase-6/integrated-validation-release`, created from Phase 5 HEAD
`9227f51`.

GIT POLICY: commit locally only. No remote, no push, no tags.
ABSOLUTE RESTRICTION: no AI attribution of any kind on any commit.

## Sections

- §0 Ground rules -- standing, applies throughout.
- §1 Preflight: consolidated evidence file -- NOT STARTED.
- §2 Low-memory stack profile + deferred e2e/ZAP runs -- NOT STARTED.
- §3 End-to-end pipeline test (ingestion -> dossier) -- NOT STARTED.
- §4 Regression suite -- NOT STARTED.
- §5 Backtest reproducibility and audits -- NOT STARTED.
- §6 Consolidated evaluation report (pre-review) -- NOT STARTED.
- §7 Human review pack (build only, no reviewing) -- NOT STARTED.
- §8 Performance and reliability -- NOT STARTED.
- §9 Security and tenant re-validation -- NOT STARTED.
- §10 Cost per filing -- NOT STARTED.
- §11 Data-source compliance and licence review -- NOT STARTED.
- §12 Final documentation -- NOT STARTED.
- §13 Clean-install and reproducible-setup test -- NOT STARTED.
- §14 Production-readiness checklist -- NOT STARTED.
- §15 Release-gate status -- NOT STARTED.
- §16 Run and verify -- NOT STARTED.
- §17 Commit (local only) and backup -- ongoing throughout.
- §18 Human checkpoint and 6A exit gates -- NOT STARTED. **STOP here --
  do not begin Phase 6B.**

## Exact next step

§1: run the full backend/frontend checks for a green baseline, then build
`docs/phase-6/orchestrator-evidence.md` with verbatim Phase 2-5 evidence per
the brief's own list. Check the 5 real stop conditions before continuing
past §1.

## Known starting context (from Phase 5)

- Real host memory pressure was a recurring, confirmed problem throughout
  Phase 5 (multiple real OOM kills, unrelated to this project's own Docker
  stack -- from the user's other running applications). §2's own low-memory
  stack profile work directly addresses this; sequence accordingly.
- Deferred from Phase 5 (`docs/release/release-gates.md`): the full
  Playwright e2e suite, the ZAP baseline, a single-batch full
  integration-test run. This brief's own "Deferred gates now due" list
  names the Playwright/ZAP pair plus human review types that don't exist
  yet, the outcome-evidence spot-check, 10-dossier human review, and
  GitHub Actions verification after a first push (the last one stays
  blocked on GIT POLICY -- no remote -- same as every prior phase).
- Two items carried over from Phase 4/5, still unresolved, not part of
  this brief: pushing a backup bundle to a remote (no remote configured);
  SpiceJet's control-group status (a human decision from Phase 3 §17.1).

## Pending items carried over (not part of this brief, flagged so they are not lost)

- Push a backup bundle to a git remote -- no remote configured; GIT POLICY
  unchanged.
- SpiceJet's control-group status -- unresolved human decision, Phase 3
  §17.1.
