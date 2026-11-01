"""Tests for ledgerlight.agent.export -- Phase 4 Sec6 dossier export.
Pure unit tests against hand-built real ORM-shaped objects (no DB
write needed: export only reads already-in-memory attributes)."""

from __future__ import annotations

import datetime as dt
import json
import uuid

from ledgerlight.agent.export import export_dossier_json, export_dossier_markdown
from ledgerlight.agent.models import Dossier, Investigation


def _investigation() -> Investigation:
    return Investigation(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        as_of=dt.date(2020, 1, 1),
        requested_by="test",
        budget_config={},
        usage={},
    )


def _dossier(investigation_id: uuid.UUID, sections: dict[str, list[str]]) -> Dossier:
    return Dossier(
        investigation_id=investigation_id,
        version=1,
        status="FINALISED",
        sections=sections,
        claim_id_map={},
        renderer_name="offline_template",
        renderer_version="1",
    )


def test_export_dossier_markdown_includes_all_8_sections_in_order() -> None:
    investigation = _investigation()
    dossier = _dossier(investigation.id, {"summary": ["A real summary sentence."]})
    markdown = export_dossier_markdown(dossier, investigation, "Export Test Co")

    headings = [
        "1. Summary",
        "2. Chronology",
        "3. Findings",
        "4. Risk signals",
        "5. Conflicting evidence",
        "6. Limitations and data gaps",
        "7. Sources",
        "8. Disclaimer",
    ]
    positions = [markdown.index(h) for h in headings]
    assert positions == sorted(positions)


def test_export_dossier_markdown_marks_empty_sections_explicitly() -> None:
    investigation = _investigation()
    dossier = _dossier(investigation.id, {})
    markdown = export_dossier_markdown(dossier, investigation, "Export Test Co")
    assert markdown.count("None found.") == 8


def test_export_dossier_markdown_includes_real_sentences() -> None:
    investigation = _investigation()
    dossier = _dossier(
        investigation.id, {"findings": ["A VERIFIED AUD_RESIGN event was known as of X."]}
    )
    markdown = export_dossier_markdown(dossier, investigation, "Export Test Co")
    assert "A VERIFIED AUD_RESIGN event was known as of X." in markdown


def test_export_dossier_json_round_trips_real_content() -> None:
    investigation = _investigation()
    dossier = _dossier(investigation.id, {"summary": ["A real sentence."]})
    dossier.claim_id_map = {"summary:0": [str(uuid.uuid4())]}
    payload = json.loads(export_dossier_json(dossier, investigation))
    assert payload["status"] == "FINALISED"
    assert payload["sections"]["summary"] == ["A real sentence."]
    assert payload["investigation_id"] == str(investigation.id)
    assert len(payload["claim_id_map"]["summary:0"]) == 1
