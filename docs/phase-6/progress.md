# Phase 6A Progress

Read `docs/phase-6/brief-6a.md` first (the complete, verbatim brief), then
this file, before resuming any session. Branch
`phase-6/integrated-validation-release`, created from Phase 5 HEAD
`9227f51`.

GIT POLICY: commit locally only. No remote, no push, no tags.
ABSOLUTE RESTRICTION: no AI attribution of any kind on any commit.

## Sections

- §0 Ground rules -- standing, applies throughout.
- §1 Preflight: consolidated evidence file -- **COMPLETE** (2026-11-05).
  Green baseline (408 default + 322 integration, one sequential pass, no
  memory kill -- resolves the open Phase 5 full-batch gate).
  `docs/phase-6/orchestrator-evidence.md` built with verbatim Phase 2-5
  evidence. All 5 stop conditions checked explicitly: none triggered.
  Commit: `66f7020`.
- §2 Low-memory stack profile + deferred e2e/ZAP runs -- **COMPLETE** (see
  below).
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

- §2 Low-memory stack profile + deferred e2e/ZAP runs -- **COMPLETE**
  (2026-11-05). `infra/docker-compose.e2e-lite.yml` built
  (per-service mem_limit/mem_reservation, tuned Postgres, worker gated
  behind a `with-worker` profile, DAGSTER_MAX_CONCURRENT_RUNS=1). Real idle
  memory measured (postgres 26MiB fresh vs 2.3GiB accumulated-cache;
  garage/api/web all under 150MiB). The full Playwright e2e suite
  (`frontend/e2e/full-e2e-lite.spec.ts`) built and run against the real
  stack -- **4/4 passed**: login, search, overview+as_of, timeline+tiers,
  evidence+highlighted span (direct nav -- see the real UI gap noted
  below), investigation creation through FINALISE, dossier view, review
  decision (as reviewer), watchlist+alert-rule creation, webhook
  registration+test delivery, alert visibility after `generate_alerts.py`,
  cross-tenant denial. Real memory under load measured (~550MB total across
  all 4 services, comfortably inside budget).

  **Found and fixed a real, significant bug** while building this: the
  frontend's CSP (`script-src 'self'`, no exception) blocked Next.js's own
  inline hydration scripts outright -- React never hydrated in any real
  browser, so every form (login included) silently fell back to a native,
  unintercepted HTML GET submission with credentials in the URL. The
  documented Next.js nonce-based fix was implemented and tested directly;
  it did not work in this exact Next.js 16.4.3 setup (confirmed: no `nonce`
  attribute ever appeared on Next's own inline scripts). Deployed the
  pragmatic, honestly-disclosed fix instead (`'unsafe-inline'`, no nonce
  source present) -- full writeup `docs/phase-6/evidence/
  sec02-csp-hydration-bug.md`; residual risk recorded in
  `docs/security/threat-model.md`; both gaps (the nonce fix not working,
  and the ZAP baseline still not run) tracked in `docs/release/
  release-gates.md`.

  **Found a second real gap** (documented, not fixed -- a real missing UI
  affordance, not a defect in anything that exists): no page in this
  frontend ever links a dossier/timeline entry to a document URL carrying
  `char_start`/`char_end` -- the document viewer supports rendering the
  highlighted span (reads them from its own `searchParams`), but nothing
  navigates there with them. Proven directly in the e2e test via direct
  navigation with a real evidence span pulled from the database.

  **ZAP baseline run** against the real e2e-lite stack (own Docker
  network, no sudo): 0 FAIL in both runs. First run: 6 WARN/62 PASS. Two
  real, easy findings fixed (`X-Powered-By` header disabled via
  `poweredByHeader: false`; a real `Permissions-Policy` header added,
  denying every browser feature this app uses none of) and confirmed
  gone in a second run: 4 WARN/64 PASS. Remaining 4 triaged as accepted
  (`docs/phase-6/evidence/sec02-zap-triage.md`) -- the CSP finding is
  the same already-disclosed `'unsafe-inline'` trade-off; the other 3
  are informational or real-but-low-value (Cross-Origin-Embedder-Policy,
  not applicable to an app with no cross-origin embeds). Full Playwright
  suite re-confirmed 4/4 passing after both header fixes.

  Real host memory was highly unstable throughout this work (swung
  0.29GB-3.26GB free from the user's own other applications), causing 2
  real Docker build kills along the way -- all recorded in
  `docs/phase-6/evidence/`. Commit: `dea2c0c` (main), plus a follow-up
  for the ZAP work and header fixes.

## Exact next step

§2 is fully done. Move to §3: the automated end-to-end pipeline test
(ingestion -> dossier), run twice to prove idempotency, asserting the
full provenance/known_at chain.

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
