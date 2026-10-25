"""store-backfill: load every Phase 0/Correction-1 manifest file into
object storage and the metadata DB. Idempotent — running it twice changes
nothing, because every write is guarded by an existence check keyed on
immutable identity (object storage: content hash; DB: unique constraints
on (source_id, source_key) for documents and (document_id, sha256) for
versions). The actual upsert logic lives in ledgerlight.ingestion.upsert,
shared with the live per-source ingestion jobs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from ledgerlight.acquisition.manifest import ManifestEntry, read_entries
from ledgerlight.common.hashing import sha256_file
from ledgerlight.ingestion.upsert import upsert_document_version
from ledgerlight.storage.s3_store import ObjectStore


@dataclass
class BackfillStats:
    entries_seen: int = 0
    documents_created: int = 0
    versions_created: int = 0
    versions_already_present: int = 0
    objects_uploaded: int = 0
    objects_already_present: int = 0
    hash_mismatches: list[str] = field(default_factory=list)


def _distinct_content_occurrences(entries: list[ManifestEntry]) -> list[ManifestEntry]:
    """Collapse manifest entries (which include duplicate-skip bookkeeping
    rows, possibly across multiple acquire_seed runs) down to one entry
    per (source_id, retrieval_url, sha256) — the first time that exact
    content was seen at that URL. A changed sha256 at the same URL is a
    real new version; a repeated identical sha256 is not."""
    by_key: dict[tuple[str, str, str], ManifestEntry] = {}
    for entry in sorted(entries, key=lambda e: e.retrieved_at):
        key = (entry.source_id, entry.retrieval_url, entry.sha256)
        if key not in by_key:
            by_key[key] = entry
    return list(by_key.values())


def run_store_backfill(
    session: Session,
    store: ObjectStore,
    manifest_paths: list[Path],
) -> BackfillStats:
    stats = BackfillStats()

    all_entries: list[ManifestEntry] = []
    for p in manifest_paths:
        all_entries.extend(read_entries(p))
    stats.entries_seen = len(all_entries)

    for entry in _distinct_content_occurrences(all_entries):
        local_path = Path(entry.local_path)
        if not local_path.exists():
            # Fresh clone with no downloaded files yet — not an error, just nothing to load.
            continue

        actual_hash = sha256_file(local_path)
        if actual_hash != entry.sha256:
            stats.hash_mismatches.append(str(local_path))
            continue

        body = local_path.read_bytes()
        was_uploaded_before = store.exists(store.object_key(entry.sha256, local_path.suffix))

        _version, doc_new, version_new = upsert_document_version(session, store, entry, body)

        if not was_uploaded_before:
            stats.objects_uploaded += 1
        else:
            stats.objects_already_present += 1
        if doc_new:
            stats.documents_created += 1
        if version_new:
            stats.versions_created += 1
        else:
            stats.versions_already_present += 1

    session.commit()
    return stats
