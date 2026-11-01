# Human Review Workflow (Phase 4 §7)

`ledgerlight/agent/review.py` -- real automatic routing, the real
review CLI's backend, the append-only decision audit, and the
immutable-event-version feedback loop.

## Automatic routing

`create_review_tasks` is called automatically at the end of every real
investigation (`run_investigation`, both the normal-completion path and
the budget-exceeded path), right after the real dossier is persisted.
`determine_routing` checks every real rule the brief lists against the
real investigation/dossier/claims; more than one reason can fire, and
all of them do.

## Reason codes

| Code | Fires when | Priority |
|---|---|---|
| `high_severity_finding` | a real event claim has `severity="high"` | high |
| `conflicting_evidence` | the dossier's "Conflicting evidence" section is non-empty | high |
| `verification_failed` | `final_status="NEEDS_REVIEW"` for a reason other than a budget | high |
| `budget_exceeded` | `final_status="NEEDS_REVIEW"` and `failure_reason` mentions a budget | high |
| `candidate_tier_majority` | more than half the real event claims are CANDIDATE tier, not VERIFIED | default |
| `low_confidence_extraction` | a real extracted field feeding an event claim has `confidence < 0.7` | default |
| `seeded_qc` | a deliberately flawed dossier injected by `qc-seed` (`docs/agent/security.md`-adjacent; never a real finding) | default |

`REASON_CODES` in `review.py` is the single source of truth for both
the codes and their real descriptions.

## The `dossier-review` CLI (`scripts/dossier_review.py`)

- `dossier-review list [--limit N]` -- the real open queue, highest
  priority first.
- `dossier-review show --task-id <id>` -- the real dossier the task is
  about, as Markdown. Prints an explicit warning first if the task is
  `seeded_qc=True` -- per the brief's own §0 ground rule, a seeded QC
  item (or a gold item) must never be reviewed by a real human as if it
  were a real finding; this warning exists so an operator cannot miss
  that distinction.
- `dossier-review decide --task-id <id> --decision <approve|
  approve_with_edits|reject|escalate> --reviewer <name> [--notes ...]`
  -- records the real decision and appends to the real, append-only
  `review_decisions_audit` (`record_decision`; never edits a prior audit
  row).
- `dossier-review feedback --event-id <id> --status <verified|rejected>
  --reviewer <name> [--task-id <id>] [--notes ...]` -- the real feedback
  loop (`apply_event_feedback`): creates a NEW, immutable `EventVersion`
  row. `events.status` itself is never mutated in place, and this never
  touches the frozen Phase 1/2 test split (no column here references
  `label_items` or any gold-label table).

## Seeded QC (`qc-seed`)

`ledgerlight/agent/qc_seed.py` + `scripts/qc_seed.py` -- injects a
real, deliberately flawed dossier (one of four flaw types: `wrong_date`,
`wrong_number`, `missing_citation`, `unsupported_claim`) on top of a
real, already-FINALISED investigation's real claim set, as a NEW
dossier version. Dossier version 1 (the real, unflawed render) and the
investigation's own real `final_status` are never touched -- the one
exclusion rule every other real statistic (`agent-eval`'s own report,
most of all) relies on: filter out any `ReviewTask.seeded_qc=True` row,
and the dossier versions they reference.

`expected_outcome` is always `"reject"` -- every seeded flaw is a
genuine defect, so a correct reviewer decision is always to reject it.
`qc-seed catch-rate` reports, per flaw type, how many seeded items have
been decided and how many of those decisions matched `expected_outcome`
-- an undecided seeded item is excluded from the rate, never counted as
a miss.

`qc-seed batch` seeds a deterministic share of a real target list,
cycling through all four flaw types. A target with no real donor claim
for its assigned flaw type (`wrong_date`/`wrong_number` need a real,
resolving evidence span to corrupt against) is skipped, reported, and
does not abort the rest of the batch.
