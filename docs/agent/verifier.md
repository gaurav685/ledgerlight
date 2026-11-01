# Investigation Agent Verifier (Phase 4 §5)

`ledgerlight/agent/verifier.py` -- the real, final check between a
claim/rendered sentence and FINALISE. Any failure routes to REPAIR or
NEEDS_REVIEW; this module only ever reports real check results, never
decides the routing itself (`state_machine.py` does that).

## Per-claim checks (`verify_claim`)

Run per real evidence span on a claim (a claim with multiple evidence
spans is checked against each of them):

| Check | What it verifies |
|---|---|
| `citation_resolves` | the evidence span actually resolves to real `document_pages.raw_text`, via `get_evidence`, honoring point-in-time |
| `point_in_time` | the evidence's own `known_at <= as_of` |
| `date_in_span` | the claim's `known_at` date is literally found in the span text -- real ISO/DD-MM-YYYY/DD-Month-YYYY parsing, **never MM/DD/YYYY**, so a DD/MM-vs-MM/DD mix-up never silently passes |
| `number_in_span` (metric claims, numeric value) | real crore/lakh/absolute-INR unit conversion; `percent` and `percentage_points` are matched against the span's own real unit wording ("%" vs "percentage point(s)"/"pp"), never interchanged, and never validated against a bare matching number alone |
| `name_in_span` (metric claims, string value, e.g. a CARE rating symbol) | real, normalized (case/whitespace-insensitive) containment |
| `entailment` (event claims; `care_rating` metric claims) | the real local DeBERTa-v3 NLI model, checked against a **minimal natural-language hypothesis** built from the claim (e.g. "An AUD_RESIGN event occurred.") -- deliberately **not** the literal rendered "Findings" sentence, which embeds an ISO timestamp and tier jargon the model does not read as entailed prose (confirmed directly: the same real, correctly-supporting span scores ~0.24 against the literal sentence, ~0.99 against the minimal hypothesis) |

`risk_signal`/`limitation` claims, and any claim with a genuinely empty
evidence list, are a disclosed exception: `EVIDENCE_EXEMPT_CLAIM_TYPES
= {"risk_signal", "limitation"}`. Any OTHER claim type (`event`,
`timeline_entry`, `metric`) with empty evidence is a real defect --
"unsupported claim" -- and fails, never passes as exempt.

### Entailment threshold

`DEFAULT_NLI_ENTAILMENT_THRESHOLD = 0.95`, calibrated via
`scripts/calibrate_nli_threshold.py` against the small, labelled
SYNTHETIC set in `ledgerlight/agent/nli_calibration.py`
(`docs/agent/nli-calibration.json`): every threshold from 0.35 to 0.95
gave perfect precision/recall on that set, and 0.95 (the top of that
plateau) was chosen deliberately -- this project's standing rule is
that a false "verified" claim slipping into FINALISED is worse than a
real, correctly-supported claim going to REPAIR/NEEDS_REVIEW
unnecessarily. Real, disclosed limitation: the synthetic set is small
(20 clearly-separated examples); real precision/recall on genuinely
borderline claims is unverified.

## Per-sentence checks (`verify_dossier`)

For every rendered sentence (`section:index`):

- **sentence mapping**: every sentence maps to at least one real claim
  ID, and every claim ID it maps to must actually exist. A sentence with
  no mapped claim ID is a renderer defect with no real claim to blame --
  REPAIR cannot "fix" it by removing a claim, so it routes straight to
  NEEDS_REVIEW.
- **sentence values** (`check_sentence_values_in_claims`): every real
  number appearing in a sentence must exist somewhere in the payload of
  one of its own mapped claims -- real insurance against a renderer (an
  LLM renderer, or any future one) introducing a number no real claim
  actually carries. Scoped to numbers only (free-text name checking
  can't tell claim-sourced tokens from ordinary connective prose), and
  exempted for the `summary` section (its numbers are honest aggregate
  counts over the whole claim set, not any one claim's payload) and the
  `sources` section (its date/excerpt come from the cited document
  itself, already checked per claim by `verify_claim`).
- **banned language** (`check_banned_language`): fails if `fraud`,
  `fraudulent`, `scam`, `guilty`, `will default`, or `siphoned` appears
  outside a short (<=15-word), quoted, attributed excerpt. The fixed
  legal disclaimer section is exempted from this one check specifically
  (and disclosed as such in the code) -- its own text legitimately
  negates these terms ("not proof of ... fraud").
- **contradictions** (`find_contradictions`): two or more real `event`
  claims of the same `event_type_code` with different `known_at` dates
  are both presented in the "Conflicting evidence" section, attributed,
  never silently resolved to one. This is real content for a human
  reviewer, not itself a verification failure (`verify_dossier.passed`
  does not depend on it) -- it routes to human review via
  `determine_routing`'s own `CONFLICTING_EVIDENCE` check
  (`docs/agent/review-workflow.md`).

## Failing closed

A verifier crash or timeout is caught by the state machine (not this
module) and fails closed to `NEEDS_REVIEW`, reason
`verifier_crashed: ...` -- this module raises real exceptions rather
than swallowing them, so the caller can do that. Tested directly in
`tests/test_agent_adversarial.py` via a monkeypatched crash.
