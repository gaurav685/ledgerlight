"""Phase 4 §7: seeded QC. Injects a configurable share of deliberately
flawed dossiers into the real review queue, flagged `seeded_qc=True`
with a real `expected_outcome`, so a human reviewer's real catch rate
per flaw type can be measured. Seeded items are excluded from every
other real statistic (§7's own explicit rule) -- never counted in
§8's agent-eval tallies.

Design: `seed_flawed_dossier` first runs ONE real investigation to
completion via `run_investigation` (a fresh `Investigation` row, never
reusing an existing one), so the seeded dossier sits among real,
honestly-produced content rather than a fabricated shell. It then
injects exactly one deliberately flawed `Claim` on top of that real,
passed-verification claim set and re-renders through the real offline
template renderer -- the flaw must read as plausible prose to a human
reviewer, so it goes through the same renderer every real claim does,
never a hand-written sentence bypassing it. This produces a NEW
dossier version (never touching dossier version 1, the real,
unflawed render) and opens a real `ReviewTask` against it. The
underlying `Investigation.final_status` is set once, by the real run,
before the flaw is ever injected, and is never touched again here --
so §8's investigation-level statistics (FINALISED/NEEDS_REVIEW
breakdown, claims-per-dossier, etc.) stay real and uncorrupted as long
as they are computed from `Investigation.final_status` and from
dossier versions that are NOT referenced by a `seeded_qc=True`
`ReviewTask` -- the one, sufficient exclusion rule this module
establishes and documents here rather than leaving implicit.

Four flaw types, per the brief: a missing citation (evidence points
at a document span that does not exist), an unsupported claim
(evidence is empty for a claim type that is not exempt), a wrong date
(the claim's own `known_at` does not match any date in its real,
resolving evidence span), and a wrong number (a `metric` claim's
value does not match its real, resolving evidence span). Every seeded
flaw is a genuine defect -- the correct reviewer decision is always
"reject"; `expected_outcome` records that real fact per task, rather
than a flaw-type lookup table a reviewer could not see.
"""

from __future__ import annotations

import datetime as dt
import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.agent.budgets import BudgetConfig
from ledgerlight.agent.models import Claim, Dossier, ReviewTask
from ledgerlight.agent.render import RENDERER_NAME, RENDERER_VERSION, render_offline
from ledgerlight.agent.review import SEEDED_QC
from ledgerlight.agent.state_machine import run_investigation
from ledgerlight.knowledge.models import Company

FLAW_WRONG_DATE = "wrong_date"
FLAW_WRONG_NUMBER = "wrong_number"
FLAW_MISSING_CITATION = "missing_citation"
FLAW_UNSUPPORTED_CLAIM = "unsupported_claim"
ALL_FLAW_TYPES: tuple[str, ...] = (
    FLAW_WRONG_DATE,
    FLAW_WRONG_NUMBER,
    FLAW_MISSING_CITATION,
    FLAW_UNSUPPORTED_CLAIM,
)

SEEDED_QC_EXPECTED_OUTCOME = "reject"
_WRONG_KNOWN_AT = "1901-01-01T00:00:00+00:00"
_WRONG_RATING_VALUE = "ZZZ_SEEDED_QC_NOT_A_REAL_RATING"


@dataclass
class SeededQCItem:
    investigation_id: uuid.UUID
    dossier_id: uuid.UUID
    review_task_id: uuid.UUID
    flaw_type: str
    flawed_claim_id: uuid.UUID
    company_id: uuid.UUID
    as_of: dt.date


def _real_claims_for_investigation(session: Session, investigation_id: uuid.UUID) -> list[Claim]:
    return list(
        session.scalars(
            select(Claim)
            .where(Claim.investigation_id == investigation_id)
            .where(Claim.verification_status != "failed")
            .order_by(Claim.created_at)
        ).all()
    )


