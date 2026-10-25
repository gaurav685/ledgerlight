"""Import manually-downloaded documents from data/inbox/ into the manifest.

Some documents (BSE/NSE pages our acquisition tool is blocked from) are
only obtainable by a human using an ordinary browser — see
docs/data/manual-download-checklist.md. This module never fetches
anything itself; it only takes files a person has already placed in
data/inbox/ (gitignored) plus a provenance.csv describing where each one
came from, hashes them, copies them into data/raw/manual/, and records a
manifest entry with retrieval_method="manual_browser_download".
"""

from __future__ import annotations

import csv
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from ledgerlight.acquisition.manifest import ManifestEntry, append_entry
from ledgerlight.common.hashing import sha256_file
from ledgerlight.common.timeutil import utc_now_iso

PROVENANCE_FILENAME = "provenance.csv"
REQUIRED_PROVENANCE_COLUMNS = ("file_name", "original_url", "retrieved_at_by_user", "notes")


class MissingProvenanceError(RuntimeError):
    """Raised (per-file, caught by the caller) when a file has no provenance row."""


@dataclass
class ImportResult:
    imported: list[str]
    skipped_duplicate: list[str]
    rejected_no_provenance: list[str]


def _read_provenance(inbox_dir: Path) -> dict[str, dict[str, str]]:
    provenance_path = inbox_dir / PROVENANCE_FILENAME
    if not provenance_path.exists():
        return {}
    with provenance_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing_cols = set(REQUIRED_PROVENANCE_COLUMNS) - set(reader.fieldnames or [])
        if missing_cols:
            raise ValueError(f"{provenance_path} missing required columns: {sorted(missing_cols)}")
        return {row["file_name"]: row for row in reader}


def import_inbox(
    *,
    data_dir: Path,
    inbox_dir: Path | None = None,
    manifest_path: Path | None = None,
) -> ImportResult:
    """Import every file in inbox_dir that has a matching provenance.csv row.

    Idempotent: a file whose content (sha256) already exists under
    data/raw/manual/ is recorded as a duplicate skip, not re-imported.
    """
    inbox_dir = inbox_dir or (data_dir / "inbox")
    manifest_path = manifest_path or (data_dir / "manifests" / "manual.jsonl")

    result = ImportResult(imported=[], skipped_duplicate=[], rejected_no_provenance=[])

    if not inbox_dir.exists():
        return result

    provenance = _read_provenance(inbox_dir)

    candidate_files = sorted(
        p for p in inbox_dir.iterdir() if p.is_file() and p.name != PROVENANCE_FILENAME
    )

    for file_path in candidate_files:
        row = provenance.get(file_path.name)
        if row is None:
            result.rejected_no_provenance.append(file_path.name)
            continue

        digest = sha256_file(file_path)
        dest_dir = data_dir / "raw" / "manual"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{digest}{file_path.suffix}"

        if dest_path.exists() and sha256_file(dest_path) == digest:
            result.skipped_duplicate.append(file_path.name)
            continue

        shutil.copyfile(file_path, dest_path)

        entry = ManifestEntry(
            record_id=str(uuid.uuid4()),
            source_id="manual",
            source_url=row["original_url"],
            retrieval_url=row["original_url"],
            retrieved_at=utc_now_iso(),
            retrieval_method="manual_browser_download",
            http_status=200,
            content_type=None,
            bytes=dest_path.stat().st_size,
            sha256=digest,
            local_path=str(dest_path),
            document_type="unknown",
            publication_time=row.get("retrieved_at_by_user") or None,
            coverage_note=row.get("notes") or None,
            licence_status="unclear",
            redistribution_allowed="unclear",
            known_limitations=(
                "Manually downloaded by a human via browser; not fetched by the acquisition tool."
            ),
        )
        append_entry(manifest_path, entry)
        result.imported.append(file_path.name)

    return result
