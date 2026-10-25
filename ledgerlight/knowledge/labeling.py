"""Silver label proposals: a keyword/rule baseline run over real chunks,
proposing an event_type (or 'none') per chunk. Every row this writes has
label_source='ai_assisted_unreviewed' -- only the label-review CLI
(ledgerlight.knowledge.label_review) can promote a row to
'human_reviewed', which is what makes a label GOLD. This module never
sets label_source itself to anything else.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.models import Chunk, LabelItem

PROPOSER_NAME = "keyword-rule-baseline"
PROPOSER_VERSION = "1"


# Each event_type is a set of "all of these terms/phrases must appear
# somewhere in the chunk" groups (co-occurrence within a ~1000-char
# topically-coherent chunk, not strict proximity -- real disclosure text
# interposes firm names, dates, and clause boundaries between the
# subject and the verb, e.g. "...STATUTORY AUDITOR - PRICE WATERHOUSE &
# CO CHARTERED ACCOUNTANTS LLP (PWC)... has resigned", found empirically
# while tuning this against the real corpus). Order matters only for
# which event_type wins when multiple match the same chunk (first match
# wins) -- real co-occurrence (e.g. a KMP exit that's also an ID exit)
# is a known, accepted taxonomy overlap (see data/taxonomy/
# taxonomy-v1.0.yaml's co_occurrence_note), not resolved by this
# proposer.
def _contains_all(text_lower: str, *term_groups: tuple[str, ...]) -> bool:
    """term_groups: each group is a tuple of alternative phrases; at
    least one phrase from EVERY group must appear in text_lower."""
    return all(any(term in text_lower for term in group) for group in term_groups)


_EVENT_TYPE_RULES: list[tuple[str, tuple[tuple[str, ...], ...]]] = [
    (
        "AUDIT_QUAL",
        (("qualified opinion", "adverse opinion", "disclaimer of opinion", "emphasis of matter"),),
    ),
    ("FORENSIC", (("forensic audit",),)),
    ("AUD_RESIGN", (("auditor",), ("resign",))),
    (
        "RATING_ACT",
        (("downgrade", "downgraded", "rating withdrawn", "negative watch", "negative outlook"),),
    ),
    ("PLEDGE_UP", (("pledge", "pledged", "encumbrance"), ("promoter",))),
    ("ID_EXIT", (("independent director",), ("resign",))),
    (
        "KMP_EXIT",
        (
            (
                "chief financial officer",
                "chief executive officer",
                "company secretary",
                "whole-time director",
                "whole time director",
                "managing director",
            ),
            ("resign",),
        ),
    ),
    ("RESULT_DELAY", (("delay", "delayed"), ("result", "results"))),
    ("RPT_GROWTH", (("related party transaction", "related parties transaction"),)),
]


def propose_event_type(text: str) -> str | None:
    """Returns an event_type code, or None for 'none' -- the first
    matching rule wins (see module docstring)."""
    text_lower = text.lower()
    for code, term_groups in _EVENT_TYPE_RULES:
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