def _build_flawed_claim(investigation_id: uuid.UUID, flaw_type: str, donor: Claim | None) -> Claim:
    """One real, deliberately flawed `Claim` of `flaw_type`.
    `wrong_date`/`wrong_number` need a real `donor` claim with a real,
    resolving evidence span to corrupt against -- without one, there
    is no real span text to be wrong relative to, so this raises
    rather than fabricating a span that would not actually resolve."""
    now_iso = dt.datetime.now(dt.UTC).isoformat()

    if flaw_type == FLAW_UNSUPPORTED_CLAIM:
        return Claim(
            investigation_id=investigation_id,
            claim_type="event",
            payload={
                "event_type_code": "AUD_RESIGN",
                "event_time": now_iso,
                "known_at": now_iso,
                "severity": "high",
                "tier": "CANDIDATE",
                "qc_flaw_type": flaw_type,
            },
            evidence=[],
        )
    if flaw_type == FLAW_MISSING_CITATION:
        return Claim(
            investigation_id=investigation_id,
            claim_type="event",
            payload={
                "event_type_code": "AUD_RESIGN",
                "event_time": now_iso,
                "known_at": now_iso,
                "severity": "high",
                "tier": "CANDIDATE",
                "qc_flaw_type": flaw_type,
            },
            evidence=[
                {
                    "document_version_id": str(uuid.uuid4()),
                    "page_number": 1,
                    "char_start": 0,
                    "char_end": 10,
                }
            ],
        )

    if donor is None or not donor.evidence:
        raise ValueError(
            f"flaw_type={flaw_type!r} needs a real donor claim with a resolving evidence "
            "span to corrupt against; this investigation has no such claim"
        )
    span = dict(cast("dict[str, object]", donor.evidence[0]))

    if flaw_type == FLAW_WRONG_DATE:
        return Claim(
            investigation_id=investigation_id,
            claim_type="event",
            payload={
                "event_type_code": donor.payload.get("event_type_code", "AUD_RESIGN"),
                "event_time": _WRONG_KNOWN_AT,
                "known_at": _WRONG_KNOWN_AT,
                "severity": "high",
                "tier": "CANDIDATE",
                "qc_flaw_type": flaw_type,
            },
            evidence=[span],
        )
    if flaw_type == FLAW_WRONG_NUMBER:
        return Claim(
            investigation_id=investigation_id,
            claim_type="metric",
            payload={
                "name": "care_rating",
                "value": _WRONG_RATING_VALUE,
                "unit": "CARE_rating_symbol",
                "known_at": now_iso,
                "qc_flaw_type": flaw_type,
            },
            evidence=[span],
        )
    raise ValueError(f"unknown flaw_type: {flaw_type!r}")


def seed_flawed_dossier(
    session: Session,
    company_id: uuid.UUID,
    as_of: dt.date,
    flaw_type: str,
    requested_by: str = "qc-seed",
    budget_config: BudgetConfig | None = None,
) -> SeededQCItem:
    """Runs one real investigation for `(company_id, as_of)` to
    completion, injects one deliberately flawed claim of `flaw_type`
    on top of its real claim set, re-renders, persists a new dossier
    version, and opens a `seeded_qc=True` review task against it."""
    if flaw_type not in ALL_FLAW_TYPES:
        raise ValueError(f"unknown flaw_type: {flaw_type!r}; must be one of {ALL_FLAW_TYPES}")

    outcome = run_investigation(session, company_id, as_of, requested_by, budget_config)
    investigation = outcome.investigation

    real_claims = _real_claims_for_investigation(session, investigation.id)
    donor = next(
        (c for c in real_claims if c.claim_type in ("event", "metric") and c.evidence), None
    )
    flawed_claim = _build_flawed_claim(investigation.id, flaw_type, donor)
    session.add(flawed_claim)
    session.flush()

    company = session.get(Company, company_id)
    company_name = company.display_name if company is not None else str(company_id)
    all_claims = [*real_claims, flawed_claim]
    rendered = render_offline(session, all_claims, company_name, as_of.isoformat(), company_id)

    existing_versions = session.scalars(
        select(Dossier.version).where(Dossier.investigation_id == investigation.id)
    ).all()
    version = (max(existing_versions) + 1) if existing_versions else 1
    dossier = Dossier(
        investigation_id=investigation.id,
        version=version,
        status="NEEDS_REVIEW",
        sections=rendered.sections,
        claim_id_map=rendered.claim_id_map,
        renderer_name=RENDERER_NAME,
        renderer_version=RENDERER_VERSION,
    )
    session.add(dossier)
    session.flush()

    task = ReviewTask(
        dossier_id=dossier.id,
        reason_code=SEEDED_QC,
        priority=0,
        status="open",
        seeded_qc=True,
        expected_outcome=SEEDED_QC_EXPECTED_OUTCOME,
    )
    session.add(task)
    session.commit()

    return SeededQCItem(
        investigation_id=investigation.id,
        dossier_id=dossier.id,
        review_task_id=task.id,
        flaw_type=flaw_type,
        flawed_claim_id=flawed_claim.id,
        company_id=company_id,
        as_of=as_of,
    )


