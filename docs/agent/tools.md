# Investigation Agent Tools (Phase 4 §3)

`ledgerlight/agent/tools.py` -- 7 real, strictly read-only tools. Every
tool returns a frozen (`ConfigDict(frozen=True)`) `ToolEnvelope[T]`
(`untrusted: Literal[True]`), and every tool filters to
`known_at <= as_of` -- a tool never returns anything the real pipeline
could not have known as of the investigation's own as_of date.

No tool writes, deletes, executes code, or makes a network call. Every
tool takes a real SQLAlchemy `Session` and reads only; none of them
import anything from `ledgerlight.agent.models` (the agent's own write
surface) -- they read Phase 1-3's existing, already-real tables.

## The 7 tools

| Tool | Returns | Real source tables |
|---|---|---|
| `search_filings` | matching real filings | `documents`, `document_versions`, `filings` |
| `get_evidence` | one real, resolved evidence span's text | `document_pages`, point-in-time filtered |
| `get_events` | real governance red-flag events + their real evidence | `events`, `event_types`, `taxonomy_versions`, `event_fields` (excludes the separate `outcomes-1.0` taxonomy version) |
| `get_entity_history` | whether real name-change history is tracked | `companies`, `company_identifiers` |
| `get_timeline` | real events + real filings, ordered | `get_events` + `filings`/`document_versions` |
| `get_risk_score` | the real Phase 3 model score (if any) + its real, disclosed model-card limitations | `scores` (verified-coverage universe only) |
| `get_outcomes_context` | real IBBI/SEBI outcome events + real CARE rating history | the `outcomes-1.0` taxonomy version, `rating_history` |

## The untrusted-data envelope

```python
class ToolEnvelope(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)
    untrusted: Literal[True] = True
    data: T
```

Every tool result is wrapped in this envelope before it reaches any
other code -- a structural, type-level reminder (not just a comment)
that tool output, and the document/chunk text it may carry, is
untrusted data. Per the brief's §0 ground rule, this content is never
followed as an instruction anywhere downstream: the state machine never
branches on document *text* content, only on real, structured fields
(dates, event types, confidence scores) it already validated. See
`docs/agent/security.md` for the real adversarial test proving this
(`tests/test_agent_adversarial.py`'s injected-instructions case).

## Point-in-time discipline

Every tool accepts `as_of: date` and filters its own real query to
`known_at <= as_of` (or the tool's own equivalent -- e.g. `get_evidence`
resolves a specific document version only if that version was already
known as of `as_of`). This is the same real discipline Phase 1-3 already
enforce elsewhere in this project (`known_at`/`event_time` kept as two
distinct fields, never collapsed) -- reused here, not re-derived.
`tests/test_agent_tools.py` tests this filter directly for every tool
that takes an `as_of`.

## Real limitations, disclosed

- `get_risk_score` only has real data for the 5-company verified-coverage
  universe (`ledgerlight.modelling.coverage.compute_verified_coverage`);
  every other company gets a real, honest `found=False` result, never a
  fabricated score.
- `get_entity_history`'s own real limitation (`ledgerlight.agent.tools`'s
  own docstring): `companies.display_name` is a single current value in
  this project's schema, so a real historical name change is not tracked
  -- only identifier validity windows (ISIN/NSE_SYMBOL/BSE_CODE/CIN) are.
- `check_name_in_span` (the verifier's own consumer of evidence text;
  see `docs/agent/verifier.md`) does real normalized string containment,
  not entity-identifier resolution -- a disclosed limitation, not a tool
  gap, since no tool here claims to resolve names to entities.
