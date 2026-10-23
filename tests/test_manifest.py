from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ledgerlight.acquisition.manifest import ManifestEntry, append_entry, json_schema, read_entries

VALID_KWARGS = dict(
    record_id="r1",
    source_id="sebi",
    source_url="https://www.sebi.gov.in/enforcement/orders/example.html",
    retrieval_url="https://www.sebi.gov.in/enforcement/orders/example.pdf",
    retrieved_at="2026-01-01T00:00:00+00:00",
    http_status=200,
    content_type="application/pdf",
    bytes=1234,
    sha256="a" * 64,
    local_path="data/raw/sebi/2026/aaaa.pdf",
    licence_status="public_no_explicit_licence",
    redistribution_allowed="unclear",
)


def test_manifest_entry_round_trips_json() -> None:
    entry = ManifestEntry(**VALID_KWARGS)
    again = ManifestEntry.model_validate_json(entry.model_dump_json())
    assert again == entry


def test_manifest_entry_rejects_bad_sha256_length() -> None:
    bad = dict(VALID_KWARGS, sha256="tooshort")
    with pytest.raises(ValidationError):
        ManifestEntry(**bad)


def test_manifest_entry_rejects_unknown_licence_status() -> None:
    bad = dict(VALID_KWARGS, licence_status="made_up_status")
    with pytest.raises(ValidationError):
        ManifestEntry(**bad)


def test_json_schema_exports_required_fields() -> None:
    schema = json_schema()
    assert "sha256" in schema["properties"]
    assert "record_id" in schema["required"]


def test_append_and_read_entries_round_trip(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifests" / "test.jsonl"
    entry1 = ManifestEntry(**VALID_KWARGS)
    entry2 = ManifestEntry(**dict(VALID_KWARGS, record_id="r2", sha256="b" * 64))

    append_entry(manifest_path, entry1)
    append_entry(manifest_path, entry2)

    entries = read_entries(manifest_path)
    assert [e.record_id for e in entries] == ["r1", "r2"]


def test_read_entries_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_entries(tmp_path / "does_not_exist.jsonl") == []
