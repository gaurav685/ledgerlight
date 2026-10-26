"""Bootstraps real Entity rows from what Phase 2 has actually produced:
one company-type Entity per Company with at least one Filing, and one
audit_firm-type Entity + Mention + EntityLink per distinct audit_firm
value found in real event_fields (from the AUD_RESIGN extractor). Not a
general-purpose importer -- a real, idempotent run over this corpus's
actual output, not a stub.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.entity_resolution import link_mention, resolve_mention
from ledgerlight.knowledge.models import Company, Entity, EventField, Filing, Mention


@dataclass
class BootstrapStats:
    company_entities_created: int = 0
    company_entities_already_present: int = 0
    audit_firm_mentions_created: int = 0
    audit_firm_entities_created: int = 0
    audit_firm_links_created: int = 0


def bootstrap_company_entities(session: Session) -> BootstrapStats:
    stats = BootstrapStats()
    company_ids = {row[0] for row in session.execute(select(Filing.company_id).distinct()).all()}
    for company_id in company_ids:
        existing = session.scalar(select(Entity).where(Entity.company_id == company_id))
        if existing is not None:
            stats.company_entities_already_present += 1
            continue
        company = session.get(Company, company_id)
        if company is None:
            continue
        session.add(
            Entity(entity_type="company", company_id=company.id, display_name=company.display_name)
        )
        stats.company_entities_created += 1
    session.commit()
    return stats


def bootstrap_audit_firm_entities(session: Session) -> BootstrapStats:
    stats = BootstrapStats()
    audit_firm_fields = session.scalars(
        select(EventField).where(EventField.field_name == "audit_firm")
    ).all()

    for field in audit_firm_fields:
        firm_name = field.value_json
        if not isinstance(firm_name, str):
            continue

        existing_mention = session.scalar(
            select(Mention).where(
                Mention.version_id == field.evidence_version_id,
                Mention.page_number == field.evidence_page,
                Mention.char_start == field.evidence_char_start,
                Mention.char_end == field.evidence_char_end,
            )
        )
        if existing_mention is not None:
            continue

        mention = Mention(
            version_id=field.evidence_version_id,
            page_number=field.evidence_page,
            char_start=field.evidence_char_start,
            char_end=field.evidence_char_end,
            surface_text=firm_name,
            guessed_entity_type="audit_firm",
        )
        session.add(mention)
        session.flush()
        stats.audit_firm_mentions_created += 1

        result = resolve_mention(session, surface_text=firm_name, entity_type="audit_firm")
        if result.decision == "reject":
            new_entity = Entity(entity_type="audit_firm", display_name=firm_name)
            session.add(new_entity)
            session.flush()
            stats.audit_firm_entities_created += 1
            from ledgerlight.knowledge.entity_resolution import MatchResult

            result = MatchResult("auto_link", "manual", new_entity.id, 100.0)

        link = link_mention(session, mention, result)
        if link is not None:
            stats.audit_firm_links_created += 1

    session.commit()
    return stats
