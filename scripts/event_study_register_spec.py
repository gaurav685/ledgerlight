"""Enhancement 1 §1: freeze a governance event-study pre-registration
spec by recording its real sha256 in `model_registry`
(`model_name="event-study-spec"`), reusing the exact table
`scripts/train_risk.py` already writes to -- never a new, duplicate
registry.

Guards the real freeze requirement the brief asks for: a given
`model_version` (spec version, e.g. "v1") may be registered once with
one real hash. Registering the SAME file content again under the
SAME version is a no-op (idempotent). Registering DIFFERENT content
under a version that is already registered is refused -- a revised
spec is a new version (`--version v2`), reported alongside v1, never
a silent overwrite of a version results may already exist under.

Usage:
    python3 -m uv run python scripts/event_study_register_spec.py \
        --spec docs/enhancements/event-study/spec.v1.json --version v1
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402

MODEL_NAME = "event-study-spec"


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze a governance event-study spec.")
    parser.add_argument("--spec", required=True, help="path to the machine-readable spec JSON")
    parser.add_argument("--version", required=True, help='spec version, e.g. "v1"')
    args = parser.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.is_file():
        print(f"spec file not found: {spec_path}")
        return 1
    spec_bytes = spec_path.read_bytes()
    spec_sha256 = hashlib.sha256(spec_bytes).hexdigest()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        existing = session.execute(
            text(
                "SELECT artifact_hash FROM model_registry "
                "WHERE model_name = :model_name AND model_version = :model_version"
            ),
            {"model_name": MODEL_NAME, "model_version": args.version},
        ).first()

        if existing is not None:
            existing_hash = existing[0]
            if existing_hash == spec_sha256:
                print(
                    f"{MODEL_NAME}/{args.version} already registered with this exact "
                    f"spec (sha256={spec_sha256}) -- no-op, nothing changed."
                )
                return 0
            print(
                f"REFUSED: {MODEL_NAME}/{args.version} is already registered with a "
                f"DIFFERENT real hash ({existing_hash}) than this file's real hash "
                f"({spec_sha256}). A revised spec must be a NEW version "
                f"(e.g. --version v2), never an overwrite of a version results may "
                f"already exist under. Spec freeze guard: refused to write."
            )
            return 1

        session.execute(
            text(
                "INSERT INTO model_registry "
                "(id, model_name, model_version, artifact_hash, params_json) "
                "VALUES (gen_random_uuid(), :model_name, :model_version, :artifact_hash, "
                " CAST(:params AS JSONB))"
            ),
            {
                "model_name": MODEL_NAME,
                "model_version": args.version,
                "artifact_hash": spec_sha256,
                "params": spec_path.read_text(encoding="utf-8"),
            },
        )
        session.commit()

    print(f"model_registry: {MODEL_NAME}/{args.version} artifact_hash={spec_sha256}")
    print(f"frozen spec file: {spec_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
