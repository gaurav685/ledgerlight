"""Tests for ledgerlight.agent.export -- Phase 4 Sec6 dossier export.
Pure unit tests against hand-built real ORM-shaped objects (no DB
write needed: export only reads already-in-memory attributes)."""

from __future__ import annotations

import datetime as dt
import json
import re
import uuid

from ledgerlight.agent.export import SECTION_HEADINGS, export_dossier_json, export_dossier_markdown
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


# --- Phase 6 Correction 1 Sec3: the real markdown-bleed bug ------------------
#
# `get_risk_score` reads the real model card's own "## Intended use"
# Markdown section verbatim (heading, blank line, paragraph) into one
# claim payload field, rendered as one `risk_signals` sentence. A bare
# `- {sentence}` list item broke on the embedded blank line and turned
# the embedded `## Intended use` into a heading at the SAME level as
# this document's own `## 4. Risk signals` heading -- a stray sibling,
# not real nested content.

MODEL_CARD_EXCERPT = (
    "## Intended use\n\nA research prototype that scores companies for "
    "red flags. **Not investment advice.**"
)


def _heading_outline(markdown: str) -> list[tuple[int, str]]:
    """Every `#`-heading line NOT inside a blockquote (a line starting
    with `>`), with its level -- a real, if minimal, structural parse
    of this project's own self-generated Markdown (never arbitrary
    third-party Markdown), sufficient to assert the one invariant that
    matters here: no stray heading escapes its section."""
    outline: list[tuple[int, str]] = []
    for line in markdown.split("\n"):
        if line.startswith(">"):
            continue
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            outline.append((len(match.group(1)), match.group(2)))
    return outline


def test_export_dossier_markdown_has_no_stray_heading_from_multiline_content() -> None:
    """The real regression case: a `risk_signals` sentence carrying
    the model card's own raw "## Intended use" Markdown must never
    produce a level-2 heading sibling to this document's own 8 real
    section headings."""
    investigation = _investigation()
    dossier = _dossier(investigation.id, {"risk_signals": [MODEL_CARD_EXCERPT]})
    markdown = export_dossier_markdown(dossier, investigation, "Export Test Co")

    outline = _heading_outline(markdown)
    assert outline[0] == (1, "Investigation Dossier: Export Test Co")
    section_headings = outline[1:]
    assert section_headings == [(2, heading) for heading in SECTION_HEADINGS.values()], (
        "a stray heading (likely the model card's own embedded '## Intended use') "
        "escaped its section and broke the document's real heading hierarchy"
    )
    assert "> ## Intended use" in markdown


def test_export_dossier_markdown_quotes_every_line_of_multiline_content() -> None:
    """A blank line inside the quoted excerpt must stay inside the
    blockquote (as a bare `>`), never end it early -- otherwise the
    paragraph after it escapes the quote entirely."""
    investigation = _investigation()
    dossier = _dossier(investigation.id, {"risk_signals": [MODEL_CARD_EXCERPT]})
    markdown = export_dossier_markdown(dossier, investigation, "Export Test Co")

    lines = markdown.split("\n")
    heading_idx = lines.index("> ## Intended use")
    assert lines[heading_idx + 1] == ">"
    assert lines[heading_idx + 2].startswith("> A research prototype")


def test_export_dossier_markdown_structure_holds_across_every_section() -> None:
    """Parses every real section's own rendered Markdown and asserts
    the full, real 8-heading hierarchy holds regardless of which
    section carries real content -- Correction 1 Sec3.2's own
    requirement."""
    investigation = _investigation()
    for key in SECTION_HEADINGS:
        dossier = _dossier(
            investigation.id,
            {key: ["A real single-line sentence.", MODEL_CARD_EXCERPT]},
        )
        markdown = export_dossier_markdown(dossier, investigation, "Export Test Co")
        outline = _heading_outline(markdown)
        assert outline == [(1, "Investigation Dossier: Export Test Co")] + [
            (2, heading) for heading in SECTION_HEADINGS.values()
        ], f"heading hierarchy broke when section {key!r} carried multiline content"
