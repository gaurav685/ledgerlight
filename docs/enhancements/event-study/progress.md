# Enhancement 1: Governance Event Study — progress log

Branch: `enhancement/event-study`, created from
`phase-6/integrated-validation-release` @ `0345a43` (2026-11-13).

Ground rules carried from Phase 6: commit locally only, no push, no
tags; no fabrication, no sudo, point-in-time integrity; neutral
language, not investment advice; no AI attribution on any commit.

## Status

- [ ] §1 Pre-registration: `spec.md` + machine-readable spec, sha256
      stored, frozen before any CAR is computed.
- [ ] §2 Implementation: `ledgerlight/research/event_study.py`,
      `event_study_runs` migration, CLI commands, Dagster asset,
      tests.
- [ ] §3 Outputs: `report.md`, CAAR plots, API endpoint, UI panel.
- [ ] §4 Verify and commit.

## Log

**2026-11-13** — Branch created, `brief.md` saved verbatim,
`progress.md` initialized. Dispatched a read-only research pass over
the existing schema (`price_bars`, `events`/outcome tables, any
`model_registry`, `Company`/`Filing` linkage, Alembic migration
convention, Dagster asset convention, CLI/API router conventions,
trading-calendar handling, and available stats/plotting
dependencies) to ground §1's spec in what actually exists, rather
than inventing table/column names. §1 work starts once that comes
back.
