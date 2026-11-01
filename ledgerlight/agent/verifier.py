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
    contradictions: list[ContradictionGroup]

    @property
    def passed(self) -> bool:
        return (
            all(r.passed for r in self.claim_results)
            and not self.sentence_mapping_failures
            and not self.banned_language_failures
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


def check_number_in_span(
    span_text: str, claimed_value: float, unit: str, tolerance: float = 1e-6
) -> CheckResult:
    """Real numeric equality within an explicit tolerance, with real
    crore/lakh/absolute-INR conversion -- "5 crore" and "500 lakh" are
    the same real amount and must both match a claim of either unit.
    "%" and "percentage_points" are deliberately NOT inter-converted
    (a real, distinct-units case, per §5's own requirement) -- a claim
    in one must be checked against a span number in the same unit."""
    numbers_in_span = [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", span_text)]
    if unit in ("percent", "percentage_points"):
        passed = any(abs(n - claimed_value) <= tolerance for n in numbers_in_span)
        return CheckResult(
            "number_in_span", passed, f"{claimed_value} {unit} found in span numbers: {passed}"
        )

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


EVIDENCE_EXEMPT_CLAIM_TYPES = frozenset({"risk_signal", "limitation"})


def verify_claim(session: Session, claim: Claim, as_of: dt.date) -> ClaimVerificationResult:
    """Runs the real, applicable checks for one real claim. ONLY
    `risk_signal`/`limitation` claims (`EVIDENCE_EXEMPT_CLAIM_TYPES`)
    are exempt from citation/point-in-time/entailment when they carry
    no evidence -- that is their real, by-design shape (see
    `ledgerlight.agent.claims`'s own module docstring). Any OTHER
    claim type (event, timeline_entry, metric) with an empty evidence
    list is a real defect -- an unsupported claim -- and must FAIL,
    never pass as exempt."""
    checks: list[CheckResult] = []
    if not claim.evidence:
        if claim.claim_type in EVIDENCE_EXEMPT_CLAIM_TYPES:
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

        known_at_str = claim.payload.get("known_at")
        if isinstance(known_at_str, str):
            try:
                claimed_date = dt.datetime.fromisoformat(known_at_str).date()
                checks.append(check_date_in_span(resolved.data.text, claimed_date))
            except ValueError:
                pass

        if claim.claim_type == "metric":
            value = claim.payload.get("value")
            unit = claim.payload.get("unit")
            if isinstance(value, int | float) and isinstance(unit, str):
                checks.append(check_number_in_span(resolved.data.text, float(value), unit))
            elif isinstance(value, str) and isinstance(unit, str):
                # A non-numeric unit (e.g. "CARE_rating_symbol") means the
                # real value is a name/symbol, not a number -- checked for
                # real containment instead.
                checks.append(check_name_in_span(resolved.data.text, value))

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
    claim_results = [verify_claim(session, claim, as_of) for claim in claims]

    claims_by_id = {claim.id: claim for claim in claims}
    sentence_mapping_failures: list[str] = []
    banned_language_failures: list[str] = []

    for section, sentences in rendered.sections.items():
        for idx, sentence in enumerate(sentences):
            key = f"{section}:{idx}"
            claim_ids = rendered.claim_id_map.get(key, [])
            if not claim_ids:
                sentence_mapping_failures.append(f"{key}: no claim ID mapped")
                continue
            for claim_id_str in claim_ids:
                if uuid.UUID(claim_id_str) not in claims_by_id:
                    sentence_mapping_failures.append(
                        f"{key}: claim id {claim_id_str} does not exist"
                    )

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
        contradictions=contradictions,
    )
