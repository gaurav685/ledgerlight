# Human Review Guide (Phase 6A §7)

This is for a real human reviewer. Every tool below was built, smoke-
tested against real data, and verified to resume/skip/record a
reviewer name correctly -- but **nothing in this review pack has
actually been reviewed yet**. That is deliberately Phase 6B's job, not
this phase's; this document only explains how to do it when the time
comes.

## One-page summary

| # | Type | Real sample size | Est. time | Command |
|---|---|---|---|---|
| 1 | Field review | 30 (real corpus currently supports 30) | ~45 min | `make field-review REVIEWER="you"` |
| 2 | Entity-pair review | **5** (real corpus is thin -- see below, not 20) | ~10 min | `make entity-pair-review REVIEWER="you"` |
| 3 | Retrieval review | 10 queries x up to 10 results | ~60 min | `make retrieval-review REVIEWER="you"` |
| 4 | Outcome-evidence spot-check | 45 (all real primary outcomes -- fewer than 60) | ~45 min | `make outcome-evidence-review REVIEWER="you"` |
| 5 | Dossier review | 13 (10 real + 3 seeded-QC, unlabelled) | ~90 min | see §5 below (per-item `--task-id`) |

Total real wall-clock for all five, done once through: **~4 hours**.
Run `make review-progress` any time to see counts per type and per
reviewer -- safe to check mid-session, nothing is required to finish
in one sitting.

**Every type resumes automatically.** If you stop partway and come
back later, re-run the exact same command -- anything you already
decided is skipped, and you pick up where you left off. A `skip`
persists like any other decision (with an optional note); it does not
need to be revisited unless you explicitly choose to redo it.

## Order to do things in

1. **Field review** first -- it's the most mechanical (does this value
   match the cited text?), a good warm-up.
2. **Entity-pair review** second -- quick, only 5 real pairs.
3. **Outcome-evidence spot-check** third -- similar mechanical style to
   field review, slightly higher stakes (these feed the risk model).
4. **Retrieval review** fourth -- more judgment-heavy (is this result
   actually relevant to the query?), best done with a clear head.
5. **Dossier review** last -- the richest, slowest type, and the one
   where the ~3 seeded-QC items test whether you catch deliberately
   injected flaws. Do this when you have the most attention budget.

## 1. Field review

**What it shows**: one real extracted field value (e.g. `audit_firm =
"KPMG"`), the exact cited span in the source document (marked
`>>>...<<<`), and ~150 characters of context on each side.

**Decisions**: `correct` (the value matches what the cited span really
says) / `wrong-value` (it doesn't -- you'll be asked for the corrected
value) / `unsupported` (the cited span doesn't actually support this
value at all) / `skip` (with an optional note).

**Examples**:
- Cited span: `...has resigned from... Price Waterhouse & Co Chartered
  Accountants LLP, have ceased to be the Statutory Auditors...`,
  value: `"Price Waterhouse & Co Chartered Accountants LLP"` →
  **correct**.
- Cited span mentions a resignation date of `April 27, 2018` but the
  extracted `resignation_date` field says `2018-04-28` → **wrong-value**
  (corrected value: `2018-04-27`).

**Run it**:
```
make field-review REVIEWER="your name"
.venv\Scripts\python.exe scripts\field_review.py --reviewer "your name"
```

## 2. Entity-pair review

