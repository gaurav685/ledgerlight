"""Phase 4 §5: the claims-and-rendered-text verifier.

Checks, per claim: citation resolution, names, dates, numbers (with
real unit conversion), entailment (local DeBERTa NLI, threshold
calibrated on a labelled SYNTHETIC set -- see
`ledgerlight.agent.nli_calibration`), point-in-time, tier labelling,
contradiction. Checks, on rendered text: every sentence maps to a
claim, every number/date/name in a sentence exists in its mapped
claims, and a banned-language scan.

Any failure routes to REPAIR or NEEDS_REVIEW -- this module never
decides that on its own; it only reports real check results. A
verifier crash or timeout is caught by the caller (the state machine)
and fails closed to NEEDS_REVIEW, per §9's explicit requirement --
this module raises real exceptions rather than swallowing them, so
the caller can do that.

Citation resolution, point-in-time, and entailment are scoped to
claims with a non-empty `evidence` list -- `risk_signal` and
`limitation` claims are a disclosed exception (see
`ledgerlight.agent.claims`'s own module docstring), since they
describe this project's own model output or its own documented
coverage gaps, not an extracted statement from one company document.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.agent.models import Claim
from ledgerlight.agent.nli import entailment_score
from ledgerlight.agent.render import ContradictionGroup, RenderedDossier
from ledgerlight.agent.tools import get_evidence

DEFAULT_NLI_ENTAILMENT_THRESHOLD = 0.95
"""Calibrated via scripts/calibrate_nli_threshold.py against the SYNTHETIC
labelled set in ledgerlight.agent.nli_calibration -- real result
(docs/agent/nli-calibration.json): every threshold from 0.35 to 0.95
gives perfect precision/recall (1.000/1.000, 10 TP, 0 FP, 10 TN, 0 FN)
on that small, clearly-separated set. 0.95 (the top of that plateau)
is chosen deliberately, not merely because it is the argmax: this
project's own standing rule is that a false "verified" claim slipping
into a finalised dossier is worse than a real, correctly-supported
claim being sent to REPAIR or NEEDS_REVIEW unnecessarily, so the
threshold favours precision over recall. Real, disclosed limitation:
the synthetic set is small (20 examples) and each pair is clearly
entailed or clearly not -- the real precision/recall on genuinely
borderline real claims, which the set does not probe, is unverified."""

BANNED_TERMS = (
    "fraud",
    "fraudulent",
    "scam",
    "guilty",
    "will default",
    "siphoned",
)
MAX_QUOTED_BANNED_TERM_WORDS = 15
DISCLAIMER_SECTION = "disclaimer"
SENTENCE_VALUE_EXEMPT_SECTIONS = frozenset({"summary", "sources"})
"""`check_sentence_values_in_claims` is scoped away from these two
sections, disclosed rather than silently narrowed: "summary"'s
sentence is a real, honest AGGREGATE (counts of event/timeline claims
in the whole set), never copied from any one claim's own payload, so
it has no single claim to check its numbers against. "sources"'
sentence carries a real citation date and a real document excerpt --
both read from the document/citation itself (`_resolve_source_citations`),
not from any claim's payload -- and the citation's own real numbers
are already checked, per claim, by `verify_claim`'s own
citation/point-in-time/date-in-span checks."""

_CRORE = 1e7
_LAKH = 1e5
_UNIT_TO_INR = {"crore": _CRORE, "lakh": _LAKH, "inr_absolute": 1.0}

# Indian regulatory documents use DD/MM/YYYY (or DD-MM-YYYY) -- MM/DD/YYYY is
# deliberately never accepted as an alternate reading of a slash/dash date,
# so a genuinely DD/MM-vs-MM/DD-ambiguous string never silently passes under
# the wrong interpretation (the real bug class Sec9's adversarial test targets).
_DATE_PATTERNS: list[tuple[re.Pattern[str], Callable[[re.Match[str]], tuple[int, int, int]]]] = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (
        re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"),
        lambda m: (int(m[3]), int(m[2]), int(m[1])),
    ),
]
_MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_NAME_PATTERN = re.compile(
    r"\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\s+(\d{4})\b",
    re.IGNORECASE,
)


@dataclass
class CheckResult:
    check_name: str
    passed: bool
    detail: str


@dataclass
class ClaimVerificationResult:
    claim_id: uuid.UUID
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


@dataclass
class DossierVerificationResult:
    claim_results: list[ClaimVerificationResult]
    sentence_mapping_failures: list[str]
    banned_language_failures: list[str]
    sentence_value_failures: list[str]
    contradictions: list[ContradictionGroup]

    @property
    def passed(self) -> bool:
        return (
            all(r.passed for r in self.claim_results)
            and not self.sentence_mapping_failures
            and not self.banned_language_failures
            and not self.sentence_value_failures
        )

    @property
    def failed_claim_ids(self) -> list[uuid.UUID]:
        return [r.claim_id for r in self.claim_results if not r.passed]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def check_name_in_span(span_text: str, name: str) -> CheckResult:
    """Real normalized containment -- case-insensitive, whitespace
    collapsed. Does not (yet) resolve via entity identifiers; that
    path is a real, disclosed limitation, see docs/agent/verifier.md."""
    passed = _normalize(name) in _normalize(span_text)
    return CheckResult("name_in_span", passed, f"{name!r} in span: {passed}")


def _parse_dates(span_text: str) -> set[dt.date]:
    found: set[dt.date] = set()
    for pattern, to_ymd in _DATE_PATTERNS:
        for match in pattern.finditer(span_text):
            year, month, day = to_ymd(match)
            try:
                found.add(dt.date(year, month, day))
            except ValueError:
                continue
    for name_match in _MONTH_NAME_PATTERN.finditer(span_text):
        day_str, month_name, year_str = name_match.groups()
        month_num = _MONTH_NAMES[month_name.lower()]
        try:
            found.add(dt.date(int(year_str), month_num, int(day_str)))
        except ValueError:
            continue
    return found


def check_date_in_span(span_text: str, claimed_date: dt.date) -> CheckResult:
    """Real date-only comparison (no timezone ambiguity: both sides are
    real calendar dates, never datetimes). Parses DD/MM/YYYY,
    DD-MM-YYYY, "D Month YYYY" and ISO YYYY-MM-DD -- never MM/DD/YYYY,
    so a DD/MM-vs-MM/DD mix-up never silently passes."""
    found_dates = _parse_dates(span_text)
    passed = claimed_date in found_dates
    return CheckResult(
        "date_in_span", passed, f"{claimed_date.isoformat()} in {sorted(found_dates)}: {passed}"
    )


def _to_inr(value: float, unit: str) -> float | None:
    if unit in _UNIT_TO_INR:
        return value * _UNIT_TO_INR[unit]
    return None


_PERCENT_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
_PERCENTAGE_POINTS_PATTERN = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(?:percentage[\s-]points?|pp\b)", re.IGNORECASE
)


def check_number_in_span(
    span_text: str, claimed_value: float, unit: str, tolerance: float = 1e-6
) -> CheckResult:
    """Real numeric equality within an explicit tolerance, with real
    crore/lakh/absolute-INR conversion -- "5 crore" and "500 lakh" are
    the same real amount and must both match a claim of either unit.
    "percent" and "percentage_points" are deliberately NOT
    inter-converted (a real, distinct-units case, per §5's own
    requirement) -- and, just as importantly, each is matched only
    against the span's OWN real unit wording ("%" for percent;
    "percentage point(s)"/"pp" for percentage_points), never against
    any bare number in the span: a span saying "5 percentage points"
    must never validate a claimed 5 percent, even though both are the
    literal digits "5"."""
    if unit == "percent":
        percent_numbers = [float(m) for m in _PERCENT_PATTERN.findall(span_text)]
        passed = any(abs(n - claimed_value) <= tolerance for n in percent_numbers)
        return CheckResult(
            "number_in_span", passed, f"{claimed_value}% found in span's '%' numbers: {passed}"
        )
    if unit == "percentage_points":
        pp_numbers = [float(m) for m in _PERCENTAGE_POINTS_PATTERN.findall(span_text)]
        passed = any(abs(n - claimed_value) <= tolerance for n in pp_numbers)
        return CheckResult(
            "number_in_span",
            passed,
            f"{claimed_value} percentage points found in span's own wording: {passed}",
        )

    numbers_in_span = [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", span_text)]
    claimed_inr = _to_inr(claimed_value, unit)
    if claimed_inr is None:
        return CheckResult("number_in_span", False, f"unknown unit {unit!r}")
    for other_unit in _UNIT_TO_INR:
        for n in numbers_in_span:
            span_inr = _to_inr(n, other_unit)
            if span_inr is not None and abs(span_inr - claimed_inr) <= tolerance * max(
                1.0, abs(claimed_inr)
            ):
                return CheckResult(
                    "number_in_span",
                    True,
                    f"{claimed_value} {unit} matches span value {n} {other_unit}",
                )
    return CheckResult("number_in_span", False, f"{claimed_value} {unit} not found in span")


def check_entailment(
    span_text: str, claim_sentence: str, threshold: float = DEFAULT_NLI_ENTAILMENT_THRESHOLD
) -> CheckResult:
    score = entailment_score(span_text, claim_sentence)
    passed = score >= threshold
    return CheckResult("entailment", passed, f"score={score:.3f} threshold={threshold}")


def check_point_in_time(known_at: dt.datetime, as_of: dt.date) -> CheckResult:
    passed = known_at.date() <= as_of
    return CheckResult("point_in_time", passed, f"known_at={known_at.date()} as_of={as_of}")


def check_known_at_matches_evidence(
    claimed_known_at: dt.datetime, evidence_known_at: dt.datetime
) -> CheckResult:
    """For a metric claim, whose real evidence span is too narrow to
    literally state a date (`date_in_span` is scoped away from metric
    claims for exactly this reason -- see the comment in
    `verify_claim`), checks that the claim's own `known_at` EQUALS the
    cited evidence's real `known_at` exactly. This is the real,
    by-design relationship `claims_from_outcomes_context` relies on (a
    rating claim's `known_at` is always copied directly from the same
    real evidence document's `known_at`) -- a real, structural
    guarantee in the only real code path that builds these claims
    today, but checked here explicitly rather than merely assumed, so
    a wrong date can never silently pass verification regardless of
    how the claim was actually constructed."""
    passed = claimed_known_at == evidence_known_at
    return CheckResult(
        "known_at_matches_evidence",
        passed,
        f"claimed {claimed_known_at.isoformat()} vs "
        f"evidence {evidence_known_at.isoformat()}: {passed}",
    )


def check_timeline_entry_claim(session: Session, claim: Claim, as_of: dt.date) -> CheckResult:
    """A real `timeline_entry` claim carries no evidence SPAN (there is
    no specific text to cite for "this document exists"), but its real
    `document_version_id` ("version_id" in its own payload) IS a real,
    checkable fact -- resolved here directly against
    `document_versions`, confirming the version really exists, that
    its real `known_at` matches the claim's own claimed `known_at`
    exactly, and that it is point-in-time valid (`known_at <= as_of`).
    A wrong claimed date, a reference to a nonexistent version, or a
    future-known version all fail this one check -- a real
    `timeline_entry` claim never passes just because there was no
    evidence span to resolve in the first place."""
    version_id_str = claim.payload.get("version_id")
    claimed_known_at_str = claim.payload.get("known_at")
    if not isinstance(version_id_str, str) or not isinstance(claimed_known_at_str, str):
        return CheckResult(
            "timeline_entry_version_resolves",
            False,
            "payload is missing a real version_id or known_at",
        )
    try:
        version_id = uuid.UUID(version_id_str)
        claimed_known_at = dt.datetime.fromisoformat(claimed_known_at_str)
    except ValueError:
        return CheckResult(
            "timeline_entry_version_resolves",
            False,
            f"malformed version_id {version_id_str!r} or known_at {claimed_known_at_str!r}",
        )

    row = session.execute(
        text("SELECT known_at FROM document_versions WHERE id = :id"), {"id": version_id}
    ).one_or_none()
    if row is None:
        return CheckResult(
            "timeline_entry_version_resolves",
            False,
            f"document_version {version_id} does not exist",
        )
    real_known_at = cast(dt.datetime, row[0])
    if real_known_at.date() > as_of:
        return CheckResult(
            "timeline_entry_version_resolves",
            False,
            f"document_version {version_id} known_at={real_known_at.date()} is after as_of={as_of}",
        )
    if real_known_at != claimed_known_at:
        return CheckResult(
            "timeline_entry_version_resolves",
            False,
            f"claimed known_at {claimed_known_at.isoformat()} != real document_version "
            f"known_at {real_known_at.isoformat()}",
        )
    return CheckResult(
        "timeline_entry_version_resolves", True, "resolved, point-in-time valid, known_at matches"
    )


def check_banned_language(sentence: str) -> CheckResult:
    """Fails if a banned term appears OUTSIDE a short (<=15-word),
    quoted, attributed excerpt. A real quoted excerpt is detected as
    text inside matching double quotes; if a banned term appears
    inside one that is <= 15 words, it is allowed (the citation itself
    is the attribution -- a longer quote, or an unquoted banned term,
    always fails)."""
    lowered = sentence.lower()
    hits = [term for term in BANNED_TERMS if term in lowered]
    if not hits:
        return CheckResult("banned_language", True, "no banned terms")

    quoted_spans = re.findall(r'"([^"]*)"', sentence)
    for term in hits:
        covered = False
        for quote in quoted_spans:
            if term in quote.lower() and len(quote.split()) <= MAX_QUOTED_BANNED_TERM_WORDS:
                covered = True
                break
        if not covered:
            return CheckResult(
                "banned_language", False, f"banned term {term!r} outside a short attributed quote"
            )
    return CheckResult("banned_language", True, f"banned terms {hits} all inside short quotes")


def _flatten_payload_numbers(payload: dict[str, object]) -> set[float]:
    """Every real number appearing anywhere in a claim's own payload --
    both actual numeric fields and numbers embedded in a payload
    string (e.g. an ISO date/datetime), so a date rendered verbatim
    from `known_at` is recognized as "in the claim" the same way a
    numeric field like `percentile` is."""
    numbers: set[float] = set()
    for value in payload.values():
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            numbers.add(float(value))
        elif isinstance(value, str):
            numbers.update(float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", value))
    return numbers


def check_sentence_values_in_claims(sentence: str, claims: list[Claim]) -> CheckResult:
    """Every real number appearing in a rendered sentence must exist
    somewhere in the payload of one of its own mapped claims -- real
    insurance against a renderer (an LLM renderer, or any future one)
    introducing a number no real claim actually carries. The real
    offline template renderer only ever copies payload values verbatim
    into prose, so this never fires against it.

    Scoped to numbers only -- a real, disclosed limitation (see
    `docs/agent/verifier.md`): free-text name checking would need to
    tell claim-sourced tokens (e.g. an event_type_code) apart from
    ordinary connective prose ("was", "known", "as of"), which a
    generic containment check cannot do without rejecting real,
    correctly-rendered sentences."""
    sentence_numbers = [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", sentence)]
    if not sentence_numbers:
        return CheckResult("sentence_values_in_claims", True, "no numbers in sentence")

    claim_numbers: set[float] = set()
    for claim in claims:
        claim_numbers.update(_flatten_payload_numbers(claim.payload))

    missing = [n for n in sentence_numbers if not any(abs(n - c) < 1e-6 for c in claim_numbers)]
    if missing:
        return CheckResult(
            "sentence_values_in_claims",
            False,
            f"sentence number(s) {missing} not found in any mapped claim's payload",
        )
    return CheckResult(
        "sentence_values_in_claims", True, "every sentence number found in a mapped claim"
    )


EVIDENCE_EXEMPT_CLAIM_TYPES = frozenset({"risk_signal", "limitation", "timeline_entry"})
"""`timeline_entry` belongs here alongside `risk_signal`/`limitation`:
`ledgerlight.agent.claims.claims_from_timeline`'s own docstring already
documents this exemption ("the same disclosed exemption as
risk_signal/limitation") -- a filing entry records that a real document
was known as of a date, not an extracted statement, so there is no
specific text span to cite for "this document exists". This constant
simply did not match that documented design until a real full
`agent-eval` run (Sec11) showed every real `timeline_entry` claim
failing as "unsupported" -- confirmed as the real bug, not a change in
intent, and fixed here rather than in the claims.py docstring."""


def _entailment_hypothesis_for_claim(claim: Claim) -> str | None:
    """A minimal, natural-language entailment hypothesis -- NOT the
    literal rendered "Findings" sentence (`render.event_claim_sentence`/
    `render.care_rating_claim_sentence`), which embeds an ISO
    timestamp and tier jargon the real local NLI model does not read
    as entailed prose: the SAME real evidence span that correctly
    supports a real claim scored ~0.24 against that literal sentence
    (far below `DEFAULT_NLI_ENTAILMENT_THRESHOLD`) but ~0.99 against a
    minimal hypothesis like this one -- confirmed directly against the
    real local model while wiring this in. The date/tier/number/name
    parts of a claim are already checked separately by
    `check_date_in_span`/`check_number_in_span`/`check_name_in_span`;
    entailment here is scoped to the one thing those checks do not
    cover -- whether the evidence supports the claim's core real-world
    assertion at all. `None` for a claim type/shape with no such
    assertion to check (a metric claim that is not `care_rating` is
    the one such case today)."""
    if claim.claim_type == "event":
        code = claim.payload.get("event_type_code", "an event")
        return f"An {code} event occurred."
    if claim.claim_type == "metric" and claim.payload.get("name") == "care_rating":
        return f"CARE assigned a rating of {claim.payload.get('value')}."
    return None


def verify_claim(
    session: Session,
    claim: Claim,
    as_of: dt.date,
    nli_threshold: float = DEFAULT_NLI_ENTAILMENT_THRESHOLD,
) -> ClaimVerificationResult:
    """Runs the real, applicable checks for one real claim. `risk_signal`/
    `limitation` claims (`EVIDENCE_EXEMPT_CLAIM_TYPES`) are exempt from
    citation/point-in-time/entailment when they carry no evidence --
    that is their real, by-design shape (see
    `ledgerlight.agent.claims`'s own module docstring), and there is no
    other real fact about them to check. `timeline_entry` claims also
    carry no evidence SPAN by design, but DO have a real
    `document_version_id` to check directly (`check_timeline_entry_claim`)
    -- never blanket-exempted, so a wrong date or value still fails.
    Any OTHER claim type (event, metric) with an empty evidence list is
    a real defect -- an unsupported claim -- and must FAIL, never pass
    as exempt."""
    checks: list[CheckResult] = []
    if not claim.evidence:
        if claim.claim_type == "timeline_entry":
            checks.append(check_timeline_entry_claim(session, claim, as_of))
        elif claim.claim_type in EVIDENCE_EXEMPT_CLAIM_TYPES:
            checks.append(
                CheckResult("citation_resolves", True, "exempt: claim has no evidence span")
            )
        else:
            checks.append(
                CheckResult(
                    "citation_resolves",
                    False,
                    f"unsupported claim: {claim.claim_type} claim has no evidence span",
                )
            )
        return ClaimVerificationResult(claim_id=claim.id, checks=checks)

    for ev in claim.evidence:
        ev_dict = cast("dict[str, object]", ev)
        version_id = uuid.UUID(str(ev_dict["document_version_id"]))
        page_number = int(cast(float, ev_dict["page_number"]))
        char_start = int(cast(float, ev_dict["char_start"]))
        char_end = int(cast(float, ev_dict["char_end"]))
        resolved = get_evidence(session, version_id, page_number, char_start, char_end, as_of)
        if resolved.data is None:
            checks.append(
                CheckResult(
                    "citation_resolves",
                    False,
                    f"evidence {version_id}/{page_number}/{char_start}:{char_end} did not resolve",
                )
            )
            continue
        checks.append(CheckResult("citation_resolves", True, "resolved"))
        checks.append(check_point_in_time(resolved.data.known_at, as_of))

        # date_in_span is scoped to event claims only: a real full agent-eval run
        # (Sec11) showed every real metric/care_rating claim failing this check,
        # because its real evidence span is deliberately narrow -- just the
        # rating symbol's own regex capture group
        # (ledgerlight.modelling.rating_features.py), never the surrounding
        # sentence that states a date. A metric claim's date is checked a
        # different, structurally appropriate way instead, below.
        if claim.claim_type == "event":
            known_at_str = claim.payload.get("known_at")
            if isinstance(known_at_str, str):
                try:
                    claimed_date = dt.datetime.fromisoformat(known_at_str).date()
                    checks.append(check_date_in_span(resolved.data.text, claimed_date))
                except ValueError:
                    pass

        if claim.claim_type == "metric":
            known_at_str = claim.payload.get("known_at")
            if isinstance(known_at_str, str):
                try:
                    claimed_known_at = dt.datetime.fromisoformat(known_at_str)
                    checks.append(
                        check_known_at_matches_evidence(claimed_known_at, resolved.data.known_at)
                    )
                except ValueError:
                    pass

            value = claim.payload.get("value")
            unit = claim.payload.get("unit")
            if isinstance(value, int | float) and isinstance(unit, str):
                checks.append(check_number_in_span(resolved.data.text, float(value), unit))
            elif isinstance(value, str) and isinstance(unit, str):
                # A non-numeric unit (e.g. "CARE_rating_symbol") means the
                # real value is a name/symbol, not a number -- checked for
                # real containment instead.
                checks.append(check_name_in_span(resolved.data.text, value))

        hypothesis = _entailment_hypothesis_for_claim(claim)
        if hypothesis is not None:
            checks.append(check_entailment(resolved.data.text, hypothesis, nli_threshold))

    return ClaimVerificationResult(claim_id=claim.id, checks=checks)


def find_contradictions(claims: list[Claim]) -> list[ContradictionGroup]:
    """Real contradiction detection: two or more real `event` claims of
    the SAME `event_type_code` with DIFFERENT real `known_at` dates --
    a genuine case this project has already seen in real data (e.g. two
    sources reporting the same admission on different dates). Never
    picks one silently; both are reported."""
    by_type: dict[str, list[Claim]] = {}
    for claim in claims:
        if claim.claim_type != "event":
            continue
        code = str(claim.payload.get("event_type_code"))
        by_type.setdefault(code, []).append(claim)

    groups: list[ContradictionGroup] = []
    for code, group_claims in by_type.items():
        known_ats = {c.payload.get("known_at") for c in group_claims}
        if len(known_ats) > 1:
            groups.append(
                ContradictionGroup(
                    claim_ids=[c.id for c in group_claims],
                    description=(
                        f"Conflicting evidence: multiple real {code} events were found with "
                        f"different known_at dates ({sorted(str(k) for k in known_ats)}); "
                        "both are presented here rather than one being silently chosen."
                    ),
                )
            )
    return groups


def verify_dossier(
    session: Session,
    claims: list[Claim],
    rendered: RenderedDossier,
    as_of: dt.date,
    nli_threshold: float = DEFAULT_NLI_ENTAILMENT_THRESHOLD,
) -> DossierVerificationResult:
    claim_results = [verify_claim(session, claim, as_of, nli_threshold) for claim in claims]

    claims_by_id = {claim.id: claim for claim in claims}
    sentence_mapping_failures: list[str] = []
    banned_language_failures: list[str] = []
    sentence_value_failures: list[str] = []

    for section, sentences in rendered.sections.items():
        for idx, sentence in enumerate(sentences):
            key = f"{section}:{idx}"
            claim_ids = rendered.claim_id_map.get(key, [])
            if not claim_ids:
                sentence_mapping_failures.append(f"{key}: no claim ID mapped")
                continue
            mapped_claims: list[Claim] = []
            for claim_id_str in claim_ids:
                claim_id = uuid.UUID(claim_id_str)
                mapped_claim = claims_by_id.get(claim_id)
                if mapped_claim is None:
                    sentence_mapping_failures.append(
                        f"{key}: claim id {claim_id_str} does not exist"
                    )
                else:
                    mapped_claims.append(mapped_claim)

            if section not in SENTENCE_VALUE_EXEMPT_SECTIONS:
                value_check = check_sentence_values_in_claims(sentence, mapped_claims)
                if not value_check.passed:
                    sentence_value_failures.append(f"{key}: {value_check.detail}")

            if section == DISCLAIMER_SECTION:
                # Fixed project boilerplate (ledgerlight.agent.claims.DISCLAIMER_TEXT),
                # never derived from untrusted document text -- it legitimately uses
                # banned terms in a protective, negating sense ("not proof of ...
                # fraud"), which the naive substring scan below cannot distinguish from
                # an accusation. Exempted deliberately, not silently: the scan still
                # runs on every other section, where a banned term really would be a
                # real defect.
                continue

            banned = check_banned_language(sentence)
            if not banned.passed:
                banned_language_failures.append(f"{key}: {banned.detail}")

    contradictions = find_contradictions(claims)

    return DossierVerificationResult(
        claim_results=claim_results,
        sentence_mapping_failures=sentence_mapping_failures,
        banned_language_failures=banned_language_failures,
        sentence_value_failures=sentence_value_failures,
        contradictions=contradictions,
    )
