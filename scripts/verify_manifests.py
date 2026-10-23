"""Validate every manifest under data/manifests/*.jsonl against the files on disk.

Usage:
  uv run python scripts/verify_manifests.py              # error on missing files
  uv run python scripts/verify_manifests.py --allow-missing   # fresh-clone mode
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.acquisition.manifest import ManifestEntry, read_entries  # noqa: E402
from ledgerlight.common.hashing import sha256_file  # noqa: E402

MANIFEST_DIR = REPO_ROOT / "data" / "manifests"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Treat files absent on a fresh clone as 'not downloaded' rather than errors",
    )
    args = parser.parse_args()

    manifest_files = sorted(MANIFEST_DIR.glob("*.jsonl"))
    if not manifest_files:
        print(f"No manifest files found under {MANIFEST_DIR}")
        return 0

    all_entries: list[ManifestEntry] = []
    for mf in manifest_files:
        all_entries.extend(read_entries(mf))

    hash_mismatches: list[str] = []
    missing_not_downloaded: list[str] = []
    missing_errors: list[str] = []

    for entry in all_entries:
        local_path = (
            REPO_ROOT / entry.local_path
            if not Path(entry.local_path).is_absolute()
            else Path(entry.local_path)
        )
        if not local_path.exists():
            if args.allow_missing:
                missing_not_downloaded.append(entry.record_id)
            else:
                missing_errors.append(entry.record_id)
            continue
        actual = sha256_file(local_path)
        if actual != entry.sha256:
            hash_mismatches.append(
                f"{entry.record_id} ({entry.local_path}): expected {entry.sha256}, got {actual}"
            )

    by_source = Counter(e.source_id for e in all_entries)
    by_doc_type = Counter(e.document_type for e in all_entries)
    by_year = Counter(e.retrieved_at[:4] for e in all_entries)
    by_company: Counter[str] = Counter()
    for e in all_entries:
        if e.company_identifiers:
            key = (
                e.company_identifiers.nse_symbol
                or e.company_identifiers.bse_scrip_code
                or "unknown"
            )
            by_company[key] += 1

    print(f"Manifests checked: {[mf.name for mf in manifest_files]}")
    print(f"Total entries: {len(all_entries)}")
    print(f"By source: {dict(by_source)}")
    print(f"By document_type: {dict(by_doc_type)}")
    print(f"By year (retrieved_at): {dict(by_year)}")
    print(f"By company: {dict(by_company)}")

    if args.allow_missing:
        print(f"Not downloaded (fresh clone, --allow-missing): {len(missing_not_downloaded)}")

    if missing_errors:
        print(f"ERROR: {len(missing_errors)} manifest entries reference missing local files:")
        for rid in missing_errors:
            print(f"  - {rid}")

    if hash_mismatches:
        print(f"ERROR: {len(hash_mismatches)} sha256 mismatches:")
        for m in hash_mismatches:
            print(f"  - {m}")

    if hash_mismatches or missing_errors:
        return 1
    print("OK: all present files match their recorded sha256.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
