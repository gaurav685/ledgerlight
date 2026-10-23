"""Pre-commit hook: refuse to commit anything under data/raw, data/interim or
data/processed. These are gitignored, but a force-add (git add -f) could
still stage one — this hook is the second line of defense.
"""

from __future__ import annotations

import sys

BLOCKED_PREFIXES = ("data/raw/", "data/interim/", "data/processed/")
ALLOWED_SUFFIXES = (".gitkeep",)


def main(argv: list[str]) -> int:
    bad = [
        path
        for path in argv
        if path.replace("\\", "/").startswith(BLOCKED_PREFIXES)
        and not path.endswith(ALLOWED_SUFFIXES)
    ]
    if bad:
        print("ERROR: refusing to commit files under data/raw, data/interim or data/processed:")
        for path in bad:
            print(f"  - {path}")
        print(
            "These directories hold downloaded third-party documents and must never be committed."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
