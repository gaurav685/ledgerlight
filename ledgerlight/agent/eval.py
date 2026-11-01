"""Phase 4 §8: evaluation. Runs real investigations across the real
SEED-track (the same 15 companies as `ledgerlight.ingestion.seed_track`)
and a real, query-derived UNIVERSE-track, then reports the real
FINALISED/NEEDS_REVIEW breakdown with reasons, claims-per-dossier,
per-check-type verification pass rate, claims removed in REPAIR,
unsupported-claim leakage into the final rendered dossier (target 0 --
any real occurrence is reported as a defect, not just a rate), and
real runtime/tool-call/token/cost p50/p95.

UNIVERSE-track selection rule (query-derived, not hand-picked -- the
same culture as `ledgerlight.modelling.coverage.compute_verified_coverage`):
of the real company universe EXCLUDING the 15 SEED-track companies
(resolved via real NSE_SYMBOL identifiers, the same way
`scripts/build_seed_governance_features.py` already does),
`UNIVERSE_TRACK_EVENT_COMPANY_COUNT` companies with the most real
governance events -- the real "has signal" case outside the curated
SEED list -- plus enough companies with ZERO real events, ordered by
the lowest real `company_id` (a fixed, reproducible tiebreak, never
randomness), to reach `UNIVERSE_TRACK_TOTAL`. The brief's own
suggested rule ("a mix of high/low score percentiles") is not
available here: real scores (the `scores` table) exist for only the
5-company verified-coverage universe, itself a subset of SEED -- a
real, disclosed limitation, stated here rather than silently
substituted for.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.agent.budgets import BudgetConfig, Usage
from ledgerlight.agent.models import Claim, Dossier
from ledgerlight.agent.state_machine import run_investigation
from ledgerlight.agent.verifier import EVIDENCE_EXEMPT_CLAIM_TYPES
from ledgerlight.ingestion.seed_track import SEED_COMPANY_SEARCH_NAMES

SEED_TRACK = "SEED"
UNIVERSE_TRACK = "UNIVERSE"

UNIVERSE_TRACK_EVENT_COMPANY_COUNT = 8
UNIVERSE_TRACK_TOTAL = 15

DEFAULT_EVAL_AS_OF_DATES: tuple[dt.date, ...] = (dt.date(2019, 1, 1), dt.date(2023, 1, 1))
"""Two fixed, documented as_of dates applied to every target company --
not derived per-company, so every real investigation in one eval run
is checked against the real same point-in-time boundary twice (an
earlier date most companies have little real data before, and a
later date most real events/filings/ratings already known by)."""


def seed_track_company_ids(session: Session) -> dict[uuid.UUID, str]:
    """Real SEED-track company_ids, resolved via real NSE_SYMBOL
    identifiers -- the same resolution
    `scripts/build_seed_governance_features.py` already uses."""
    symbols = [
        identifiers.nse_symbol
        for _name, identifiers in SEED_COMPANY_SEARCH_NAMES
        if identifiers.nse_symbol
    ]
    rows = session.execute(
        text(
            "SELECT DISTINCT company_id, value FROM company_identifiers "
            "WHERE identifier_type = 'NSE_SYMBOL' AND value = ANY(:symbols)"
        ),
        {"symbols": symbols},
    ).all()
    return {row[0]: row[1] for row in rows}


def universe_track_company_ids(
    session: Session,
    event_company_count: int = UNIVERSE_TRACK_EVENT_COMPANY_COUNT,
    total: int = UNIVERSE_TRACK_TOTAL,
) -> list[uuid.UUID]:
    """The real, query-derived UNIVERSE-track selection -- see this
    module's own docstring for the full, disclosed rule."""
    seed_ids = list(seed_track_company_ids(session))

    top_event_rows = session.execute(
        text(
            """
            SELECT c.id FROM companies c
            JOIN events e ON e.company_id = c.id
            WHERE c.id != ALL(:seed_ids)
            GROUP BY c.id
            ORDER BY count(e.id) DESC, c.id
            LIMIT :limit
            """
        ),
        {"seed_ids": seed_ids, "limit": event_company_count},
    ).all()
    event_company_ids = [row[0] for row in top_event_rows]

    remaining = max(total - len(event_company_ids), 0)
    exclude_ids = [*seed_ids, *event_company_ids]
    zero_event_rows = session.execute(
        text(
            """
            SELECT c.id FROM companies c
            WHERE c.id != ALL(:exclude_ids)
              AND NOT EXISTS (SELECT 1 FROM events e WHERE e.company_id = c.id)
            ORDER BY c.id
            LIMIT :limit
            """
        ),
        {"exclude_ids": exclude_ids, "limit": remaining},
    ).all()
    zero_event_company_ids = [row[0] for row in zero_event_rows]

    return [*event_company_ids, *zero_event_company_ids]


