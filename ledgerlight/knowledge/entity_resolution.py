"""Entity resolution: deterministic identifiers first, then normalization
rules, then similarity scoring with blocking -- in that order, never
skipping a stage. Thresholds are tuned on validation pairs (see
docs/knowledge/entity-resolution.md); nothing below the auto-link
threshold is ever auto-merged. Conflicting identifiers create
review_queue items. Merges are reversible via EntityMerge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.models import (
    Entity,
    EntityIdentifier,
    EntityLink,
    EntityMerge,
    Mention,
    ReviewQueueItem,
)

MatchMethod = Literal["exact_identifier", "normalized_name", "fuzzy", "manual"]
MatchDecision = Literal["auto_link", "review", "reject"]

# Tuned on validation pairs (see docs/knowledge/entity-resolution.md for
# the pairs and the tuning rationale) -- never auto-link below AUTO_LINK.
AUTO_LINK_THRESHOLD = 92.0
REVIEW_THRESHOLD = 75.0
# below REVIEW_THRESHOLD -> reject (no link, no review item)

_LEGAL_SUFFIXES = [
    r"\bprivate limited\b",
    r"\bpvt\.?\s*ltd\.?\b",
    r"\blimited\b",
    r"\bltd\.?\b",
    r"\bllp\b",
    r"&\s*co\.?\b",  # no leading \b: "&" is non-word, so \b can't anchor there
    r"\band co\.?\b",
    r"\bchartered accountants\b",
    r"\bcharteredaccountants\b",
]
_HONORIFICS = [r"\bmr\.?\b", r"\bmrs\.?\b", r"\bms\.?\b", r"\bdr\.?\b"]


def normalize_name(name: str) -> str:
    """Strips legal suffixes (Ltd/Limited/Pvt/LLP/& Co/Chartered
    Accountants), honorifics (Mr/Mrs/Ms/Dr), punctuation, and collapses
    whitespace -- case-insensitive throughout. Used for both company and
    person/firm names; applying firm-suffix stripping to a person's name
    is harmless since those patterns won't match."""
    normalized = name.lower().strip()
    for pattern in _HONORIFICS + _LEGAL_SUFFIXES:
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


@dataclass
class MatchResult:
    decision: MatchDecision
    method: MatchMethod | None
    entity_id: UUID | None
    score: float


def _try_exact_identifier(session: Session, identifier_type: str, value: str) -> list[Entity]:
    rows = session.scalars(
        select(EntityIdentifier).where(
            EntityIdentifier.identifier_type == identifier_type, EntityIdentifier.value == value
        )
    ).all()
    entity_ids = {r.entity_id for r in rows}
    if not entity_ids:
        return []
    return list(session.scalars(select(Entity).where(Entity.id.in_(entity_ids))).all())


def _try_normalized_name(session: Session, entity_type: str, name: str) -> list[Entity]:
    target = normalize_name(name)
    candidates = session.scalars(select(Entity).where(Entity.entity_type == entity_type)).all()
    return [e for e in candidates if normalize_name(e.display_name) == target]


def _fuzzy_score(name: str, candidate_name: str) -> float:
    from rapidfuzz import fuzz

    return float(fuzz.token_sort_ratio(normalize_name(name), normalize_name(candidate_name)))


def resolve_mention(
    session: Session,
    *,
    surface_text: str,
    entity_type: str,
    identifier_type: str | None = None,
    identifier_value: str | None = None,
    blocking_candidates: list[Entity] | None = None,
) -> MatchResult:
    """Matching order: (1) deterministic identifier, (2) normalized-name
    exact match, (3) fuzzy similarity with blocking. Stops at the first
    stage that produces an unambiguous match."""
    if identifier_type and identifier_value:
        matches = _try_exact_identifier(session, identifier_type, identifier_value)
        if len(matches) == 1:
            return MatchResult("auto_link", "exact_identifier", matches[0].id, 100.0)
        if len(matches) > 1:
            return MatchResult("review", "exact_identifier", None, 100.0)

    name_matches = _try_normalized_name(session, entity_type, surface_text)
    if len(name_matches) == 1:
        return MatchResult("auto_link", "normalized_name", name_matches[0].id, 100.0)
    if len(name_matches) > 1:
        return MatchResult("review", "normalized_name", None, 100.0)

    candidates = blocking_candidates
    if candidates is None:
        candidates = list(
            session.scalars(select(Entity).where(Entity.entity_type == entity_type)).all()
        )
    best_entity: Entity | None = None
    best_score = 0.0
    for candidate in candidates:
        score = _fuzzy_score(surface_text, candidate.display_name)
        if score > best_score:
            best_score = score
            best_entity = candidate

    if best_entity is None:
        return MatchResult("reject", None, None, 0.0)
    if best_score >= AUTO_LINK_THRESHOLD:
        return MatchResult("auto_link", "fuzzy", best_entity.id, best_score)
    if best_score >= REVIEW_THRESHOLD:
        return MatchResult("review", "fuzzy", best_entity.id, best_score)
    return MatchResult("reject", "fuzzy", None, best_score)


def link_mention(session: Session, mention: Mention, result: MatchResult) -> EntityLink | None:
    if result.decision == "reject" or result.entity_id is None:
        return None

    link = EntityLink(
        mention_id=mention.id,
        entity_id=result.entity_id,
        method=result.method or "manual",
        score=result.score,
        status="active",
    )
    session.add(link)
    session.flush()

    if result.decision == "review":
        session.add(
            ReviewQueueItem(
                item_type="entity_link",
                reference_id=link.id,
                reason_code=f"below_auto_link_threshold_{result.method}",
                priority=3,
                status="open",
            )
        )
    session.commit()
    return link


def detect_identifier_conflict(
    session: Session, identifier_type: str, value: str, claimed_display_name: str
) -> ReviewQueueItem | None:
    """A conflict: the SAME identifier value is already associated with
    an entity whose display name doesn't match (normalized) the newly
    claimed name -- e.g. the same DIN appearing with two different
    spellings/names across filings. Never auto-merges; always queued."""
    existing = session.scalars(
        select(EntityIdentifier).where(
            EntityIdentifier.identifier_type == identifier_type, EntityIdentifier.value == value
        )
    ).all()
    for identifier in existing:
        entity = session.get(Entity, identifier.entity_id)
        if entity is None:
            continue
        if normalize_name(entity.display_name) != normalize_name(claimed_display_name):
            item = ReviewQueueItem(
                item_type="other",
                reference_id=identifier.id,
                reason_code="identifier_name_conflict",
                priority=1,
                status="open",
                resolution=None,
            )
            session.add(item)
            session.commit()
            return item
    return None


def merge_entities(
    session: Session, source_entity_id: UUID, target_entity_id: UUID, reason: str, actor: str
) -> EntityMerge:
    merge = EntityMerge(
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        reason=reason,
        actor=actor,
    )
    session.add(merge)
    session.commit()
    return merge


def unmerge_entities(session: Session, merge_id: UUID, actor: str) -> EntityMerge:
    merge = session.get(EntityMerge, merge_id)
    if merge is None:
        raise ValueError(f"no such entity_merge: {merge_id}")
    if merge.reversed_at is not None:
        raise ValueError(f"entity_merge {merge_id} was already reversed")
    import datetime as dt

    merge.reversed_at = dt.datetime.now(dt.UTC)
    merge.reversed_by = actor
    session.commit()
    return merge
