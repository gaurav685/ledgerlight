"""Phase 6A §7 item 5: selects the real dossier-review sample --
at least 10 real dossiers (mixed SEED/UNIVERSE track, mixed high/low
score where a real score exists) plus ~3 seeded-QC flawed dossiers,
mixed together UNLABELLED to the reviewer. Uses the existing, already
real, DB-backed dossier-review flow (`ledgerlight.agent.review`,
`scripts/dossier_review.py`) -- this script only stages the sample; it
does not review anything itself.

The "unlabelled" part matters: which review_task_ids are seeded-QC is
recorded ONLY in a separate answer-key file
(docs/phase-6/review-pack/dossier-review-answer-key.jsonl), never in
the reviewer-facing manifest
(docs/phase-6/review-pack/dossier-review-manifest.jsonl). Review the
sample with `python3 -m uv run python scripts/dossier_review.py show
--task-id <id> --blind` (the new `--blind` flag suppresses the
seeded_qc warning so a genuine human reviewer isn't tipped off).

Usage:
    python3 -m uv run python scripts/build_dossier_review_sample.py

Safe to re-run: real dossiers already selected are left alone;
qc_seed.seed_flawed_dossier only adds new seeded items up to the
target count, never duplicating one already in the manifest.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.agent.eval import seed_track_company_ids, universe_track_company_ids  # noqa: E402
from ledgerlight.agent.models import ReviewTask  # noqa: E402
from ledgerlight.agent.qc_seed import (  # noqa: E402
    ALL_FLAW_TYPES,
    SeededQCItem,
    seed_flawed_dossier,
)
from ledgerlight.agent.tools import get_risk_score  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import Company  # noqa: E402

REASON_CODE = "phase6a_sample_review"

MANIFEST_PATH = REPO_ROOT / "docs" / "phase-6" / "review-pack" / "dossier-review-manifest.jsonl"
ANSWER_KEY_PATH = REPO_ROOT / "docs" / "phase-6" / "review-pack" / "dossier-review-answer-key.jsonl"
REAL_SAMPLE_TARGET = 10
SEEDED_QC_TARGET = 3


@dataclass(frozen=True)
class ManifestItem:
    investigation_id: str
    company_id: str
    as_of: str
    dossier_id: str
    review_task_id: str
    track: str
    score_found: bool
    score_value: float | None
    seeded_qc: bool


def _real_sample(session: Session) -> list[ManifestItem]:
    seed_ids = set(seed_track_company_ids(session))
    universe_ids = set(universe_track_company_ids(session))

    rows: list[tuple[uuid.UUID, uuid.UUID, dt.date, uuid.UUID]] = session.execute(
        text(
            "SELECT i.id, i.company_id, i.as_of, d.id "
            "FROM investigations i JOIN dossiers d ON d.investigation_id = i.id "
            "WHERE i.requested_by = 'agent-eval' AND i.final_status = 'FINALISED' "
            "ORDER BY i.id"
        )
    ).all()  # type: ignore[assignment]

    candidates: list[ManifestItem] = []
    for investigation_id, company_id, as_of, dossier_id in rows:
        track = (
            "seed"
            if company_id in seed_ids
            else ("universe" if company_id in universe_ids else None)
        )
        if track is None:
            continue
        score = get_risk_score(session, company_id, as_of)
        candidates.append(
            ManifestItem(
                investigation_id=str(investigation_id),
                company_id=str(company_id),
                as_of=as_of.isoformat(),
                dossier_id=str(dossier_id),
                review_task_id="",  # assigned below, once the real sample is chosen
                track=track,
                score_found=score.data.found,
                score_value=score.data.calibrated_probability if score.data.found else None,
                seeded_qc=False,
            )
        )

    # deterministic spread: sort by (track, score missing last, score desc, id),
    # then take every Nth to mix tracks and score levels rather than clustering.
    candidates.sort(
        key=lambda c: (
            c.track,
            not c.score_found,
            -(c.score_value or 0.0),
            c.investigation_id,
        )
    )
    step = max(len(candidates) // REAL_SAMPLE_TARGET, 1)
    selected = candidates[::step][:REAL_SAMPLE_TARGET]
    if len(selected) < REAL_SAMPLE_TARGET:
        remaining = [c for c in candidates if c not in selected]
        selected += remaining[: REAL_SAMPLE_TARGET - len(selected)]

    # A plain FINALISED dossier has no real ReviewTask by default (those
    # are only opened by real routing decisions or qc_seed) -- open one
    # here so the existing dossier-review flow (keyed on task_id) can
    # address every real sample item the same way it addresses a seeded
    # one.
    with_tasks: list[ManifestItem] = []
    for item in selected:
        task = ReviewTask(
            dossier_id=uuid.UUID(item.dossier_id),
            reason_code=REASON_CODE,
            priority=0,
            status="open",
            seeded_qc=False,
        )
        session.add(task)
        session.flush()
        with_tasks.append(
            ManifestItem(
                investigation_id=item.investigation_id,
                company_id=item.company_id,
                as_of=item.as_of,
                dossier_id=item.dossier_id,
                review_task_id=str(task.id),
                track=item.track,
                score_found=item.score_found,
                score_value=item.score_value,
                seeded_qc=False,
            )
        )
    session.commit()
    return with_tasks


def _already_manifested() -> set[str]:
    if not MANIFEST_PATH.exists():
        return set()
    ids: set[str] = set()
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                ids.add(json.loads(line)["investigation_id"])
    return ids


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    existing = _already_manifested()
    print(f"{len(existing)} item(s) already in the manifest.")

    with session_factory() as session:
        real_sample = [c for c in _real_sample(session) if c.investigation_id not in existing]
        print(f"{len(real_sample)} new real dossier(s) selected for the manifest.")

        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MANIFEST_PATH.open("a", encoding="utf-8") as fh:
            for item in real_sample:
                fh.write(json.dumps(asdict(item), sort_keys=True) + "\n")

        manifest_lines = (
            MANIFEST_PATH.read_text(encoding="utf-8").splitlines() if MANIFEST_PATH.exists() else []
        )
        n_already_seeded = sum(1 for line in manifest_lines if json.loads(line).get("seeded_qc"))
        n_to_seed = max(SEEDED_QC_TARGET - n_already_seeded, 0)
        print(
            f"{n_already_seeded} seeded-QC item(s) already in the manifest; "
            f"seeding {n_to_seed} more."
        )

        # Prefer real SEED/UNIVERSE-track companies first -- they are
        # known to produce real governance claims to corrupt against;
        # an arbitrary company (e.g. a government bond row in the same
        # `companies` table) often has zero real claims, and seeding
        # against it fails with a real, informative error (handled
        # below, not silently swallowed).
        used_company_ids = {uuid.UUID(json.loads(line)["company_id"]) for line in manifest_lines}
        preferred_ids = (
            set(seed_track_company_ids(session)) | set(universe_track_company_ids(session))
        ) - used_company_ids
        preferred = [session.get(Company, cid) for cid in sorted(preferred_ids)]
        others = [
            c
            for c in session.scalars(select(Company).order_by(Company.id)).all()
            if c.id not in used_company_ids and c.id not in preferred_ids
        ]
        seed_candidates = [c for c in preferred if c is not None] + others

        seeded_this_run: list[SeededQCItem] = []
        candidate_idx = 0
        while len(seeded_this_run) < n_to_seed and candidate_idx < len(seed_candidates):
            flaw_type = ALL_FLAW_TYPES[len(seeded_this_run) % len(ALL_FLAW_TYPES)]
            company = seed_candidates[candidate_idx]
            candidate_idx += 1
            try:
                seed_result = seed_flawed_dossier(
                    session, company.id, dt.date(2019, 1, 1), flaw_type
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  could not seed against {company.display_name}: {exc}")
                continue
            seeded_this_run.append(seed_result)
        if len(seeded_this_run) < n_to_seed:
            print("WARNING: ran out of distinct real companies to seed against.")

        with (
            MANIFEST_PATH.open("a", encoding="utf-8") as fh,
            ANSWER_KEY_PATH.open("a", encoding="utf-8") as key_fh,
        ):
            for seeded in seeded_this_run:
                fh.write(
                    json.dumps(
                        asdict(
                            ManifestItem(
                                investigation_id=str(seeded.investigation_id),
                                company_id=str(seeded.company_id),
                                as_of=seeded.as_of.isoformat(),
                                dossier_id=str(seeded.dossier_id),
                                review_task_id=str(seeded.review_task_id),
                                track="n/a",
                                score_found=False,
                                score_value=None,
                                seeded_qc=True,
                            )
                        ),
                        sort_keys=True,
                    )
                    + "\n"
                )
                key_fh.write(
                    json.dumps(
                        {
                            "review_task_id": str(seeded.review_task_id),
                            "investigation_id": str(seeded.investigation_id),
                            "flaw_type": seeded.flaw_type,
                            "flawed_claim_id": str(seeded.flawed_claim_id),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

    total_lines = (
        len(MANIFEST_PATH.read_text(encoding="utf-8").splitlines()) if MANIFEST_PATH.exists() else 0
    )
    print(f"\nmanifest now has {total_lines} total item(s): {MANIFEST_PATH}")
    print(f"answer key (do not show the reviewer): {ANSWER_KEY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
