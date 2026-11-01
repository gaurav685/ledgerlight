"""Phase 5 §3/§10: exports the real FastAPI app's own live OpenAPI
schema to docs/api/openapi.json -- never hand-written, never allowed
to drift from the real routes/schemas, since it's generated directly
from `ledgerlight.api.app.create_app()` itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.api.app import create_app  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "docs" / "api" / "openapi.json"


def main() -> int:
    app = create_app()
    schema = app.openapi()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"exported real OpenAPI schema ({len(schema.get('paths', {}))} paths) to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
