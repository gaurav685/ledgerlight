from __future__ import annotations

from pathlib import Path

from ledgerlight.acquisition.import_local import import_inbox
from ledgerlight.acquisition.manifest import read_entries


def test_empty_inbox_imports_nothing(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    result = import_inbox(data_dir=data_dir)
    assert result.imported == []
    assert result.skipped_duplicate == []
    assert result.rejected_no_provenance == []


def test_missing_inbox_dir_imports_nothing(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    result = import_inbox(data_dir=data_dir, inbox_dir=data_dir / "does_not_exist")
    assert result == import_inbox(data_dir=data_dir, inbox_dir=data_dir / "does_not_exist")


def test_file_without_provenance_row_is_rejected(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    inbox = data_dir / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "orphan.pdf").write_bytes(b"orphan content")
    (inbox / "provenance.csv").write_text(
        "file_name,original_url,retrieved_at_by_user,notes\n", encoding="utf-8"
    )

    result = import_inbox(data_dir=data_dir)

    assert result.imported == []
    assert result.rejected_no_provenance == ["orphan.pdf"]
    assert not (data_dir / "raw" / "manual").exists()


def test_file_with_provenance_is_imported(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    inbox = data_dir / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "report.pdf").write_bytes(b"real document content")
    (inbox / "provenance.csv").write_text(
        "file_name,original_url,retrieved_at_by_user,notes\n"
        "report.pdf,https://www.bseindia.com/example.pdf,2026-01-01,auditor resignation letter\n",
        encoding="utf-8",
    )

    result = import_inbox(data_dir=data_dir)

    assert result.imported == ["report.pdf"]
    entries = read_entries(data_dir / "manifests" / "manual.jsonl")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.retrieval_method == "manual_browser_download"
    assert entry.source_url == "https://www.bseindia.com/example.pdf"
    assert Path(entry.local_path).read_bytes() == b"real document content"


def test_reimport_same_content_is_idempotent(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    inbox = data_dir / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "a.pdf").write_bytes(b"identical bytes")
    (inbox / "provenance.csv").write_text(
        "file_name,original_url,retrieved_at_by_user,notes\n"
        "a.pdf,https://www.bseindia.com/a.pdf,2026-01-01,note\n",
        encoding="utf-8",
    )
    first = import_inbox(data_dir=data_dir)
    assert first.imported == ["a.pdf"]

    # Simulate the user dropping the exact same file in again.
    (inbox / "a_copy.pdf").write_bytes(b"identical bytes")
    (inbox / "provenance.csv").write_text(
        "file_name,original_url,retrieved_at_by_user,notes\n"
        "a.pdf,https://www.bseindia.com/a.pdf,2026-01-01,note\n"
        "a_copy.pdf,https://www.bseindia.com/a.pdf,2026-01-01,note\n",
        encoding="utf-8",
    )
    second = import_inbox(data_dir=data_dir)
    assert second.imported == []
    assert set(second.skipped_duplicate) == {"a.pdf", "a_copy.pdf"}
