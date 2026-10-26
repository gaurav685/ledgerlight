"""Entity resolution tests: normalization rules, matching-order
precedence (identifier > normalized name > fuzzy), thresholds
(auto-link/review/reject boundaries), conflict detection, and reversible
merge/unmerge."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from ledgerlight.knowledge.entity_resolution import (
    AUTO_LINK_THRESHOLD,
    REVIEW_THRESHOLD,
    detect_identifier_conflict,
    merge_entities,
    normalize_name,
    resolve_mention,
    unmerge_entities,
)
from ledgerlight.knowledge.models import Entity, EntityIdentifier

pytestmark = pytest.mark.integration


# --- normalization -------------------------------------------------------


def test_normalize_strips_legal_suffix_limited() -> None:
    assert normalize_name("Vakrangee Limited") == "vakrangee"


def test_normalize_strips_pvt_ltd() -> None:
    assert normalize_name("Acme Pvt. Ltd.") == "acme"


def test_normalize_strips_llp_and_co() -> None:
    assert normalize_name("Price Waterhouse & Co Chartered Accountants LLP") == "price waterhouse"


def test_normalize_strips_honorific() -> None:
    assert normalize_name("Mr. Anil Khanna") == "anil khanna"


def test_normalize_collapses_punctuation_and_whitespace() -> None:
    assert normalize_name("Deloitte,  Haskins & Sells") == "deloitte haskins sells"


def test_normalize_is_case_insensitive() -> None:
    assert normalize_name("INFOSYS LIMITED") == normalize_name("infosys limited")


# --- matching order / thresholds -----------------------------------------


def _make_entity(session: Session, entity_type: str, display_name: str) -> Entity:
    entity = Entity(entity_type=entity_type, display_name=display_name)
    session.add(entity)
    session.flush()
    return entity


def test_exact_identifier_match_wins_even_with_different_surface_name(db_session: Session) -> None:
    entity = _make_entity(db_session, "person", "A. Khanna")
    db_session.add(EntityIdentifier(entity_id=entity.id, identifier_type="DIN", value="01334483"))
    db_session.flush()

    result = resolve_mention(
        db_session,
        surface_text="Anil Khanna",  # different surface form, same DIN
        entity_type="person",
        identifier_type="DIN",
        identifier_value="01334483",
    )
    assert result.decision == "auto_link"
    assert result.method == "exact_identifier"
    assert result.entity_id == entity.id


def test_normalized_name_exact_match_when_no_identifier(db_session: Session) -> None:
    entity = _make_entity(
        db_session, "audit_firm", "Price Waterhouse & Co Chartered Accountants LLP"
    )
    result = resolve_mention(
        db_session,
        surface_text="Price Waterhouse & Co. Chartered Accountants LLP",
        entity_type="audit_firm",
    )
    assert result.decision == "auto_link"
    assert result.method == "normalized_name"
    assert result.entity_id == entity.id


def test_fuzzy_match_above_auto_link_threshold(db_session: Session) -> None:
    # A one-character typo survives normalization (neither side strips
    # to the same string), so this only matches at the fuzzy stage --
    # unlike "Vakrangee Ltd" vs "Vakrangee Limited", which both normalize
    # to "vakrangee" and would short-circuit at the normalized-name stage.
    entity = _make_entity(db_session, "company", "Vakrangee Softwares")
    result = resolve_mention(db_session, surface_text="Vakrange Softwares", entity_type="company")
    assert result.decision == "auto_link"
    assert result.method == "fuzzy"
    assert result.score >= AUTO_LINK_THRESHOLD
    assert result.entity_id == entity.id


def test_fuzzy_match_in_review_band(db_session: Session) -> None:
    _make_entity(db_session, "company", "Reliance Industries")
    result = resolve_mention(db_session, surface_text="Reliance Infra", entity_type="company")
    assert result.score < AUTO_LINK_THRESHOLD
    if result.score >= REVIEW_THRESHOLD:
        assert result.decision == "review"
    else:
        assert result.decision == "reject"


def test_fuzzy_match_below_review_threshold_is_rejected(db_session: Session) -> None:
    _make_entity(db_session, "company", "Totally Unrelated Corp")
    result = resolve_mention(db_session, surface_text="Zzz Qqq Xyz", entity_type="company")
    assert result.decision == "reject"
    assert result.entity_id is None


def test_no_candidates_at_all_is_rejected_not_linked(db_session: Session) -> None:
    result = resolve_mention(db_session, surface_text="Nobody At All", entity_type="person")
    assert result.decision == "reject"
    assert result.entity_id is None


def test_ambiguous_identifier_match_goes_to_review_never_auto_link(db_session: Session) -> None:
    e1 = _make_entity(db_session, "person", "Person A")
    e2 = _make_entity(db_session, "person", "Person B")
    shared_din = "99999999"
    db_session.add(EntityIdentifier(entity_id=e1.id, identifier_type="DIN", value=shared_din))
    db_session.add(EntityIdentifier(entity_id=e2.id, identifier_type="DIN", value=shared_din))
    db_session.flush()

    result = resolve_mention(
        db_session,
        surface_text="Person A",
        entity_type="person",
        identifier_type="DIN",
        identifier_value=shared_din,
    )
    assert result.decision == "review"
    assert result.entity_id is None


# --- conflict detection ----------------------------------------------------


def test_identifier_conflict_detected_for_mismatched_name(db_session: Session) -> None:
    entity = _make_entity(db_session, "person", "Anil Khanna")
    db_session.add(EntityIdentifier(entity_id=entity.id, identifier_type="DIN", value="01334483"))
    db_session.flush()

    item = detect_identifier_conflict(db_session, "DIN", "01334483", "Sunil Khanna")
    assert item is not None
    assert item.reason_code == "identifier_name_conflict"


def test_no_conflict_when_name_matches_after_normalization(db_session: Session) -> None:
    entity = _make_entity(db_session, "person", "Anil Khanna")
    db_session.add(EntityIdentifier(entity_id=entity.id, identifier_type="DIN", value="01334483"))
    db_session.flush()

    item = detect_identifier_conflict(db_session, "DIN", "01334483", "Mr. Anil Khanna")
    assert item is None


# --- merge / unmerge --------------------------------------------------------


def test_merge_then_unmerge_is_reversible(db_session: Session) -> None:
    source = _make_entity(db_session, "company", "Duplicate Co")
    target = _make_entity(db_session, "company", "Duplicate Co Ltd")

    merge = merge_entities(db_session, source.id, target.id, "duplicate registration", "analyst1")
    assert merge.reversed_at is None

    unmerged = unmerge_entities(db_session, merge.id, "analyst2")
    assert unmerged.reversed_at is not None
    assert unmerged.reversed_by == "analyst2"


def test_cannot_unmerge_twice(db_session: Session) -> None:
    source = _make_entity(db_session, "company", "A")
    target = _make_entity(db_session, "company", "B")
    merge = merge_entities(db_session, source.id, target.id, "reason", "analyst1")
    unmerge_entities(db_session, merge.id, "analyst2")

    with pytest.raises(ValueError, match="already reversed"):
        unmerge_entities(db_session, merge.id, "analyst3")


def test_unmerge_unknown_merge_id_raises(db_session: Session) -> None:
    with pytest.raises(ValueError, match="no such entity_merge"):
        unmerge_entities(db_session, uuid.uuid4(), "analyst1")
