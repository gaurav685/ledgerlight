"""Phase 4 §4 DRAFT / §6: the default, fully-offline deterministic
template renderer. Builds the dossier's prose from already-persisted,
real `Claim` rows -- never from raw tool output directly, since every
rendered sentence must map to a real claim ID (§5's own requirement),
and a claim only has a real ID once persisted.

No LLM, no network call, no randomness -- the same real claim set
renders to the exact same prose every time (the determinism exit gate,
§9), which is also why this is the *default* renderer: it is the one
path that works with LLM_PROVIDER unset.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass
from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.agent.models import Claim

RENDERER_NAME = "offline_template"
RENDERER_VERSION = "1"

MAX_EXCERPT_WORDS = 15


def event_claim_sentence(claim: Claim) -> str:
    """The real "Findings" sentence for one event claim -- factored
    out of `render_offline`'s own loop so `ledgerlight.agent.verifier`
    can check entailment against the EXACT text a reader actually
    sees, never a separately-drifting approximation of it."""
    tier = claim.payload.get("tier", "CANDIDATE")
    code = claim.payload.get("event_type_code", "an event")
    known_at = claim.payload.get("known_at", "an unknown date")
    qualifier = "unverified (CANDIDATE)" if tier == "CANDIDATE" else "VERIFIED"
    return f"A {qualifier} {code} event was known as of {known_at}."


def care_rating_claim_sentence(claim: Claim) -> str:
    """The real "Findings" sentence for one `care_rating` metric claim
    -- same reuse reason as `event_claim_sentence`."""
    return (
        f"CARE assigned the rating {claim.payload.get('value')} known as of "
        f"{claim.payload.get('known_at')}."
    )


def _content_sort_key(claim: Claim, primary_field: str) -> tuple[str, str]:
    """A fully content-based sort key -- never DB retrieval order,
    which is not real-content-deterministic (two separately persisted
    copies of the same real claim set can tie on `created_at`, since
    Postgres `now()` is constant within one transaction, and then get
    arbitrarily ordered by their own random UUIDs). The real payload
    JSON (sorted keys) is the tiebreaker, so even same-`primary_field`
    claims sort identically across runs."""
    primary = cast(str, claim.payload.get(primary_field, ""))
    return primary, json.dumps(claim.payload, sort_keys=True)


@dataclass
class ContradictionGroup:
    """Two or more real claim IDs that the §5 verifier found in real
    conflict (different dates or values for the same real-world fact).
    Populated only after VERIFY has run; `None`/empty on the first
    DRAFT pass, before any contradiction check has happened."""

    claim_ids: list[uuid.UUID]
    description: str


@dataclass
class RenderedDossier:
    sections: dict[str, list[str]]
    claim_id_map: dict[str, list[str]]


def _add_sentence(
    sections: dict[str, list[str]],
    claim_id_map: dict[str, list[str]],
    section: str,
    sentence: str,
    claim_ids: list[uuid.UUID],
) -> None:
    sections.setdefault(section, [])
    key = f"{section}:{len(sections[section])}"
    sections[section].append(sentence)
    claim_id_map[key] = [str(cid) for cid in claim_ids]


def _resolve_source_citations(
    session: Session, version_ids: set[uuid.UUID]
) -> dict[uuid.UUID, dict[str, object]]:
    """Real document title (best-effort: `company_name_raw` +
    `document_type`), source, date (`published_at`, falling back to
    `known_at`), and a real, <=15-word excerpt from the real page 1
    text -- for the Sources section (§6.7)."""
    if not version_ids:
        return {}
    rows = session.execute(
        text(
            """
            SELECT dv.id, d.source_id, d.company_name_raw, d.document_type,
                   dv.published_at, dv.known_at, dp.raw_text
            FROM document_versions dv
            JOIN documents d ON d.id = dv.document_id
            LEFT JOIN document_pages dp ON dp.version_id = dv.id AND dp.page_number = 1
            WHERE dv.id = ANY(:ids)
            """
        ),
        {"ids": list(version_ids)},
    ).all()
    citations: dict[uuid.UUID, dict[str, object]] = {}
    for row in rows:
        version_id = cast(uuid.UUID, row[0])
        source_id = cast(str, row[1])
        company_name_raw = cast("str | None", row[2])
        document_type = cast(str, row[3])
        published_at = cast("dt.datetime | None", row[4])
        known_at = cast(dt.datetime, row[5])
        raw_text = cast("str | None", row[6])
        title = f"{company_name_raw or 'Unknown company'}: {document_type}"
        excerpt = ""
        if raw_text:
            words = raw_text.split()[:MAX_EXCERPT_WORDS]
            excerpt = " ".join(words)
        citations[version_id] = {
            "title": title,
            "source": source_id,
            "date": (published_at or known_at).date().isoformat(),
            "excerpt": excerpt,
        }
    return citations


def render_offline(
    session: Session,
    claims: list[Claim],
    company_name: str,
    as_of_iso: str,
    contradictions: list[ContradictionGroup] | None = None,
) -> RenderedDossier:
    sections: dict[str, list[str]] = {}
    claim_id_map: dict[str, list[str]] = {}
    contradictions = contradictions or []

    # Sorted by real content, never by DB retrieval order: two separately
    # persisted copies of the same real claim set (e.g. a first pass and a
    # resumed run) can tie on `created_at` (same-transaction `now()`) and
    # get arbitrarily ordered by their random UUIDs otherwise -- a real
    # determinism bug this sort fixes at the source, not downstream.
    event_claims = sorted(
        (c for c in claims if c.claim_type == "event"),
        key=lambda c: _content_sort_key(c, "known_at"),
    )
    timeline_claims = sorted(
        (c for c in claims if c.claim_type == "timeline_entry"),
        key=lambda c: _content_sort_key(c, "known_at"),
    )
    metric_claims = sorted(
        (c for c in claims if c.claim_type == "metric"),
        key=lambda c: _content_sort_key(c, "known_at"),
    )
    risk_claims = [c for c in claims if c.claim_type == "risk_signal"]
    limitation_claims = sorted(
        (c for c in claims if c.claim_type == "limitation"),
        key=lambda c: _content_sort_key(c, "text"),
    )

    # 1. Summary
    verified_count = sum(1 for c in event_claims if c.payload.get("tier") == "VERIFIED")
    candidate_count = sum(1 for c in event_claims if c.payload.get("tier") == "CANDIDATE")
    _add_sentence(
        sections,
        claim_id_map,
        "summary",
        f"This dossier covers {company_name} as of {as_of_iso}, based on "
        f"{len(event_claims)} real governance/outcome events "
        f"({verified_count} VERIFIED, {candidate_count} CANDIDATE) and "
        f"{len(timeline_claims)} real filings known as of that date.",
        [c.id for c in event_claims] or [c.id for c in risk_claims],
    )

    # 2. Chronology
    for claim in timeline_claims:
        label = claim.payload.get("label", "a filing")
        known_at = claim.payload.get("known_at", "an unknown date")
        _add_sentence(
            sections,
            claim_id_map,
            "chronology",
            f"A real {label} filing was known as of {known_at}.",
            [claim.id],
        )

    # 3. Findings
    for claim in event_claims:
        _add_sentence(sections, claim_id_map, "findings", event_claim_sentence(claim), [claim.id])
    for claim in metric_claims:
        if claim.payload.get("name") != "care_rating":
            continue
        _add_sentence(
            sections, claim_id_map, "findings", care_rating_claim_sentence(claim), [claim.id]
        )

    # 4. Risk signals
    for claim in risk_claims:
        if claim.payload.get("found"):
            _add_sentence(
                sections,
                claim_id_map,
                "risk_signals",
                f"The model's estimated risk percentile was "
                f"{claim.payload.get('percentile')} "
                f"(calibrated probability {claim.payload.get('calibrated_probability')}).",
                [claim.id],
            )
        else:
            _add_sentence(
                sections,
                claim_id_map,
                "risk_signals",
                "No real model score was available for this company as of this date.",
                [claim.id],
            )
        limitations_text = claim.payload.get("model_limitations")
        if limitations_text:
            _add_sentence(
                sections,
                claim_id_map,
                "risk_signals",
                str(limitations_text),
                [claim.id],
            )

    # 5. Conflicting evidence
    for group in contradictions:
        _add_sentence(
            sections,
            claim_id_map,
            "conflicting_evidence",
            group.description,
            group.claim_ids,
        )

    # 6. Limitations and data gaps (the disclaimer claim is rendered
    # separately, in its own §6.8 section, not here).
    for claim in limitation_claims:
        if claim.payload.get("is_disclaimer"):
            continue
        _add_sentence(
            sections,
            claim_id_map,
            "limitations",
            str(claim.payload.get("text")),
            [claim.id],
        )

    # 7. Sources
    version_ids: set[uuid.UUID] = set()
    for claim in claims:
        for ev in claim.evidence:
            version_ids.add(uuid.UUID(str(cast("dict[str, object]", ev)["document_version_id"])))
    citations = _resolve_source_citations(session, version_ids)
    evidence_claims_by_version: dict[uuid.UUID, list[uuid.UUID]] = {}
    for claim in claims:
        for ev in claim.evidence:
            vid = uuid.UUID(str(cast("dict[str, object]", ev)["document_version_id"]))
            evidence_claims_by_version.setdefault(vid, []).append(claim.id)
    for version_id, citation in citations.items():
        _add_sentence(
            sections,
            claim_id_map,
            "sources",
            f"{citation['title']} ({citation['source']}, {citation['date']}): "
            f"\"{citation['excerpt']}\"",
            evidence_claims_by_version.get(version_id, []),
        )

    # 8. Disclaimer -- a real limitation claim
    # (`claims.standing_limitation_claims`'s own disclaimer entry,
    # `payload["is_disclaimer"] = True`), not claim-less boilerplate: every
    # real sentence maps to a real claim ID, with no exemption.
    for claim in limitation_claims:
        if not claim.payload.get("is_disclaimer"):
            continue
        _add_sentence(
            sections, claim_id_map, "disclaimer", str(claim.payload.get("text")), [claim.id]
        )

    return RenderedDossier(sections=sections, claim_id_map=claim_id_map)