def seed_qc_batch(
    session: Session,
    targets: list[tuple[uuid.UUID, dt.date]],
    seed_fraction: float,
    requested_by: str = "qc-seed",
    budget_config: BudgetConfig | None = None,
    rng_seed: int = 0,
    on_skip: Callable[[uuid.UUID, dt.date, str, str], None] | None = None,
) -> list[SeededQCItem]:
    """Deterministically (fixed `rng_seed`) picks `seed_fraction` of
    `targets` -- at least one if `targets` is non-empty and
    `seed_fraction` > 0 -- and seeds one flawed dossier for each,
    cycling through all four flaw types in a fixed order so a real
    batch gets real coverage of every type, not whichever the random
    choice happens to favour.

    A real target that has no real donor claim for its assigned flaw
    type (`wrong_date`/`wrong_number` need one; `missing_citation`/
    `unsupported_claim` never do) is skipped, never retried with a
    different flaw type -- the deterministic cycling order is itself
    this function's real, documented per-type coverage guarantee, not
    something to work around per company. The real investigation
    `seed_flawed_dossier` already ran before hitting that limit is
    kept regardless; only its flawed v2 dossier is not created.
    `on_skip`, if given, is called with (company_id, as_of, flaw_type,
    reason) for every real skip, so a caller (a CLI, say) can report
    it -- this function itself does no I/O."""
    if not 0.0 <= seed_fraction <= 1.0:
        raise ValueError(f"seed_fraction must be in [0, 1], got {seed_fraction}")
    if not targets:
        return []

    count = round(len(targets) * seed_fraction)
    if seed_fraction > 0.0:
        count = max(count, 1)
    count = min(count, len(targets))

    rng = random.Random(rng_seed)
    chosen = rng.sample(targets, k=count)

    items: list[SeededQCItem] = []
    for i, (company_id, as_of) in enumerate(chosen):
        flaw_type = ALL_FLAW_TYPES[i % len(ALL_FLAW_TYPES)]
        try:
            items.append(
                seed_flawed_dossier(
                    session, company_id, as_of, flaw_type, requested_by, budget_config
                )
            )
        except ValueError as exc:
            if on_skip is not None:
                on_skip(company_id, as_of, flaw_type, str(exc))
    return items


@dataclass
class CatchRateRow:
    flaw_type: str
    seeded_count: int
    reviewed_count: int
    caught_count: int

    @property
    def catch_rate(self) -> float | None:
        if self.reviewed_count == 0:
            return None
        return self.caught_count / self.reviewed_count


def compute_catch_rate_report(session: Session) -> list[CatchRateRow]:
    """Real reviewer catch rate per flaw type, from real `ReviewTask`
    rows with `seeded_qc=True` that already have a recorded
    `decision` -- an open, undecided seeded task is not yet testable
    and is excluded from the rate, never counted as a miss.
    `flaw_type` is recovered from the one flawed claim's
    `payload['qc_flaw_type']` on that task's investigation (the
    brief's own §2 schema has no dedicated column for it on
    `ReviewTask`); "caught" means the real recorded decision equals
    the task's own real `expected_outcome`, never a hardcoded guess at
    what counts as catching a flaw."""
    rows = session.execute(
        text(
            """
            SELECT c.payload->>'qc_flaw_type' AS flaw_type, rt.decision, rt.expected_outcome
            FROM review_tasks rt
            JOIN dossiers d ON d.id = rt.dossier_id
            JOIN claims c ON c.investigation_id = d.investigation_id
            WHERE rt.seeded_qc = true
              AND c.payload->>'qc_flaw_type' IS NOT NULL
            """
        )
    ).all()

    by_flaw: dict[str, list[tuple[str | None, str | None]]] = {}
    for flaw_type, decision, expected_outcome in rows:
        by_flaw.setdefault(str(flaw_type), []).append(
            (cast("str | None", decision), cast("str | None", expected_outcome))
        )

    report: list[CatchRateRow] = []
    for flaw_type in ALL_FLAW_TYPES:
        pairs = by_flaw.get(flaw_type, [])
        reviewed = [(d, e) for d, e in pairs if d is not None]
        caught = sum(1 for d, e in reviewed if d == e)
        report.append(
            CatchRateRow(
                flaw_type=flaw_type,
                seeded_count=len(pairs),
                reviewed_count=len(reviewed),
                caught_count=caught,
            )
        )
    return report


def print_catch_rate_report(report: list[CatchRateRow]) -> None:
    print("Seeded QC reviewer catch rate (seeded items excluded from every other real statistic):")
    for row in report:
        rate = "n/a (no decisions yet)" if row.catch_rate is None else f"{row.catch_rate:.1%}"
        print(
            f"  {row.flaw_type:<20} seeded={row.seeded_count:<3} "
            f"reviewed={row.reviewed_count:<3} caught={row.caught_count:<3} rate={rate}"
        )