@dataclass
class EvalRunResult:
    company_id: uuid.UUID
    track: str
    as_of: dt.date
    investigation_id: uuid.UUID
    final_status: str
    failure_reason: str | None
    claim_count: int
    claims_removed_in_repair: int
    runtime_seconds: float
    tool_calls: int
    llm_tokens: int
    cost_usd: float
    unsupported_claim_leaked: bool


def _latest_dossier(session: Session, investigation_id: uuid.UUID) -> Dossier | None:
    return session.scalars(
        select(Dossier)
        .where(Dossier.investigation_id == investigation_id)
        .order_by(Dossier.version.desc())
        .limit(1)
    ).first()


def _referenced_claim_ids(dossier: Dossier) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    for claim_id_strs in dossier.claim_id_map.values():
        for s in cast("list[str]", claim_id_strs):
            ids.add(uuid.UUID(s))
    return ids


def _has_unsupported_claim_leak(
    claims_by_id: dict[uuid.UUID, Claim], referenced_ids: set[uuid.UUID]
) -> bool:
    """A real defect check: does the FINAL rendered dossier reference
    any claim that is itself unsupported (empty evidence, a claim
    type that is not exempt)? If the §5/§7 fixes hold, this is always
    False -- a real occurrence here means a real claim slipped past
    `verify_claim`'s exemption scoping into a FINALISED dossier."""
    for claim_id in referenced_ids:
        claim = claims_by_id.get(claim_id)
        if claim is None:
            continue
        if not claim.evidence and claim.claim_type not in EVIDENCE_EXEMPT_CLAIM_TYPES:
            return True
    return False


def run_one(
    session: Session,
    company_id: uuid.UUID,
    track: str,
    as_of: dt.date,
    requested_by: str = "agent-eval",
    budget_config: BudgetConfig | None = None,
) -> EvalRunResult:
    outcome = run_investigation(session, company_id, as_of, requested_by, budget_config)
    investigation = outcome.investigation
    usage = Usage.from_json(investigation.usage)

    all_claims = list(
        session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)).all()
    )
    claims_by_id = {c.id: c for c in all_claims}
    removed = sum(1 for c in all_claims if c.verification_status == "failed")

    dossier = _latest_dossier(session, investigation.id)
    referenced_ids = _referenced_claim_ids(dossier) if dossier is not None else set()
    leaked = _has_unsupported_claim_leak(claims_by_id, referenced_ids)

    return EvalRunResult(
        company_id=company_id,
        track=track,
        as_of=as_of,
        investigation_id=investigation.id,
        final_status=investigation.final_status or "UNKNOWN",
        failure_reason=investigation.failure_reason,
        claim_count=len(referenced_ids),
        claims_removed_in_repair=removed,
        runtime_seconds=usage.wall_seconds,
        tool_calls=usage.tool_calls,
        llm_tokens=usage.llm_tokens,
        cost_usd=usage.cost_usd,
        unsupported_claim_leaked=leaked,
    )


@dataclass
class CheckTypeStats:
    check_name: str
    total: int
    passed: int

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def compute_check_type_stats(
    session: Session, investigation_ids: list[uuid.UUID]
) -> list[CheckTypeStats]:
    """Real per-check-type pass rate, aggregated from every real
    claim's own `verification_checks` across the given investigations."""
    if not investigation_ids:
        return []
    rows = session.execute(
        text("SELECT verification_checks FROM claims WHERE investigation_id = ANY(:ids)"),
        {"ids": investigation_ids},
    ).all()
    totals: dict[str, int] = {}
    passed: dict[str, int] = {}
    for (checks,) in rows:
        for check in cast("list[dict[str, object]]", checks) or []:
            name = str(check["check_name"])
            totals[name] = totals.get(name, 0) + 1
            if check["passed"]:
                passed[name] = passed.get(name, 0) + 1
    return [
        CheckTypeStats(check_name=name, total=totals[name], passed=passed.get(name, 0))
        for name in sorted(totals)
    ]


