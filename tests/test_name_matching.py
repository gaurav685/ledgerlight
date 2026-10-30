"""Tests for ledgerlight.ingestion.name_matching -- shared by the CARE
and IBBI per-company discovery jobs. Both real cases below are taken
from live API responses (see tests/test_care_ingestion.py and
tests/test_ibbi_ingestion.py for the full per-source context)."""

from __future__ import annotations

from ledgerlight.ingestion.name_matching import best_name_match


def _name(c: dict[str, str]) -> str:
    return c["name"]


def test_best_match_prefers_exact_and_rejects_unrelated_subsidiary() -> None:
    candidates = [
        {"id": "enc-1", "name": "Vakrangee Limited"},
        {"id": "enc-2", "name": "Vakrangee Packaging LLP"},
    ]
    matched = best_name_match("Vakrangee", candidates, _name)
    assert matched is not None
    assert matched["id"] == "enc-1"


def test_best_match_returns_none_below_floor() -> None:
    candidates = [{"id": "enc-1", "name": "Completely Unrelated Industries Ltd"}]
    assert best_name_match("Gensol Engineering", candidates, _name) is None


def test_best_match_accepts_a_data_entry_variant() -> None:
    # Real IBBI data-entry typo: "Private Limited" for a public company.
    candidates = [{"id": "x", "name": "Jet Airways (India) Private Limited"}]
    matched = best_name_match("Jet Airways", candidates, _name)
    assert matched is not None


def test_best_match_rejects_unrelated_entity_sharing_a_word() -> None:
    # Real IBBI false positive: IBBI's own title search for "Jet Airways"
    # also returns this unrelated training subsidiary.
    candidates = [{"id": "x", "name": "Metro Jet Airways Training Pvt. Ltd."}]
    assert best_name_match("Jet Airways", candidates, _name) is None
