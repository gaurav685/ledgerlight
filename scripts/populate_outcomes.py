"""Phase 3 Sec3: populate the `outcomes` table with real, evidenced rows
per data/taxonomy/outcomes-v1.0.yaml. Idempotent per (event_type, company,
event_time) where that's meaningful; re-running is safe.

Five outcome types, in two groups by evidence tier:

STRUCTURED (no document evidence -- the structured number IS the
evidence, held in Outcome.outcome_value; no EventField rows, since
EventField's evidence_version_id/page/span columns are NOT NULL and a
STRUCTURED outcome has no document to cite):
  - SEVERE_DRAWDOWN: computed from price_bars exactly as
    scripts/compute_drawdown_threshold.py validated (same ETF filter,
    same winsorization, same real threshold X).
  - BHAVCOPY_DISAPPEARANCE: a company's last EQ trade_date is more than
    thresholds.min_gap_days before this run's own "as of" date, with no
    later re-appearance.

DOCUMENT-EVIDENCED (one EventField per Event, citing the real
DocumentVersion/page/span that supports it):
  - IBBI_CIRP_ADMISSION (PRIMARY): earliest-dated real IBBI order per
    (company, case number) -- a disclosed heuristic, not a hand-verified
    classification; see the taxonomy entry's own definition for why.
  - RATING_DOWNGRADE_D (PRIMARY): a literal "CARE D" / "rated D" /
    "downgraded to D" pattern found in a CARE DocumentPage's extracted
    text, with the matching span recorded.
  - SEBI_ORDER_AGAINST_COMPANY: every auto-linked SEBI document is
    itself the evidence -- no further text classification.

known_at/event_time for document-evidenced rows come directly from the
already-computed DocumentVersion.known_at/published_at
(ledgerlight.db.temporal.compute_known_at already marked ibbi/care/sebi
as RELIABLE_PUBLISHED_AT_SOURCES at fetch time) -- not re-derived here.

Usage: python scripts/populate_outcomes.py
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import Document, DocumentPage, DocumentVersion, PriceBar  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import (  # noqa: E402
    CompanyIdentifier,
    Event,
    EventField,
    EventType,
    Outcome,
    TaxonomyVersion,
)

WINSORIZE_ABS_RETURN = 0.90
_ETF_PATTERN_SUBSTRINGS = ("ETF", "BEES", "GOLDSHARE", "LIQUID", "GOLD", "SILVER")
DRAWDOWN_THRESHOLD_PP = -48.69  # p5 of the real filtered distribution, see outcomes.md
MIN_GAP_DAYS = 90
TOLERANCE_DAYS = 10
LOOKBACK_DAYS = 365

_CASE_NUMBER_PATTERN = re.compile(
    r"(C\.?P\.?\s*\(?IB\)?[\s.-]*(?:No\.?)?\s*[\d/\-]+(?:[-/][A-Za-z0-9]+)*"
    r"|IB[\s-]*\d[\d/\-]*(?:/ND/\d+)?)",
    re.IGNORECASE,
)
_RATING_D_PATTERN = re.compile(r"\bCARE\s*D\b|\brated\s+'?D'?\b|\bdowngraded\s+to\s+'?D'?\b", re.I)


def _normalize_case_number(raw: str) -> str:
    """Real bug found 2026-10-30: the same real case (DHFL's, docket
    4258/2019) was extracted as "CP (IB) No. 4258/", "CP(IB)No. 4258/",
    "CP (IB) No. 4258/2019" and (regex miss) None across its four real
    order documents -- different whitespace/truncation per document,
    grouping into 4 spurious "admissions" instead of 1 when matched as
    exact strings. The docket NUMBER itself (the leading digit run) is
    the one part stable across all of a case's real documents; group by
    that alone, dropping the year suffix and all formatting noise."""
    digits = re.findall(r"\d{2,}", raw)
    return digits[0] if digits else raw.strip()


def _looks_like_etf(symbol: str) -> bool:
    upper = symbol.upper()
    return any(pattern in upper for pattern in _ETF_PATTERN_SUBSTRINGS)


def _get_event_type(session: Session, code: str) -> EventType:
    et = session.scalar(
        select(EventType)
        .join(TaxonomyVersion, TaxonomyVersion.id == EventType.taxonomy_version_id)
        .where(TaxonomyVersion.version == "outcomes-1.0", EventType.code == code)
    )
    if et is None:
        raise RuntimeError(f"outcomes-1.0 taxonomy not loaded (missing {code})")
    return et


def _company_id_for_symbol(session: Session, symbol: str) -> object | None:
    ident = session.scalar(
        select(CompanyIdentifier).where(
            CompanyIdentifier.identifier_type == "NSE_SYMBOL", CompanyIdentifier.value == symbol
        )
    )
    return ident.company_id if ident else None


def _company_id_for_document_identifiers(session: Session, doc: Document) -> object | None:
    for id_type, value in (
        ("NSE_SYMBOL", doc.nse_symbol),
        ("ISIN", doc.isin),
        ("BSE_CODE", doc.bse_code),
    ):
        if not value:
            continue
        ident = session.scalar(
            select(CompanyIdentifier).where(
                CompanyIdentifier.identifier_type == id_type, CompanyIdentifier.value == value
            )
        )
        if ident is not None:
            return ident.company_id
    return None


def _event_exists(
    session: Session, event_type_id: object, company_id: object, event_time: dt.datetime
) -> bool:
    return (
        session.scalar(
            select(Event.id).where(
                Event.event_type_id == event_type_id,
                Event.company_id == company_id,
                Event.event_time == event_time,
            )
        )
        is not None
    )


def populate_severe_drawdown(session: Session) -> int:
    event_type = _get_event_type(session, "SEVERE_DRAWDOWN")
    rows = session.execute(
        select(PriceBar.trade_date, PriceBar.symbol, PriceBar.close).where(
            PriceBar.series == "EQ", PriceBar.close.isnot(None)
        )
    ).all()
    by_date: dict[dt.date, dict[str, float]] = {}
    all_dates: set[dt.date] = set()
    for trade_date, symbol, close in rows:
        if close is None:
            continue
        by_date.setdefault(trade_date, {})[symbol] = float(close)
        all_dates.add(trade_date)

    by_month: dict[tuple[int, int], dt.date] = {}
    for d in all_dates:
        key = (d.year, d.month)
        if key not in by_month or d > by_month[key]:
            by_month[key] = d
    month_ends = sorted(by_month.values())

    def nearest(target: dt.date) -> dt.date | None:
        if target in by_date:
            return target
        for delta in range(1, TOLERANCE_DAYS + 1):
            for c in (target + dt.timedelta(days=delta), target - dt.timedelta(days=delta)):
                if c in by_date:
                    return c
        return None

    created = 0
    for month_end in month_ends:
        prior_date = nearest(month_end - dt.timedelta(days=LOOKBACK_DAYS))
        if prior_date is None:
            continue
        now_prices, prior_prices = by_date[month_end], by_date[prior_date]
        returns: dict[str, float] = {}
        for symbol, now_price in now_prices.items():
            prior_price = prior_prices.get(symbol)
            if prior_price is None or prior_price <= 0:
                continue
            returns[symbol] = (now_price / prior_price) - 1.0
        clean = {
            s: r
            for s, r in returns.items()
            if not _looks_like_etf(s) and abs(r) <= WINSORIZE_ABS_RETURN
        }
        if len(clean) < 20:
            continue
        sorted_r = sorted(clean.values())
        n = len(sorted_r)
        median = sorted_r[n // 2] if n % 2 == 1 else (sorted_r[n // 2 - 1] + sorted_r[n // 2]) / 2

        for symbol, r in clean.items():
            excess_pp = (r - median) * 100
            if excess_pp > DRAWDOWN_THRESHOLD_PP:
                continue
            company_id = _company_id_for_symbol(session, symbol)
            if company_id is None:
                continue
            event_time = dt.datetime.combine(month_end, dt.time(0, 0), tzinfo=dt.UTC)
            if _event_exists(session, event_type.id, company_id, event_time):
                continue
            event = Event(
                event_type_id=event_type.id,
                company_id=company_id,
                event_time=event_time,
                known_at=event_time,
                severity="high",
                status="verified",
                detector_name="compute_drawdown_threshold",
                detector_version="1",
                confidence=1.0,
            )
            session.add(event)
            session.flush()
            session.add(
                Outcome(
                    event_id=event.id,
                    outcome_type="SECONDARY_SEVERE_DRAWDOWN",
                    outcome_value={
                        "symbol": symbol,
                        "as_of": month_end.isoformat(),
                        "trailing_12m_return_pct": r * 100,
                        "market_median_return_pct": median * 100,
                        "excess_return_pp": excess_pp,
                        "spec_version": "outcomes-1.0",
                    },
                    observed_at=event_time,
                )
            )
            created += 1
    session.commit()
    return created


def populate_bhavcopy_disappearance(session: Session) -> int:
    event_type = _get_event_type(session, "BHAVCOPY_DISAPPEARANCE")
    rows = session.execute(
        select(PriceBar.symbol, PriceBar.trade_date).where(PriceBar.series == "EQ")
    ).all()
    last_seen: dict[str, dt.date] = {}
    for symbol, trade_date in rows:
        if symbol not in last_seen or trade_date > last_seen[symbol]:
            last_seen[symbol] = trade_date
    max_date = max(last_seen.values())

    created = 0
    for symbol, last_date in last_seen.items():
        gap_days = (max_date - last_date).days
        if gap_days < MIN_GAP_DAYS:
            continue
        company_id = _company_id_for_symbol(session, symbol)
        if company_id is None:
            continue
        as_of_checked = dt.datetime.combine(max_date, dt.time(0, 0), tzinfo=dt.UTC)
        event_time = dt.datetime.combine(last_date, dt.time(0, 0), tzinfo=dt.UTC)
        if _event_exists(session, event_type.id, company_id, event_time):
            continue
        event = Event(
            event_type_id=event_type.id,
            company_id=company_id,
            event_time=event_time,
            known_at=as_of_checked,
            severity="medium",
            status="verified",
            detector_name="populate_outcomes.bhavcopy_disappearance",
            detector_version="1",
            confidence=1.0,
        )
        session.add(event)
        session.flush()
        session.add(
            Outcome(
                event_id=event.id,
                outcome_type="SECONDARY_BHAVCOPY_DISAPPEARANCE",
                outcome_value={
                    "symbol": symbol,
                    "last_trade_date": last_date.isoformat(),
                    "as_of_checked": max_date.isoformat(),
                    "gap_days": gap_days,
                    "spec_version": "outcomes-1.0",
                },
                observed_at=event_time,
            )
        )
        created += 1
    session.commit()
    return created


def populate_sebi_orders(session: Session) -> int:
    event_type = _get_event_type(session, "SEBI_ORDER_AGAINST_COMPANY")
    rows = session.execute(
        select(DocumentVersion, Document)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Document.source_id == "sebi")
    ).all()
    created = 0
    for version, doc in rows:
        company_id = _company_id_for_document_identifiers(session, doc)
        if company_id is None or version.published_at is None:
            continue
        if _event_exists(session, event_type.id, company_id, version.published_at):
            continue
        event = Event(
            event_type_id=event_type.id,
            company_id=company_id,
            event_time=version.published_at,
            known_at=version.known_at,
            severity="high",
            status="verified",
            detector_name="populate_outcomes.sebi_orders",
            detector_version="1",
            confidence=1.0,
        )
        session.add(event)
        session.flush()
        session.add(
            EventField(
                event_id=event.id,
                field_name="order_document",
                value_json={"retrieval_url": doc.source_key},
                evidence_version_id=version.id,
                evidence_page=1,
                evidence_char_start=0,
                evidence_char_end=0,
                extractor_name="populate_outcomes.sebi_orders",
                extractor_version="1",
                confidence=1.0,
                validation_status="validated",
            )
        )
        session.add(
            Outcome(
                event_id=event.id,
                outcome_type="SECONDARY_SEBI_ORDER",
                outcome_value={"retrieval_url": doc.source_key, "spec_version": "outcomes-1.0"},
                observed_at=version.published_at,
            )
        )
        created += 1
    session.commit()
    return created


def populate_ibbi_admissions(session: Session) -> int:
    event_type = _get_event_type(session, "IBBI_CIRP_ADMISSION")
    rows = session.execute(
        select(DocumentVersion, Document, DocumentPage)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(DocumentPage, DocumentPage.version_id == DocumentVersion.id)
        .where(Document.source_id == "ibbi")
    ).all()

    by_case: dict[tuple[object, str], list[tuple[DocumentVersion, Document, DocumentPage]]] = {}
    for version, doc, page in rows:
        company_id = _company_id_for_document_identifiers(session, doc)
        if company_id is None:
            continue
        match = _CASE_NUMBER_PATTERN.search(page.raw_text[:2000])
        case_key = _normalize_case_number(match.group(0)) if match else doc.source_key
        by_case.setdefault((company_id, case_key), []).append((version, doc, page))

    created = 0
    for (company_id, _case_number), entries in by_case.items():
        entries_with_dates = [e for e in entries if e[0].published_at is not None]
        if not entries_with_dates:
            continue
        version, doc, page = min(
            entries_with_dates, key=lambda e: e[0].published_at or dt.datetime.max
        )
        assert version.published_at is not None
        if _event_exists(session, event_type.id, company_id, version.published_at):
            continue
        match = _CASE_NUMBER_PATTERN.search(page.raw_text[:2000])
        event = Event(
            event_type_id=event_type.id,
            company_id=company_id,
            event_time=version.published_at,
            known_at=version.known_at,
            severity="high",
            status="candidate",  # pending the brief's required human spot-check
            detector_name="populate_outcomes.ibbi_admissions",
            detector_version="1",
            confidence=0.6,  # disclosed heuristic, not a verified classification
        )
        session.add(event)
        session.flush()
        session.add(
            EventField(
                event_id=event.id,
                field_name="case_number",
                value_json=match.group(0).strip() if match else None,
                normalized_value=match.group(0).strip() if match else None,
                evidence_version_id=version.id,
                evidence_page=page.page_number,
                evidence_char_start=match.start() if match else 0,
                evidence_char_end=match.end() if match else 0,
                extractor_name="populate_outcomes.ibbi_admissions",
                extractor_version="1",
                confidence=0.6,
                validation_status="validated" if match else "unverifiable",
            )
        )
        session.add(
            Outcome(
                event_id=event.id,
                outcome_type="PRIMARY_IBBI_ADMISSION",
                outcome_value={
                    "retrieval_url": doc.source_key,
                    "case_number": match.group(0).strip() if match else None,
                    "spec_version": "outcomes-1.0",
                    "heuristic": "earliest_order_per_case_number",
                },
                observed_at=version.published_at,
            )
        )
        created += 1
    session.commit()
    return created


def populate_rating_downgrade_d(session: Session) -> int:
    event_type = _get_event_type(session, "RATING_DOWNGRADE_D")
    rows = session.execute(
        select(DocumentVersion, Document, DocumentPage)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(DocumentPage, DocumentPage.version_id == DocumentVersion.id)
        .where(Document.source_id == "care")
    ).all()

    created = 0
    for version, doc, page in rows:
        match = _RATING_D_PATTERN.search(page.raw_text)
        if match is None:
            continue
        company_id = _company_id_for_document_identifiers(session, doc)
        if company_id is None or version.published_at is None:
            continue
        if _event_exists(session, event_type.id, company_id, version.published_at):
            continue
        event = Event(
            event_type_id=event_type.id,
            company_id=company_id,
            event_time=version.published_at,
            known_at=version.known_at,
            severity="high",
            status="candidate",  # pending the brief's required human spot-check
            detector_name="populate_outcomes.rating_downgrade_d",
            detector_version="1",
            confidence=0.7,
        )
        session.add(event)
        session.flush()
        session.add(
            EventField(
                event_id=event.id,
                field_name="rating_symbol",
                value_json=match.group(0),
                normalized_value=match.group(0),
                evidence_version_id=version.id,
                evidence_page=page.page_number,
                evidence_char_start=match.start(),
                evidence_char_end=match.end(),
                extractor_name="populate_outcomes.rating_downgrade_d",
                extractor_version="1",
                confidence=0.7,
                validation_status="validated",
            )
        )
        session.add(
            Outcome(
                event_id=event.id,
                outcome_type="PRIMARY_RATING_DOWNGRADE_D",
                outcome_value={
                    "retrieval_url": doc.source_key,
                    "matched_text": match.group(0),
                    "spec_version": "outcomes-1.0",
                },
                observed_at=version.published_at,
            )
        )
        created += 1
    session.commit()
    return created


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        drawdown = populate_severe_drawdown(session)
        disappearance = populate_bhavcopy_disappearance(session)
        sebi = populate_sebi_orders(session)
        ibbi = populate_ibbi_admissions(session)
        rating_d = populate_rating_downgrade_d(session)

    print(f"SEVERE_DRAWDOWN: {drawdown}")
    print(f"BHAVCOPY_DISAPPEARANCE: {disappearance}")
    print(f"SEBI_ORDER_AGAINST_COMPANY: {sebi}")
    print(f"IBBI_CIRP_ADMISSION: {ibbi}")
    print(f"RATING_DOWNGRADE_D: {rating_d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