def _percentile(values: list[float], pct: float) -> float:
    """Real linear-interpolation percentile -- 0.0 for an empty input
    (no real runs means no real percentile to report, never a crash)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


@dataclass
class EvalReport:
    results: list[EvalRunResult]
    status_breakdown: dict[str, int] = field(default_factory=dict)
    check_type_stats: list[CheckTypeStats] = field(default_factory=list)
    unsupported_claim_leaks: list[EvalRunResult] = field(default_factory=list)
    runtime_p50: float = 0.0
    runtime_p95: float = 0.0
    tool_calls_p50: float = 0.0
    tool_calls_p95: float = 0.0
    llm_tokens_p50: float = 0.0
    llm_tokens_p95: float = 0.0
    cost_usd_p50: float = 0.0
    cost_usd_p95: float = 0.0


def run_evaluation(
    session: Session,
    as_of_dates: tuple[dt.date, ...] = DEFAULT_EVAL_AS_OF_DATES,
    requested_by: str = "agent-eval",
    budget_config: BudgetConfig | None = None,
    seed_company_ids: list[uuid.UUID] | None = None,
    universe_company_ids: list[uuid.UUID] | None = None,
) -> EvalReport:
    """`seed_company_ids`/`universe_company_ids` override the real,
    full selection -- used by tests (a full 15+15 real run is too slow
    for a test suite) and, later, by a CLI wanting a smaller real
    scope. Left `None`, this runs the full real selection the brief
    asks for."""
    if seed_company_ids is not None:
        seed_ids = seed_company_ids
    else:
        seed_ids = list(seed_track_company_ids(session))
    if universe_company_ids is not None:
        universe_ids = universe_company_ids
    else:
        universe_ids = universe_track_company_ids(session)

    results: list[EvalRunResult] = []
    for company_id in seed_ids:
        for as_of in as_of_dates:
            results.append(
                run_one(session, company_id, SEED_TRACK, as_of, requested_by, budget_config)
            )
    for company_id in universe_ids:
        for as_of in as_of_dates:
            results.append(
                run_one(session, company_id, UNIVERSE_TRACK, as_of, requested_by, budget_config)
            )

    status_breakdown: dict[str, int] = {}
    for r in results:
        key = f"{r.track}:{r.final_status}"
        status_breakdown[key] = status_breakdown.get(key, 0) + 1

    check_type_stats = compute_check_type_stats(session, [r.investigation_id for r in results])
    leaks = [r for r in results if r.unsupported_claim_leaked]

    runtimes = [r.runtime_seconds for r in results]
    tool_calls = [float(r.tool_calls) for r in results]
    llm_tokens = [float(r.llm_tokens) for r in results]
    costs = [r.cost_usd for r in results]

    return EvalReport(
        results=results,
        status_breakdown=status_breakdown,
        check_type_stats=check_type_stats,
        unsupported_claim_leaks=leaks,
        runtime_p50=_percentile(runtimes, 0.5),
        runtime_p95=_percentile(runtimes, 0.95),
        tool_calls_p50=_percentile(tool_calls, 0.5),
        tool_calls_p95=_percentile(tool_calls, 0.95),
        llm_tokens_p50=_percentile(llm_tokens, 0.5),
        llm_tokens_p95=_percentile(llm_tokens, 0.95),
        cost_usd_p50=_percentile(costs, 0.5),
        cost_usd_p95=_percentile(costs, 0.95),
    )


def print_eval_report(report: EvalReport) -> None:
    print(f"Real investigations run: {len(report.results)}")
    print("Status breakdown (track:final_status -> count):")
    for key in sorted(report.status_breakdown):
        print(f"  {key}: {report.status_breakdown[key]}")

    reasons: dict[str, int] = {}
    for r in report.results:
        if r.failure_reason:
            head = r.failure_reason.split(":", 1)[0]
            reasons[head] = reasons.get(head, 0) + 1
    if reasons:
        print("NEEDS_REVIEW reasons:")
        for reason in sorted(reasons):
            print(f"  {reason}: {reasons[reason]}")

    total_claims = sum(r.claim_count for r in report.results)
    total_removed = sum(r.claims_removed_in_repair for r in report.results)
    print(f"Total claims in final dossiers: {total_claims}")
    print(f"Total claims removed in REPAIR: {total_removed}")

    print("Per-check-type pass rate:")
    for stat in report.check_type_stats:
        print(f"  {stat.check_name}: {stat.passed}/{stat.total} ({stat.pass_rate:.1%})")

    print(f"Unsupported-claim leakage into a final dossier: {len(report.unsupported_claim_leaks)}")
    for leak in report.unsupported_claim_leaks:
        print(f"  DEFECT: investigation {leak.investigation_id} (company {leak.company_id})")

    print(
        f"Runtime seconds: p50={report.runtime_p50:.2f} p95={report.runtime_p95:.2f}\n"
        f"Tool calls: p50={report.tool_calls_p50:.1f} p95={report.tool_calls_p95:.1f}\n"
        f"LLM tokens: p50={report.llm_tokens_p50:.1f} p95={report.llm_tokens_p95:.1f}\n"
        f"Cost USD: p50={report.cost_usd_p50:.4f} p95={report.cost_usd_p95:.4f}"
    )
