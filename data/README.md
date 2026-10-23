# data/

- `raw/` — unmodified downloaded documents, organised `raw/<source>/<yyyy>/...`.
  Gitignored. Populated by `scripts/acquire_seed.py` (Phase 0) and later by
  the Phase 1 ingestion pipeline.
- `interim/` — intermediate derived artefacts (future phases). Gitignored.
- `processed/` — analysis-ready outputs (future phases). Gitignored.
- `manifests/` — JSONL metadata describing every downloaded file (URL,
  retrieval time, hash, size, licence/redistribution status, etc.) and the
  machine-readable source inventory (`sources.yaml`). **Committed** —
  manifests never contain document content, only provenance metadata.

Nothing under `raw/`, `interim/` or `processed/` is ever committed: these
directories may hold copyrighted or redistribution-unclear third-party
documents. See `docs/data/source-inventory.md` for per-source terms.
