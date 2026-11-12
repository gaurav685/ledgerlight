"""Silver label proposals: a keyword/rule baseline run over real chunks,
proposing an event_type (or 'none') per chunk. Every row this writes has
label_source='ai_assisted_unreviewed' -- only the label-review CLI
(ledgerlight.knowledge.label_review) can promote a row to
'human_reviewed', which is what makes a label GOLD. This module never
sets label_source itself to anything else.

PROPOSER_VERSION 2 (Phase 3 §1.4, detector hardening): gold review of
version 1's silver proposals (80 items, docs/phase-2/phase-2-report.md
§19.2) found real, high error rates driven almost entirely by loose
whole-chunk keyword co-occurrence matching boilerplate text instead of
the real event:
  - AUDIT_QUAL (100% error, n=2): both false positives were Emphasis-of-
    Matter paragraphs, which taxonomy v1.0 explicitly says is NOT a
    qualification -- v1 wrongly put "emphasis of matter" in the same
    trigger group as "qualified opinion"/"adverse opinion"/"disclaimer
    of opinion". v2 removes it from the trigger entirely.
  - ID_EXIT (83% error, n=6): false positives were board-composition
    roster/KMP tables where a resignation belonging to one row's person
    (e.g. a Company Secretary) co-occurred, in a whole-chunk sense, with
    an unrelated Independent Director's name in a different row, plus a
    real resignation of a *Non-Executive* (not Independent) Director.
    v2 requires resignation/cessation language, the specific role, and a
    named person -- same row only when the chunk is a detected numbered
    table (>= 3 "\x07N\t"-style row markers, a real structural signal in
    this corpus, unlike plain "\n" which PDF line-wrap also uses inside
    a single sentence), else a 400-char window. Real residual limitation
    found and kept, not hidden: 3 of 4 original false positives are
    numbered-table rows that are now *correctly* detected as a genuine
    named, dated departure in that row (one even reclassifies correctly
    to KMP_EXIT, since the row says "Company Secretary", not
    "Independent Director") -- but the original reviewer rejected that
    exact fact when it appeared incidentally inside an unrelated RPT/KMP
    listing table, while accepting the identical fact when it appeared
    in a dedicated narrative announcement elsewhere. Distinguishing
    "dedicated disclosure" from "incidental mention in an unrelated
    table" needs document-level context this rule-based detector doesn't
    have -- flagged for human reconsideration, not resolved unilaterally.
  - RPT_GROWTH (67% error, n=12): false positives were RPT *policy*
    boilerplate, CSR figures, auditor-remuneration tables, and sexual-
    harassment-complaint counts that happened to contain the phrase
    "related party transaction" somewhere in a number-dense chunk. v2
    requires at least 2 distinct numeric amounts near the RPT phrase
    itself (7 of 8 original false positives now correctly suppressed).
    Real tension found and kept, not hidden: all 3 gold-ACCEPTED v1
    RPT_GROWTH examples (governance-policy prose, a SEBI-order
    paragraph, a boilerplate directors'-responsibility statement) no
    longer match -- none of them actually contained quantified 2-period
    RPT amounts, which is exactly what this phase's brief requires as
    the evidence bar; and 1 of 8 original false positives (a routine,
    mandatory RPT disclosure table with real multi-period figures but no
    verified growth *direction*) still matches, since "numeric amounts
    for >= 2 periods" is the brief's literal bar, not "verified increase"
    -- true growth-direction verification would need real per-
    counterparty table parsing, out of scope here. Both are flagged as
    policy questions for a human, not resolved unilaterally.
  - PLEDGE_UP (57% error, n=7): per this phase's explicit instruction,
    PLEDGE_UP must be computed ONLY from structured shareholding/
    encumbrance numbers, never free text. v2 removes the free-text
    PLEDGE_UP rule entirely -- this proposer no longer proposes
    PLEDGE_UP at all (see ledgerlight.knowledge.taxonomy.pledge_up_triggers
    for the structured-data rule, which has no real extractor feeding it
    yet in this corpus).
  - AUD_RESIGN (33% error, n=6): the one type with a real extractor and
    a clean 100% precision/recall on the frozen test split -- but v1's
    rule ("auditor" + "resign" anywhere in the chunk) is still looser
    than it should be. v2 requires resignation language, a "statutory
    auditor" reference (not just "auditor"), and a date, all within a
    proximity window.

See docs/modelling/event-reliability.md and docs/phase-3/phase-3-report.md
§5 for the real before/after gold-validation precision/recall this
produced.

PROPOSER_VERSION 3 (Phase 6 Correction 1 §5, negation hardening): v2's
resign/cease proximity check has no negation awareness at all -- real
corpus examples found on the dev/validation splits (never the frozen
test split -- see docs/phase-6/evidence/sec5-negation-hardening.md for
the real before/after this produced):
  - A gold-reviewed AUD_RESIGN chunk ("There has been no resignation
    of the statutory auditors during the year") has "resign" and
    "statutory auditor" genuinely close together, in a real negated
    disclosure -- v2 happens to already reject this ONE chunk anyway,
    via its own separate "a date must exist somewhere in the chunk"
    requirement (this specific chunk has none), not because of
    negation. The negation gap is still real: a future chunk with the
    same negated phrasing AND an unrelated nearby date would wrongly
    pass v2's checks.
  - A real, separate ID_EXIT positive (gold-accepted) sits right next
    to a negated clause in the same chunk ("none of the Independent
    Directors ... have resigned") -- confirms this negated-resign
    phrasing is real and common in this corpus, not a one-off.
v3 adds `ledgerlight.knowledge.evidence.is_negated_before`: before
counting a resign/cease match as positive evidence, the text
immediately preceding it must not contain a negating word ("no",
"not", "nil", "never", "none"). Applied to both _aud_resign and
_director_or_kmp_exit -- the only two rules that anchor on resign/
cease language at all; the simple keyword rules (RATING_ACT,
RESULT_DELAY, FORENSIC, RPT_GROWTH) were checked against the same
dev/validation set and showed no real negation-driven false positive,
so are left as-is rather than guessing at an unverified fix. Measured
effect on the real corpus (docs/phase-6/evidence/
sec5-negation-hardening.md): zero chunks' own predictions change,
confirmed by running v2 and v3 head-to-head over all 2593 real
chunks -- every negated occurrence in THIS corpus today already fails
one of v2's OTHER independent requirements. A real, disclosed,
preventative hardening against a confirmed real text pattern, not a
retroactive fix to a currently-live miscount.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.evidence import find_dates_in_text, is_negated_before
from ledgerlight.knowledge.models import Chunk, LabelItem

PROPOSER_NAME = "keyword-rule-baseline"
PROPOSER_VERSION = "3"

# How close two pieces of evidence must be (in characters) to count as
# "about the same thing" -- generous enough for real disclosure text
# that interposes firm/person names and clause boundaries between a
# subject and its verb (see the AUD_RESIGN Phase 2 proximity-regex bug:
# a too-tight window missed real matches), but far tighter than treating
# a whole ~1000-1400 char chunk as one undifferentiated bag of words
# (which is what let roster tables and multi-topic chunks false-positive
# in v1).
EVIDENCE_WINDOW_CHARS = 400
# Numbered-row marker this corpus's real roster/KMP-listing tables use
# (e.g. "\x078\t\nMr. X - Independent Director\n\t\n\x079\t\nMs. Y - ...").
# A genuine structural signal, unlike plain "\n" -- PDF line-wrap also
# uses "\n" inside a single logical sentence (see the \s+ note above),
# so splitting on newlines can't distinguish "new table row" from
# "the same sentence wrapped". At least 3 markers means this chunk is
# a numbered list/table, not narrative prose; a candidate table.
_ROW_MARKER_PATTERN = re.compile(r"\x07\d+\t")
MIN_ROW_MARKERS_FOR_TABLE = 3

# Real extracted text frequently wraps mid-phrase ("ceased to \nbe",
# "statutory\nauditor") -- every multi-word pattern below uses `\s+`
# between words, never a literal space, or it silently misses real
# matches across a line break (found while validating this hardening
# against real gold-reviewed chunks: a true ID_EXIT positive was missed
# because "ceased to be" appeared in the text as "ceased to \nbe").
# Note: this pattern is intentionally never matched case-insensitively
# -- "Mr"/"Dr"/capitalized-name-parts are the whole signal that
# distinguishes a real named person from a lowercase common phrase. It
# must therefore always be matched against the ORIGINAL-case text, not
# text.lower() (a real bug found while validating this hardening: every
# other check in this module runs on lowercased text, which silently
# zeroed out every person-name match until this was caught against a
# real gold-reviewed true positive).
_PERSON_NAME_PATTERN = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr)\.?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\b"
)
_RESIGN_OR_CEASE_PATTERN = re.compile(r"resign|ceas(?:e|ed|ing)", re.IGNORECASE)
_STATUTORY_AUDITOR_PATTERN = re.compile(r"statutory\s+auditor", re.IGNORECASE)
_INDEPENDENT_DIRECTOR_PATTERN = re.compile(r"independent\s+director", re.IGNORECASE)
_KMP_ROLE_PATTERN = re.compile(
    r"chief\s+financial\s+officer|chief\s+executive\s+officer|company\s+secretary"
    r"|whole[- ]?\s*time\s+director|managing\s+director",
    re.IGNORECASE,
)
_RPT_PHRASE_PATTERN = re.compile(r"related\s+part(?:y|ies)\s+transactions?", re.IGNORECASE)
_AMOUNT_PATTERN = re.compile(
    r"(?:rs\.?|inr|₹)\s?\d[\d,]*(?:\.\d+)?|(?<!\w)\d[\d,]{2,}(?:\.\d+)?\s?(?:crore|lakh|lakhs|cr\.?)\b",
    re.IGNORECASE,
)


def _positions(pattern: re.Pattern[str], text: str) -> list[int]:
    return [m.start() for m in pattern.finditer(text)]


def _non_negated_positions(pattern: re.Pattern[str], text: str) -> list[int]:
    return [p for p in _positions(pattern, text) if not is_negated_before(text, p)]


def _any_within_window(positions_a: list[int], positions_b: list[int], window: int) -> bool:
    return any(abs(a - b) <= window for a in positions_a for b in positions_b)


def _row_segments(text: str) -> list[str] | None:
    """Splits `text` into row segments at each numbered-row marker, if
    there are enough markers to call this a table. Returns None for
    ordinary narrative text (use the character-window check instead)."""
    markers = list(_ROW_MARKER_PATTERN.finditer(text))
    if len(markers) < MIN_ROW_MARKERS_FOR_TABLE:
        return None
    bounds = [m.start() for m in markers] + [len(text)]
    return [text[bounds[i] : bounds[i + 1]] for i in range(len(bounds) - 1)]


def _director_or_kmp_exit(text: str, role_pattern: re.Pattern[str]) -> bool:
    """Shared evidence rule for ID_EXIT/KMP_EXIT: resignation/cessation
    language + the specific role + a named person. In a detected
    numbered roster/KMP table, all three must belong to the SAME row
    (otherwise a resignation in one row and an unrelated role in the
    next row -- a different person -- would false-positive, which is
    exactly what v1's whole-chunk co-occurrence did). Outside such a
    table, a generous character window is used instead (real narrative
    text interposes firm/person names between subject and verb)."""
    segments = _row_segments(text)
    if segments is not None:
        return any(
            _non_negated_positions(_RESIGN_OR_CEASE_PATTERN, seg)
            and role_pattern.search(seg)
            and _PERSON_NAME_PATTERN.search(seg)
            for seg in segments
        )

    resign_positions = _non_negated_positions(_RESIGN_OR_CEASE_PATTERN, text)
    role_positions = _positions(role_pattern, text)
    name_positions = _positions(_PERSON_NAME_PATTERN, text)
    if not (resign_positions and role_positions and name_positions):
        return False
    return _any_within_window(
        resign_positions, role_positions, EVIDENCE_WINDOW_CHARS
    ) and _any_within_window(resign_positions, name_positions, EVIDENCE_WINDOW_CHARS)


def _aud_resign(text: str) -> bool:
    resign_positions = _non_negated_positions(_RESIGN_OR_CEASE_PATTERN, text)
    auditor_positions = _positions(_STATUTORY_AUDITOR_PATTERN, text)
    if not (resign_positions and auditor_positions):
        return False
    if not _any_within_window(resign_positions, auditor_positions, EVIDENCE_WINDOW_CHARS):
        return False
    # A date must exist somewhere in the chunk -- deliberately NOT
    # windowed around the resign/auditor anchors like the other checks:
    # a real gold true positive (a covering letter) had its date in the
    # letterhead, structurally separate from the resignation paragraph
    # later in the same chunk. Proximity between resign+auditor is
    # already the main filter; "a date exists in this chunk at all" is a
    # weaker, confirmatory requirement on top of that, not the primary
    # one -- reuses the same date-candidate regex/parsing already relied
    # on for evidence verification (ledgerlight.knowledge.evidence).
    return bool(find_dates_in_text(text))


def _rpt_growth(text: str) -> bool:
    rpt_positions = _positions(_RPT_PHRASE_PATTERN, text)
    if not rpt_positions:
        return False
    amount_positions = _positions(_AMOUNT_PATTERN, text)
    if len(amount_positions) < 2:
        return False
    nearby_amounts = {
        a
        for a in amount_positions
        if any(abs(a - r) <= EVIDENCE_WINDOW_CHARS for r in rpt_positions)
    }
    return len(nearby_amounts) >= 2


def _audit_qual(text_lower: str) -> bool:
    # "emphasis of matter" deliberately excluded -- taxonomy v1.0: it is
    # a separate, lower-severity flag, never a qualification.
    return any(
        phrase in text_lower
        for phrase in ("qualified opinion", "adverse opinion", "disclaimer of opinion")
    )


# Rules that don't need the stricter per-type evidence logic above --
# unchanged from v1 except AUDIT_QUAL (moved to `_audit_qual`) and
# PLEDGE_UP (removed entirely, see module docstring).
def _contains_all(text_lower: str, *term_groups: tuple[str, ...]) -> bool:
    return all(any(term in text_lower for term in group) for group in term_groups)


_SIMPLE_EVENT_TYPE_RULES: list[tuple[str, tuple[tuple[str, ...], ...]]] = [
    ("FORENSIC", (("forensic audit",),)),
    (
        "RATING_ACT",
        (("downgrade", "downgraded", "rating withdrawn", "negative watch", "negative outlook"),),
    ),
    ("RESULT_DELAY", (("delay", "delayed"), ("result", "results"))),
]


def propose_event_type(text: str) -> str | None:
    """Returns an event_type code, or None for 'none'. Order: the
    stricter, evidence-based rules are checked first (AUD_RESIGN,
    ID_EXIT, KMP_EXIT, RPT_GROWTH, AUDIT_QUAL), then the unchanged
    simple keyword rules -- first match wins, same policy as v1."""
    # _aud_resign/_director_or_kmp_exit need the ORIGINAL-case text (see
    # _PERSON_NAME_PATTERN's note); their phrase patterns are
    # case-insensitive themselves. Everything else only ever does plain
    # substring checks, so it uses the lowercased text as before.
    text_lower = text.lower()

    if _aud_resign(text):
        return "AUD_RESIGN"
    if _audit_qual(text_lower):
        return "AUDIT_QUAL"
    if _director_or_kmp_exit(text, _INDEPENDENT_DIRECTOR_PATTERN):
        return "ID_EXIT"
    if _director_or_kmp_exit(text, _KMP_ROLE_PATTERN):
        return "KMP_EXIT"
    if _rpt_growth(text_lower):
        return "RPT_GROWTH"

    for code, term_groups in _SIMPLE_EVENT_TYPE_RULES:
        if _contains_all(text_lower, *term_groups):
            return code
    return None


@dataclass
class LabelProposalStats:
    chunks_seen: int = 0
    proposals_created: int = 0
    already_proposed: int = 0
    by_event_type: dict[str, int] = field(default_factory=dict)


def propose_labels(
    session: Session,
    *,
    none_sample_rate: int = 17,
    only_chunk_ids: set[uuid.UUID] | None = None,
) -> LabelProposalStats:
    """Proposes a label for every chunk matching a pattern, plus every
    Nth non-matching chunk (none_sample_rate) as an explicit 'none'
    example -- event classifiers need negative examples too, and
    labelling every single non-matching chunk would make 'none'
    overwhelmingly dominant without adding information.

    `only_chunk_ids` restricts the scan to a specific set of chunks --
    used by tests to avoid touching the real corpus's chunks at all."""
    stats = LabelProposalStats()
    stmt = select(Chunk).order_by(Chunk.id)
    if only_chunk_ids is not None:
        stmt = stmt.where(Chunk.id.in_(only_chunk_ids))
    chunks = session.scalars(stmt).all()

    existing_chunk_ids = {
        row[0]
        for row in session.execute(
            select(LabelItem.chunk_id).where(
                LabelItem.proposer_name == PROPOSER_NAME,
                LabelItem.proposer_version == PROPOSER_VERSION,
            )
        ).all()
    }

    for chunk in chunks:
        stats.chunks_seen += 1
        if chunk.id in existing_chunk_ids:
            stats.already_proposed += 1
            continue

        event_type = propose_event_type(chunk.text)
        if event_type is None:
            # Deterministic by chunk.id, NOT by position in this query's
            # result set -- a real bug was found here: sampling by
            # enumerate() index was non-idempotent, since an unordered
            # query can return chunks in a different order across runs,
            # shifting which "none" chunks land on a sampled index.
            if int(chunk.id.hex[-4:], 16) % none_sample_rate != 0:
                continue
            code = "none"
        else:
            code = event_type

        session.add(
            LabelItem(
                version_id=chunk.version_id,
                page_number=chunk.page_number,
                chunk_id=chunk.id,
                proposed_event_type_code=code,
                proposed_confidence=None,
                proposer_name=PROPOSER_NAME,
                proposer_version=PROPOSER_VERSION,
            )
        )
        stats.proposals_created += 1
        stats.by_event_type[code] = stats.by_event_type.get(code, 0) + 1

    session.commit()
    return stats
