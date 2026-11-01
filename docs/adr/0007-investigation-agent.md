# ADR 0007: Investigation Agent State Machine (Phase 4)

## Status
Accepted (Phase 4).

## Context
Phase 4's brief (§4) asked for "an explicit, checkpointed" investigation
state machine -- PLAN -> GATHER -> TIMELINE -> DRAFT -> VERIFY -> REPAIR ->
FINALISE, terminal outcomes FINALISED or NEEDS_REVIEW -- and explicitly said:
"a custom state machine, no heavy agent framework unless justified in an
ADR." This records that decision.

## Decision
A custom state machine was built (`ledgerlight/agent/state_machine.py`),
not a third-party agent framework (LangGraph, CrewAI, the Anthropic Agent
SDK, etc.).

Reasons:

1. **The real control flow is fixed and small.** Every real investigation
   runs the exact same seven states in the exact same order; the only real
   branching is the VERIFY/REPAIR loop (bounded by `max_repair_rounds`) and
   budget checks. A general-purpose agent framework's value is mostly in
   dynamic planning/tool-selection and multi-agent orchestration -- neither
   is needed here. The brief's own PLAN state is explicitly a "deterministic
   default plan" with only an *optional* LLM plan validated against a fixed
   allowed-tool list, never free-form tool selection.
2. **Checkpointing has a real, specific shape this project needed**: one
   `InvestigationStep` row per state transition, with a real, committed
   (not merely flushed) database write, so a real process crash resumes
   from the last completed state with zero re-derivation of already-persisted
   work. This is a narrow, well-understood requirement -- a few dozen lines
   of SQLAlchemy -- not a reason to adopt a framework's own (often more
   general, and less directly inspectable) checkpointing abstraction.
3. **A framework dependency would work against this project's own
   stated priorities.** The brief's §0 ground rules require: tools strictly
   read-only, no fabrication, document content always treated as untrusted
   data, and (§9) that a document containing injected instructions produces
   no behavior change. A custom, small state machine makes every one of
   these properties directly auditable by reading `run_investigation`
   top to bottom; a general agent framework's own prompt-construction,
   tool-calling loop, and message history management would each need to be
   independently verified not to violate them, for no real benefit here.
4. **No LLM is actually in the hot path for most of this phase.** With no
   `LLM_PROVIDER`/key configured in this environment, PLAN runs its
   deterministic default plan and DRAFT uses the offline template renderer
   -- the real, default, fully-working path through this phase has no LLM
   call at all. A framework built around an LLM-driven agent loop would be
   solving a problem this phase mostly doesn't have.

## Consequences
- `run_investigation` is ~250 lines of plain Python/SQLAlchemy, directly
  readable without framework-specific documentation.
- Resuming a crashed investigation is a real, tested property
  (`test_run_investigation_resume_after_a_simulated_crash_gives_the_same_final_dossier`,
  `tests/test_agent_adversarial.py`'s dossier-hash determinism check) rather
  than something delegated to and trusted from a framework's own internals.
- If a real LLM-driven planner or renderer is added later (currently
  disabled -- no `LLM_PROVIDER` in `.env`), it plugs into PLAN/DRAFT as an
  additional, optional code path, per the brief's own §4 design -- it does
  not require re-architecting the state machine itself.
- The real cost: if this project later needs genuinely dynamic,
  multi-step tool orchestration (not the brief's current fixed plan), this
  custom state machine would need real extension rather than getting that
  behaviour from a framework for free. Not a cost paid in Phase 4.
