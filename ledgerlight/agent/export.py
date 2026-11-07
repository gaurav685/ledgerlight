"""Phase 4 §6: dossier export to Markdown and JSON.

Renders a real, already-persisted `Dossier` row -- never re-derives or
re-renders content, so an exported dossier always matches exactly
what was verified (or sent to NEEDS_REVIEW) at FINALISE time. PDF/HTML
export is Phase 5, per the brief.
"""

from __future__ import annotations

import json
from typing import cast

from ledgerlight.agent.models import Dossier, Investigation

SECTION_HEADINGS: dict[str, str] = {
    "summary": "1. Summary",
    "chronology": "2. Chronology",
    "findings": "3. Findings",
    "risk_signals": "4. Risk signals",
    "conflicting_evidence": "5. Conflicting evidence",
    "limitations": "6. Limitations and data gaps",
    "sources": "7. Sources",
    "disclaimer": "8. Disclaimer",
}
SECTION_ORDER = list(SECTION_HEADINGS)


def _render_sentence(sentence: str) -> list[str]:
    """Almost every real sentence is single-line prose and renders as
    a plain list item. The one real exception (`risk_signals`' model-
    card "Intended use" excerpt, read live and verbatim from
    docs/modelling/model-card.md -- see `get_risk_score`) carries its
    own embedded Markdown, including a `## ` heading line. Phase 6
    Correction 1 Sec3: a bare `- {sentence}` for that one broke the
    list item (a blank line inside it ends the list) and, worse,
    turned its embedded `## Intended use` into a heading at the SAME
    level as this document's own `## 4. Risk signals` section heading
    -- a stray sibling heading, not real nested content. A Markdown
    blockquote properly delimits it instead: `> ## Intended use` is a
    real heading, but nested INSIDE the quote, never breaking this
    document's own outer heading hierarchy. Every line (including
    blank ones) needs the `> ` marker -- an unmarked blank line would
    end the blockquote partway through."""
    if "\n" not in sentence:
        return [f"- {sentence}"]
    return [f"> {line}" if line else ">" for line in sentence.split("\n")]


def export_dossier_markdown(
    dossier: Dossier, investigation: Investigation, company_name: str
) -> str:
    """The real §6 8-section Markdown dossier. A section with zero
    real sentences (e.g. no real conflicting evidence was found) is
    rendered with its heading and a real, explicit
    "None found." line -- never silently omitted, so a reader can
    tell "we checked and found none" from "this was never built"."""
    lines = [
        f"# Investigation Dossier: {company_name}",
        "",
        f"As of: {investigation.as_of.isoformat()} | Status: {dossier.status} | "
        f"Version: {dossier.version}",
        f"Renderer: {dossier.renderer_name} v{dossier.renderer_version}",
        "",
    ]
    for key in SECTION_ORDER:
        heading = SECTION_HEADINGS[key]
        sentences = cast("list[str]", dossier.sections.get(key, []))
        lines.append(f"## {heading}")
        lines.append("")
        if sentences:
            for sentence in sentences:
                lines.extend(_render_sentence(sentence))
        else:
            lines.append("None found.")
        lines.append("")
    return "\n".join(lines)


def export_dossier_json(dossier: Dossier, investigation: Investigation) -> str:
    """The real dossier content plus its real metadata, as JSON --
    never a summary. `claim_id_map` is included verbatim so a
    downstream reader can trace every sentence to its real claim(s)."""
    return json.dumps(
        {
            "investigation_id": str(investigation.id),
            "company_id": str(investigation.company_id),
            "as_of": investigation.as_of.isoformat(),
            "dossier_version": dossier.version,
            "status": dossier.status,
            "renderer_name": dossier.renderer_name,
            "renderer_version": dossier.renderer_version,
            "sections": dossier.sections,
            "claim_id_map": dossier.claim_id_map,
            "created_at": dossier.created_at.isoformat() if dossier.created_at else None,
        },
        indent=2,
    )