**Honest disclosure**: the brief's own target here is ~20 pairs. The
real corpus right now supports only 5 real (mention, candidate entity)
pairs -- this mirrors a finding already disclosed in Phase 2
(`docs/phase-2/phase-2-report.md` §7e: "the real corpus's entity
surface is too thin... to build a meaningful pair set without
inventing cases"). The tool prints this note itself; it is not a bug.

**What it shows**: a real mention's surface text (e.g. `"KPMG"`), a
real candidate entity it was fuzzy-matched against (e.g. `"Price
Waterhouse & Co Chartered Accountants LLP"`), the real match score,
and whether the system itself auto-linked, flagged for review, or
rejected that pair.

**Decisions**: `same` (the mention really does refer to this entity) /
`different` (it doesn't) / `unsure` / `skip`.

**Examples**:
- Mention `"Price Waterhouse & Co Chartered Accountants LLP"` vs.
  entity `"Price Waterhouse & Co Chartered Accountants LLP"`, score
  100.0 → **same** (obviously).
- Mention `"KPMG"` vs. entity `"Price Waterhouse & Co Chartered
  Accountants LLP"`, score 10.0, system decision `reject` → **different**.

**Run it**:
```
make entity-pair-review REVIEWER="your name"
.venv\Scripts\python.exe scripts\entity_pair_review.py --reviewer "your name"
```

## 3. Retrieval review

**What it shows**: one of 10 real silver-set queries (e.g. `"statutory
auditor resignation"`), and its real top-10 hybrid-search results, one
at a time, each with a text preview. The query's own known-relevant
chunk (from the silver label set) is marked when it appears.

**Decisions**: `relevant` / `not_relevant` / `skip` -- per result, not
per query (so up to 10 decisions per query).

**Examples**:
- Query `"statutory auditor resignation"`, result text: `"UPDATE ON
  RESIGNATION FROM THE AUDIT ENGAGEMENT BY THE STATUTORY AUDITOR -
  PRICE WATERHOUSE..."` → **relevant**.
- Same query, a result whose text is about an unrelated quarterly
  results announcement → **not_relevant**.

**Run it**:
```
make retrieval-review REVIEWER="your name"
.venv\Scripts\python.exe scripts\retrieval_review.py --reviewer "your name"
```

## 4. Outcome-evidence spot-check

**What it shows**: one real primary-outcome event (IBBI CIRP admission
or a CARE/CRISIL-style rating downgrade to D), the company, the real
observed date, and the real evidence dict backing it (e.g. a matched
phrase like `"admitted into CIRP"` or `"CARE D"`, plus the source
`retrieval_url`).

**Decisions**: evidence supports the outcome? `yes` / `no` / `unclear`
/ `skip` -- then, if not skipped, date correct? `yes` / `no`.

**Examples**:
- `outcome_type: PRIMARY_IBBI_ADMISSION`, evidence: `{'admission_
  language_matched': 'admitted into CIRP', 'retrieval_url': 'https://
  ibbi.gov.in/uploads/order/...'}` → evidence supports: **yes**; date
  correct: **yes** (if the observed_at genuinely matches the order).
- `outcome_type: PRIMARY_RATING_DOWNGRADE_D`, evidence: `{'matched_
  text': 'CARE D', ...}` but the matched text is actually from a
  *different* company mentioned in the same press release → evidence
  supports: **no**.

**Run it**:
```
make outcome-evidence-review REVIEWER="your name"
.venv\Scripts\python.exe scripts\outcome_evidence_review.py --reviewer "your name"
```

## 5. Dossier review

Uses the existing, already real dossier-review flow
(`scripts/dossier_review.py`), not a new tool. This phase's own
`scripts/build_dossier_review_sample.py` already staged the real
sample (10 real dossiers, mixed SEED/UNIVERSE track and mixed real
score where one exists, plus 3 seeded-QC flawed dossiers) by opening
13 real `review_tasks`, `reason_code="phase6a_sample_review"` for the
real ones. The generated manifest and answer-key files
(`docs/phase-6/review-pack/dossier-review-*.jsonl`) are gitignored,
local-only, and deliberately not committed -- either file's content
is itself the answer to which items are seeded, so the right (and
only) way to work through this sample is the `--blind` commands below,
never by opening those files.

**List the real queue, then show and decide each task -- always with
`--blind`** (it suppresses both the explicit `seeded_qc` field and the
`reason_code` on `list`, and the "this is seeded QC" warning on
`show`, so the sample stays genuinely blind end to end):

```
make build-dossier-review-sample   # only needed once, already run
uv run python scripts/dossier_review.py list --blind

# for each task_id in the list:
make dossier-review-blind TASK=<task-id>
.venv\Scripts\python.exe scripts\dossier_review.py show --task-id <task-id> --blind

# then record your decision:
uv run python scripts/dossier_review.py decide --task-id <task-id> \
    --decision approve --reviewer "your name" [--notes "..."]
.venv\Scripts\python.exe scripts\dossier_review.py decide --task-id <task-id> ^
    --decision approve --reviewer "your name"
```

**Decisions**: `approve` / `approve_with_edits` / `reject` / `escalate`.

**Examples**:
- A real dossier whose every claim resolves to a real, correct citation
  and whose findings match the evidence → **approve**.
- A dossier with one claim whose cited span clearly does NOT say what
  the claim asserts (this is exactly what a seeded `wrong_number` or
  `wrong_date` flaw looks like, if you've hit one) → **reject**.

After finishing, a human (not this agent) decides whether to reveal
`docs/phase-6/review-pack/dossier-review-answer-key.jsonl` to compute
the real seeded-QC catch rate -- this phase does not do that
comparison itself, since doing so here would mean this agent reviewing
the result of a review it was never supposed to perform.

## Checking progress

```
make review-progress
.venv\Scripts\python.exe scripts\review_progress.py
```

Prints real counts per type, by decision and by reviewer, across all
five types (the dossier-review count is scoped to this phase's own
13-item sample, not every `review_task` in the database).
