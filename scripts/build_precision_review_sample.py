"""Enhancement `precision-review` §1-2: freezes the current production
detector for KMP_EXIT/ID_EXIT/RPT_GROWTH and builds a fresh, untouched,
deterministic sample for later human precision review. Read-only against
every table it queries; writes only the two manifests named below and
never labels, reviews, or decides anything itself.

Usage:
    uv run python scripts/build_precision_review_sample.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.precision_review import (  # noqa: E402
    SAMPLE_SEED,
    SAMPLE_SIZE_PER_TYPE,
    TARGET_EVENT_TYPES,
    build_exclusion_set,
    current_detector_state,
    run_frozen_detector,
    stratified_sample,
)

DETECTOR_FREEZE_PATH = REPO_ROOT / "data" / "manifests" / "precision-review-v1-detector.json"
SAMPLE_MANIFEST_PATH = REPO_ROOT / "data" / "manifests" / "precision-review-v1.jsonl"


def main() -> int:
    import datetime as dt

    settings = load_settings()
    session_factory = make_session_factory(settings)

    detector_state = current_detector_state()
    freeze_record = {
        "frozen_at": dt.datetime.now(dt.UTC).isoformat(),
        "sample_seed": SAMPLE_SEED,
        "sample_size_per_type": SAMPLE_SIZE_PER_TYPE,
        "disclosure": (
            "No Event-table row of KMP_EXIT, ID_EXIT or RPT_GROWTH exists in this "
            "database; extraction_pipeline.py only wires AUD_RESIGN (see "
            "docs/modelling/event-reliability.md). This freeze instead locks the "
            "exact classifier code/artifact that stands in as 'the detector' for "
            "these three types, run directly over chunk text -- see "
            "ledgerlight/knowledge/precision_review.py's module docstring."
        ),
        "detectors": detector_state,
    }
    DETECTOR_FREEZE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DETECTOR_FREEZE_PATH.open("w", encoding="utf-8") as f:
        json.dump(freeze_record, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"detector freeze written: {DETECTOR_FREEZE_PATH}")
    print(json.dumps(detector_state, indent=2, sort_keys=True))

    with session_factory() as session:
        exclusion = build_exclusion_set(session)
        print("\n-- exclusion --")
        for source, count in exclusion.by_source.items():
            print(f"  {source}: {count}")
        for note in exclusion.notes:
            print(f"  note: {note}")
        print(f"  total excluded chunk_ids (union): {len(exclusion.excluded_chunk_ids)}")

        rows: list[dict[str, object]] = []
        print("\n-- sample composition --")
        for event_type in TARGET_EVENT_TYPES:
            candidates = run_frozen_detector(
                session, event_type, excluded_chunk_ids=exclusion.excluded_chunk_ids
            )
            result = stratified_sample(candidates, seed=SAMPLE_SEED, limit=SAMPLE_SIZE_PER_TYPE)
            print(
                f"{event_type}: eligible={result.eligible_total} "
                f"sampled={len(result.selected)} shortfall={result.shortfall}"
            )
            print(f"  companies: {result.companies}")
            if result.shortfall > 0:
                print(
                    f"  SHORTFALL: only {result.eligible_total} eligible chunk(s) exist "
                    f"for {event_type} after exclusions; took all of them, below the "
                    f"target of {SAMPLE_SIZE_PER_TYPE}."
                )
            for c in result.selected:
                rows.append(
                    {
                        "id": str(c.chunk_id),
                        "type": c.event_type,
                        "company": c.company_name or "(unknown company)",
                        "seed": SAMPLE_SEED,
                    }
                )

    SAMPLE_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLE_MANIFEST_PATH.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    sha256 = hashlib.sha256(SAMPLE_MANIFEST_PATH.read_bytes()).hexdigest()
    print(f"\nsample manifest written: {SAMPLE_MANIFEST_PATH} ({len(rows)} item(s))")
    print(f"sample manifest sha256: {sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
