# Cost per filing (Phase 6A §10)

Real local measurement of per-filing resource use, per pipeline stage,
plus a parameterised AWS cost model built from it. Same host as §8:
AMD Ryzen 7 6800H (8c/16t), ~15.2GB RAM, Windows 11 Home, Docker
Desktop/WSL2 -- free memory on this host has been repeatedly,
genuinely unstable throughout this phase (from the user's other
applications, not this project's stack); every run below was done at
small scale with that constraint in mind.

## Method

`scripts/measure_cost_per_filing.py` runs N=10 real filings end to end
(ingestion through investigation), each a fresh, uniquely-worded
synthetic document (an audit-resignation notice, so it exercises the
real `AUD_RESIGN` extraction/event/entailment path), and measures
per stage:

- wall seconds (`time.monotonic()`)
- CPU seconds of the measuring process (`time.process_time()`)
- peak RSS, sampled before/after each stage (`psutil`) -- a
  conservative proxy for true peak, not a continuous sampler
- storage bytes written (raw input + derived: pages/chunks/embeddings)
- a standalone NLI (`entailment_score`) microbenchmark, 5 real calls

Every row and file the script creates (document, version, pages,
chunks, filing, company, investigation, claims, dossier, events,
review tasks, the per-filing manifest entry, the inbox file, the
content-addressed blob under `data/raw/manual/`) is deleted again at
the end of each filing. Confirmed clean after the run below via a
fresh DB session and `docker exec ... psql` directly against the real
container (bypassing the app entirely): `0` real rows and `0` stray
files left over.

```
uv run python scripts/measure_cost_per_filing.py
```

## Real bugs found and fixed while building this measurement

1. `import_inbox()` is keyword-only (`*, data_dir, ...`); the first
   draft called it positionally. `TypeError` on the very first run --
   fixed.
2. The cleanup's `events`/`event_fields` deletes were originally
   scoped by `company_id`. `Event.company_id` is nullable and is only
   ever populated by a real entity-resolution/filing-linking service
   this script intentionally bypasses (it links its synthetic company
   via a manual `Filing` row instead) -- so that delete matched zero
   rows, left `event_fields.evidence_version_id` still pointing at the
   filing's `document_versions` row, and broke the later
   `document_versions` delete on a real FK violation. Fixed by scoping
   the delete to the evidence version instead.
3. **The real one, found while verifying the fix above actually left
   the DB clean -- it didn't, at first.** `run_store_backfill()` is
   correctly idempotent for its real, intended use (re-running a full
   backfill is always safe), but it re-upserts *every* entry still in
   whatever manifest file it's given, every single call. This script
   originally pointed every filing at the one shared, ever-growing
   `data/manifests/manual.jsonl`. Calling it once per filing meant
   filing 2's backfill call silently re-created filing 1's document
   row (already deleted by filing 1's own cleanup, moments earlier,
   in the same run) -- and every later run re-created *all* prior
   runs' rows the same way, because the manifest entries and their
   content-addressed blobs under `data/raw/manual/` were never
   cleaned up either. No exception was ever raised (every delete and
   commit genuinely succeeded; the *next* filing's backfill call just
   as genuinely recreated the row) -- confirmed by direct `psql`
   queries against the container, not by trusting the script's own
   "done" output. Fixed by giving each filing its own
   `data/manifests/cost-measurement-{seed}.jsonl`, and by deleting
   that file plus its one content blob as part of the same filing's
   cleanup. 24 real orphaned rows and 25 stray manifest
   entries/blobs accumulated across the debugging runs above were
   swept up by hand once this was understood, and verified empty via
   a fresh DB session afterward.

None of these are findings about the real pipeline's own correctness
in production use (every one is this measurement script's own
plumbing) -- recorded because the brief's own ground rule is to
disclose every real finding, not just the ones that look good.

## Results (mean / p95 across N=10 real filings)

| stage | wall (s) | CPU (s) | peak RSS (MB) |
|---|---|---|---|
| import_local | 0.077 / 0.078 | 0.019 / 0.031 | 686.0 / 744.5 |
| storage_backfill | 0.111 / 0.094 | 0.041 / 0.047 | 686.4 / 744.5 |
| page_extraction | 5.433 / 5.672 | 0.011 / 0.016 | 686.4 / 744.5 |
| chunking | 0.020 / 0.031 | 0.003 / 0.016 | 686.5 / 744.5 |
| embedding | 3.433 / 0.391 | 4.972 / 2.609 | 741.6 / 744.7 |
| classify_extract | 0.031 / 0.032 | 0.156 / 0.234 | 741.6 / 744.7 |
| entity_bootstrap | 0.039 / 0.047 | 0.309 / 0.375 | 741.6 / 744.7 |
| investigation | 0.145 / 0.141 | 0.711 / 0.812 | 741.6 / 744.7 |

Storage: raw mean/p95 = 3571 / 3571 bytes; derived (pages + chunks +
embeddings) mean/p95 = 10131 / 10131 bytes (identical across all 10
filings -- every synthetic document is the same length by design).

NLI (`entailment_score`) standalone microbenchmark: mean 2.156s / p95
1.344s over 5 real calls.

**LLM tokens/cost: $0 throughout.** This project's agent renders
dossiers with the real offline template renderer
(`docs/modelling/model-card.md`); it never makes a live LLM call --
already established in Phase 4's agent-eval (Cost USD p50=p95=0.0000),
not re-measured here.

### Two real, disclosed measurement artifacts (not bugs)

- **`page_extraction`'s wall time (~5.4s) vastly exceeds its own CPU
  time (~0.01s).** `process_version()` runs the actual page-parsing
  work in a separate child process (`run_with_timeout`'s own
  `multiprocessing.Process`, a real isolation boundary against a
  hung/malformed-document parse) -- the child's CPU time is never
  visible to this script's `time.process_time()`, which only sees the
  parent. **This doesn't understate the real billed cost**: AWS
  Fargate bills by task wall-clock duration times allocated vCPU, not
  by measured CPU utilization, so wall time is already the right
  proxy for the cost model below.
- **`embedding`'s mean (3.433s wall / 4.972s CPU) is far above its own
  p95 (0.391s / 2.609s)**, and the standalone NLI benchmark shows the
  same pattern (mean 2.156s vs p95 1.344s over 5 calls). Both
  `embed_texts()` and `entailment_score()` lazily load a real model on
  first use and keep it cached for the process's lifetime -- one of
  the 10 filings pays that one-time load cost, the other 9 don't. In
  this script's own one-shot process that cost is paid once per run;
  in a real long-running worker it's paid once per worker *lifetime*
  (startup), not once per filing. **The p95 column is the better
  estimate of steady-state marginal cost per filing**; the mean
  reflects this benchmark's own cold start, not a real per-filing tax.

## AWS cost model

**Inputs marked `[MEASURED]` come from the table above. Inputs marked
`[CITED]` are real, dated, external prices. Inputs marked `[ASSUMED]`
are explicit parameters this model leaves open for the real deployment
to set -- never invented, always callable out.**

### Marginal cost per filing (compute + storage that scales with volume)

```
steady_state_wall_s = import_local + storage_backfill + page_extraction
                    + chunking + embedding_p95 + classify_extract
                    + entity_bootstrap + investigation
                  = 0.077 + 0.111 + 5.433 + 0.020 + 0.391 + 0.031
                    + 0.039 + 0.145
                  = 6.247 s                                [MEASURED, p95-based]

compute_cost_per_filing = (steady_state_wall_s / 3600)
                         * (vCPU * fargate_vcpu_hr + mem_GB * fargate_gb_hr)
```

- `fargate_vcpu_hr` = **$0.04256/vCPU-hour** (Fargate Linux/x86,
  on-demand, `ap-south-1`) `[CITED, aggregator-reported AWS rate,
  accessed 2026-11-06]`
- `fargate_gb_hr` = **$0.004655/GB-hour** (same source/region/date)
  `[CITED]`
- `vCPU` / `mem_GB`: this measurement's own peak RSS (~742MB) already
  sits close to the Phase 5 architecture doc's assumed 0.25 vCPU /
  0.5GB `worker` Fargate task size (`docs/deploy/aws-architecture.md`)
  -- a real, disclosed sizing flag for that doc, not fabricated: a
  worker task also running the real Dagster webserver alongside filing
  processing should likely be sized to **1 vCPU / 2GB**, used here
  `[ASSUMED]`.

```
compute_cost_per_filing = (6.247 / 3600) * (1*0.04256 + 2*0.004655)
                        = 0.0017353 * 0.051870
                        ≈ $0.0000900 per filing
```

Storage (per filing, one-time, not monthly -- see below for the
recurring monthly storage bill):

- raw bytes -> S3 Standard: **$0.025/GB-month** (`ap-south-1`)
  `[CITED, accessed 2026-11-06]`
- derived bytes (pages/chunks/embeddings, stored in Postgres) -> RDS
  gp3 storage: **$0.131/GB-month** (`ap-south-1`, as of Aug 2026)
  `[CITED, accessed 2026-11-06]` -- note `docs/deploy/aws-architecture.md`
  cites an earlier, lower $0.10/GB-month figure from Phase 5; both are
  shown so neither is silently overwritten.

```
raw_GB     = 3571  / 1_073_741_824 ≈ 3.33e-6 GB   [MEASURED]
derived_GB = 10131 / 1_073_741_824 ≈ 9.44e-6 GB   [MEASURED]

storage_cost_per_filing_per_month
    = raw_GB * 0.025 + derived_GB * 0.131
    ≈ $0.0000013 per filing, per month it's retained
```

**Marginal cost per filing ≈ $0.00009 compute + ~$0.0000013/month
storage -- effectively negligible at any volume this platform is
realistically sized for.**

### Why the marginal number alone is misleading: fixed infrastructure dominates

`docs/deploy/aws-architecture.md` (Phase 5, unchanged this phase)
already prices the real, always-on infrastructure this needs
regardless of filing volume:

- RDS `db.t4g.micro` (single-AZ, dev/staging sizing): **~$15/month**
  compute `[CITED, Phase 5]`
- 3 Fargate services (`api`/`worker`/`web`) at small fixed sizes,
  running continuously: **~$25-35/month** `[CITED, Phase 5]`
- Fixed baseline total: **~$40-50/month**, taken as $45/month here
  `[ASSUMED, midpoint]`

This baseline is paid whether the platform processes 10 filings or
10,000 filings a month -- it does not come out of the per-filing
marginal cost above.

### Example scenario: 10,000 filings/month

```
marginal_compute = 10,000 * $0.0000900         = $0.90/month
fixed_baseline                                  = $45/month   [CITED+ASSUMED]
blended_total    = fixed_baseline + marginal_compute
                 = $45.90/month
blended_$_per_filing = $45.90 / 10,000           ≈ $0.00459/filing
```

**At this volume the real bill is overwhelmingly the fixed Fargate +
RDS footprint, not the per-filing processing cost** -- the marginal
compute cost (~$0.90/month at 10k filings) is noise next to the fixed
~$45/month baseline. This is the honest headline number: cost per
filing at low-to-moderate volume is dominated by keeping the platform
running at all, and only becomes compute-dominated at a volume high
enough to require scaling the Fargate task count or size up from the
Phase 5 architecture doc's small, fixed sizing -- a real scaling
question for whoever operates this in production, not something this
measurement can answer by itself.

Cumulative storage growth is not included in the blended figure above
(it starts at effectively zero and grows by ~$0.013/month-worth of
new data per 10,000 filings processed, compounding slowly at these
`[CITED]` per-GB rates) -- negligible next to the fixed baseline for
any volume this model was built to cover.
