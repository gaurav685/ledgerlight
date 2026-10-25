"""Manifest schema for every file the acquisition utility downloads.

Manifest entries are metadata only (never document content) and are
committed as JSONL under data/manifests/. See docs/data/source-inventory.md
for the human-readable per-source findings this metadata is drawn from.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TOOL_VERSION = "ledgerlight-acquisition/0.1"


class CompanyIdentifiers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bse_scrip_code: str | None = None
    nse_symbol: str | None = None
    isin: str | None = None


class ManifestEntry(BaseModel):
    """One downloaded (or skipped-as-duplicate) file."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(description="Stable unique id for this manifest entry (e.g. a UUID)")
    source_id: str = Field(
        description="Key into data/manifests/sources.yaml, e.g. 'bse', 'nse', 'sebi'"
    )

    source_url: str = Field(description="Canonical/landing URL the document is referenced from")
    retrieval_url: str = Field(description="Exact URL actually fetched")

    retrieved_at: str = Field(description="UTC ISO-8601 timestamp of retrieval")
    retrieval_method: Literal["automated_fetch", "manual_browser_download", "archive_snapshot"] = (
        Field(description="How this file actually reached data/raw/")
    )
    http_status: int
    content_type: str | None = None

    bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)

    local_path: str = Field(description="Path relative to repo root; the file itself is gitignored")

    company_identifiers: CompanyIdentifiers | None = None

    document_type: str = Field(default="unknown")
    publication_time: str | None = Field(
        default=None, description="As stated by the source, else null"
    )
    coverage_note: str | None = None

    licence_status: Literal[
        "public_no_explicit_licence",
        "open_licence",
        "registration_required",
        "payment_required",
        "unclear",
    ]
    terms_url: str | None = None
    redistribution_allowed: bool | Literal["unclear"]

    known_limitations: str | None = None
    tool_version: str = Field(default=TOOL_VERSION)

    skipped_duplicate_of: str | None = Field(
        default=None,
        description="record_id of the entry this duplicate content matches, if skipped",
    )


def json_schema() -> dict[str, object]:
    return ManifestEntry.model_json_schema()


def write_json_schema(path: Path) -> None:
    path.write_text(json.dumps(json_schema(), indent=2) + "\n", encoding="utf-8")


def append_entry(manifest_path: Path, entry: ManifestEntry) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def read_entries(manifest_path: Path) -> list[ManifestEntry]:
    if not manifest_path.exists():
        return []
    entries: list[ManifestEntry] = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entries.append(ManifestEntry.model_validate_json(line))
    return entries
