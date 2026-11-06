# Data dictionary

Generated from the real, live database schema (reflected directly, not just imported SQLAlchemy models -- see this script's own docstring for why) by `scripts/generate_data_dictionary.py` -- never hand-written. 52 real tables, as of this run (excludes Alembic's own `alembic_version` bookkeeping table). Regenerate after any schema change; do not hand-edit this file.

## `alert_rules`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `watchlist_id` | UUID | no |  | FK -> `watchlists.id` |
| `rule_type` | VARCHAR(32) | no |  |  |
| `config` | JSONB | no |  |  |
| `is_active` | BOOLEAN | no |  |  |
| `created_by` | UUID | no |  | FK -> `users.id` |
| `created_at` | TIMESTAMP | no | now() |  |

Check constraints: rule_type::text = ANY (ARRAY['new_event_type'::character varying, 'score_percentile_threshold'::character varying]::text[])

## `alerts`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `alert_rule_id` | UUID | no |  | FK -> `alert_rules.id` |
| `company_id` | UUID | no |  | FK -> `companies.id` |
| `payload` | JSONB | no |  |  |
| `triggered_at` | TIMESTAMP | no | now() |  |
| `acknowledged_at` | TIMESTAMP | yes |  |  |
| `acknowledged_by` | UUID | yes |  | FK -> `users.id` |

## `api_keys`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `user_id` | UUID | no |  | FK -> `users.id` |
| `name` | VARCHAR(200) | no |  |  |
| `key_prefix` | VARCHAR(16) | no |  |  |
| `key_hash` | VARCHAR(128) | no |  |  |
| `scopes` | JSONB | no |  |  |
| `expires_at` | TIMESTAMP | yes |  |  |
| `revoked_at` | TIMESTAMP | yes |  |  |
| `last_used_at` | TIMESTAMP | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Indexes: ix_api_keys_key_prefix

Unique constraints: (key_hash)

## `audit_logs`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `actor_user_id` | UUID | yes |  | FK -> `users.id` |
| `actor_api_key_id` | UUID | yes |  | FK -> `api_keys.id` |
| `action` | VARCHAR(100) | no |  |  |
| `target_type` | VARCHAR(64) | yes |  |  |
| `target_id` | VARCHAR(64) | yes |  |  |
| `request_id` | VARCHAR(64) | yes |  |  |
| `ip` | VARCHAR(64) | yes |  |  |
| `extra` | JSONB | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `chunks`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `version_id` | UUID | no |  | FK -> `document_versions.id` |
| `page_number` | INTEGER | no |  |  |
| `char_start` | INTEGER | no |  |  |
| `char_end` | INTEGER | no |  |  |
| `text` | TEXT | no |  |  |
| `chunker_version` | VARCHAR(32) | no |  |  |
| `tsv` | TSVECTOR | yes |  |  |
| `embedding` | VECTOR(384) | yes |  |  |
| `embedding_model_name` | VARCHAR(128) | yes |  |  |
| `embedding_model_version` | VARCHAR(32) | yes |  |  |
| `known_at` | TIMESTAMP | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Indexes: ix_chunks_tsv

Unique constraints: (version_id, page_number, char_start, char_end, chunker_version)

Check constraints: char_end > char_start

## `claims`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `investigation_id` | UUID | no |  | FK -> `investigations.id` |
| `claim_type` | VARCHAR(16) | no |  |  |
| `payload` | JSONB | no |  |  |
| `evidence` | JSONB | no |  |  |
| `verification_status` | VARCHAR(16) | no |  |  |
| `verification_checks` | JSONB | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `companies`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `display_name` | VARCHAR(256) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `company_identifiers`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `company_id` | UUID | no |  | FK -> `companies.id` |
| `identifier_type` | VARCHAR(32) | no |  |  |
| `value` | VARCHAR(64) | no |  |  |
| `valid_from` | DATE | yes |  |  |
| `valid_to` | DATE | yes |  |  |
| `source_version_id` | UUID | yes |  | FK -> `document_versions.id` |
| `source_price_bar_id` | UUID | yes |  | FK -> `price_bars.id` |
| `note` | TEXT | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Indexes: ix_company_identifiers_type_value

## `dead_letters`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `payload_ref` | VARCHAR(512) | no |  |  |
| `stage` | VARCHAR(32) | no |  |  |
| `last_error` | TEXT | no |  |  |
| `attempts` | INTEGER | no |  |  |
| `first_failed_at` | TIMESTAMP | no |  |  |
| `resolved_at` | TIMESTAMP | yes |  |  |
| `resolution` | TEXT | yes |  |  |

## `document_pages`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `version_id` | UUID | no |  | FK -> `document_versions.id` |
| `page_number` | INTEGER | no |  |  |
| `raw_text` | TEXT | no |  |  |
| `text_sha256` | VARCHAR(64) | no |  |  |
| `char_count` | INTEGER | no |  |  |
| `extraction_method` | VARCHAR(16) | no |  |  |
| `ocr_engine` | VARCHAR(64) | yes |  |  |
| `ocr_engine_version` | VARCHAR(32) | yes |  |  |
| `ocr_mean_confidence` | NUMERIC(5, 4) | yes |  |  |
| `extractor_version` | VARCHAR(32) | no |  |  |
| `normalized_text` | TEXT | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Unique constraints: (version_id, page_number, extractor_version)

## `document_versions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `document_id` | UUID | no |  | FK -> `documents.id` |
| `sha256` | VARCHAR(64) | no |  |  |
| `object_key` | VARCHAR(512) | no |  |  |
| `bytes` | BIGINT | no |  |  |
| `mime_type` | VARCHAR(128) | yes |  |  |
| `retrieval_method` | VARCHAR(32) | no |  |  |
| `retrieval_url` | VARCHAR(1024) | no |  |  |
| `http_status` | INTEGER | yes |  |  |
| `retrieved_at` | TIMESTAMP | no |  |  |
| `published_at` | TIMESTAMP | yes |  |  |
| `snapshot_at` | TIMESTAMP | yes |  |  |
| `known_at` | TIMESTAMP | no |  |  |
| `known_at_basis` | VARCHAR(16) | no |  |  |
| `tool_version` | VARCHAR(64) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |
| `content_sha256` | VARCHAR(64) | yes |  |  |

Indexes: ix_document_versions_doc_content_sha256, ix_document_versions_sha256

Unique constraints: (document_id, sha256)

## `documents`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `source_id` | VARCHAR(64) | no |  | FK -> `sources.id` |
| `source_key` | VARCHAR(1024) | no |  |  |
| `bse_code` | VARCHAR(32) | yes |  |  |
| `nse_symbol` | VARCHAR(32) | yes |  |  |
| `isin` | VARCHAR(16) | yes |  |  |
| `company_name_raw` | VARCHAR(256) | yes |  |  |
| `document_type` | VARCHAR(64) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Unique constraints: (source_id, source_key)

## `dossiers`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `investigation_id` | UUID | no |  | FK -> `investigations.id` |
| `version` | INTEGER | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `sections` | JSONB | no |  |  |
| `claim_id_map` | JSONB | no |  |  |
| `renderer_name` | VARCHAR(64) | no |  |  |
| `renderer_version` | VARCHAR(32) | no |  |  |
| `prompt_version` | VARCHAR(32) | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Unique constraints: (investigation_id, version)

## `entities`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `entity_type` | VARCHAR(16) | no |  |  |
| `company_id` | UUID | yes |  | FK -> `companies.id` |
| `display_name` | VARCHAR(256) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `entity_identifiers`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `entity_id` | UUID | no |  | FK -> `entities.id` |
| `identifier_type` | VARCHAR(32) | no |  |  |
| `value` | VARCHAR(64) | no |  |  |
| `evidence_version_id` | UUID | yes |  | FK -> `document_versions.id` |
| `evidence_page` | INTEGER | yes |  |  |
| `evidence_char_start` | INTEGER | yes |  |  |
| `evidence_char_end` | INTEGER | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `entity_links`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `mention_id` | UUID | no |  | FK -> `mentions.id` |
| `entity_id` | UUID | no |  | FK -> `entities.id` |
| `method` | VARCHAR(32) | no |  |  |
| `score` | DOUBLE PRECISION | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `entity_merges`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `source_entity_id` | UUID | no |  | FK -> `entities.id` |
| `target_entity_id` | UUID | no |  | FK -> `entities.id` |
| `reason` | TEXT | no |  |  |
| `actor` | VARCHAR(64) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |
| `reversed_at` | TIMESTAMP | yes |  |  |
| `reversed_by` | VARCHAR(64) | yes |  |  |

## `event_fields`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `event_id` | UUID | no |  | FK -> `events.id` |
| `field_name` | VARCHAR(64) | no |  |  |
| `value_json` | JSONB | yes |  |  |
| `normalized_value` | TEXT | yes |  |  |
| `evidence_version_id` | UUID | no |  | FK -> `document_versions.id` |
| `evidence_page` | INTEGER | no |  |  |
| `evidence_char_start` | INTEGER | no |  |  |
| `evidence_char_end` | INTEGER | no |  |  |
| `extractor_name` | VARCHAR(64) | no |  |  |
| `extractor_version` | VARCHAR(32) | no |  |  |
| `confidence` | DOUBLE PRECISION | no |  |  |
| `validation_status` | VARCHAR(16) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `event_types`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `taxonomy_version_id` | UUID | no |  | FK -> `taxonomy_versions.id` |
| `code` | VARCHAR(32) | no |  |  |
| `name` | VARCHAR(128) | no |  |  |
| `definition` | TEXT | no |  |  |
| `required_fields` | JSONB | no |  |  |
| `optional_fields` | JSONB | no |  |  |
| `severity_rules` | JSONB | no |  |  |
| `detection_approach` | VARCHAR(32) | no |  |  |
| `thresholds` | JSONB | no |  |  |

Unique constraints: (taxonomy_version_id, code)

## `event_versions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `event_id` | UUID | no |  | FK -> `events.id` |
| `status` | VARCHAR(16) | no |  |  |
| `reviewer` | VARCHAR(64) | no |  |  |
| `review_task_id` | UUID | yes |  | FK -> `review_tasks.id` |
| `notes` | TEXT | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `events`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `event_type_id` | UUID | no |  | FK -> `event_types.id` |
| `company_id` | UUID | yes |  | FK -> `companies.id` |
| `event_time` | TIMESTAMP | yes |  |  |
| `published_at` | TIMESTAMP | yes |  |  |
| `known_at` | TIMESTAMP | no |  |  |
| `severity` | VARCHAR(16) | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `detector_name` | VARCHAR(64) | no |  |  |
| `detector_version` | VARCHAR(32) | no |  |  |
| `confidence` | DOUBLE PRECISION | no |  |  |
| `supersedes_event_id` | UUID | yes |  | FK -> `events.id` |
| `created_at` | TIMESTAMP | no | now() |  |

## `experiments`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `config_json` | JSONB | no |  |  |
| `data_snapshot_hashes` | JSONB | no |  |  |
| `git_sha` | VARCHAR(40) | no |  |  |
| `metrics_json` | JSONB | no |  |  |
| `artifacts_uri` | VARCHAR(512) | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `feature_definitions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `name` | VARCHAR(64) | no |  |  |
| `version` | VARCHAR(32) | no |  |  |
| `description` | TEXT | no |  |  |
| `inputs` | JSONB | no |  |  |
| `provenance_tier` | VARCHAR(16) | no |  |  |
| `as_of_semantics` | TEXT | no |  |  |
| `lookback_days` | INTEGER | yes |  |  |
| `track` | VARCHAR(16) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Unique constraints: (name, version)

## `feature_snapshots`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `company_id` | UUID | no |  | FK -> `companies.id` |
| `as_of` | DATE | no |  |  |
| `feature_set_version` | VARCHAR(32) | no |  |  |
| `values` | JSONB | no |  |  |
| `max_input_known_at` | TIMESTAMP | yes |  |  |
| `data_quality_flags` | JSONB | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Indexes: ix_feature_snapshots_as_of

Unique constraints: (company_id, as_of, feature_set_version)

## `filings`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `version_id` | UUID | no |  | FK -> `document_versions.id` |
| `company_id` | UUID | no |  | FK -> `companies.id` |
| `link_method` | VARCHAR(32) | no |  |  |
| `confidence` | DOUBLE PRECISION | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Unique constraints: (version_id, company_id)

## `identifier_window_corrections`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `identifier_id` | UUID | yes |  | FK -> `company_identifiers.id` |
| `old_valid_from` | DATE | no |  |  |
| `new_valid_from` | DATE | no |  |  |
| `reason` | TEXT | no |  |  |
| `script_name` | VARCHAR(128) | no |  |  |
| `script_version` | VARCHAR(32) | no |  |  |
| `applied_at` | TIMESTAMP | no | now() |  |
| `identifier_type` | VARCHAR(32) | no |  |  |
| `value` | VARCHAR(64) | no |  |  |

## `ingestion_runs`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `source_id` | VARCHAR(64) | yes |  | FK -> `sources.id` |
| `stage` | VARCHAR(32) | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `started_at` | TIMESTAMP | no |  |  |
| `finished_at` | TIMESTAMP | yes |  |  |
| `fetched` | INTEGER | no |  |  |
| `new` | INTEGER | no |  |  |
| `unchanged` | INTEGER | no |  |  |
| `failed` | INTEGER | no |  |  |
| `ocr_pages` | INTEGER | no |  |  |
| `rows_parsed` | INTEGER | no |  |  |
| `rows_quarantined` | INTEGER | no |  |  |

## `investigation_steps`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `investigation_id` | UUID | no |  | FK -> `investigations.id` |
| `step_no` | INTEGER | no |  |  |
| `state` | VARCHAR(16) | no |  |  |
| `tool_calls` | JSONB | no |  |  |
| `outputs` | JSONB | no |  |  |
| `started_at` | TIMESTAMP | no | now() |  |
| `finished_at` | TIMESTAMP | yes |  |  |

Unique constraints: (investigation_id, step_no)

## `investigations`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `company_id` | UUID | no |  | FK -> `companies.id` |
| `as_of` | DATE | no |  |  |
| `requested_by` | VARCHAR(64) | no |  |  |
| `state` | VARCHAR(16) | no |  |  |
| `final_status` | VARCHAR(16) | yes |  |  |
| `failure_reason` | TEXT | yes |  |  |
| `budget_config` | JSONB | no |  |  |
| `usage` | JSONB | no |  |  |
| `started_at` | TIMESTAMP | no | now() |  |
| `finished_at` | TIMESTAMP | yes |  |  |
| `tenant_id` | UUID | yes |  | FK -> `tenants.id` |

## `label_item_fields`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `label_item_id` | UUID | no |  | FK -> `label_items.id` |
| `field_name` | VARCHAR(64) | no |  |  |
| `proposed_value_json` | JSONB | yes |  |  |
| `proposed_char_start` | INTEGER | yes |  |  |
| `proposed_char_end` | INTEGER | yes |  |  |
| `review_status` | VARCHAR(16) | no |  |  |
| `corrected_value_json` | JSONB | yes |  |  |
| `reviewer` | VARCHAR(64) | yes |  |  |
| `reviewed_at` | TIMESTAMP | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `label_items`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `version_id` | UUID | no |  | FK -> `document_versions.id` |
| `page_number` | INTEGER | no |  |  |
| `chunk_id` | UUID | yes |  | FK -> `chunks.id` |
| `proposed_event_type_code` | VARCHAR(32) | no |  |  |
| `proposed_confidence` | DOUBLE PRECISION | yes |  |  |
| `proposer_name` | VARCHAR(64) | no |  |  |
| `proposer_version` | VARCHAR(32) | no |  |  |
| `label_source` | VARCHAR(32) | no |  |  |
| `review_status` | VARCHAR(16) | no |  |  |
| `corrected_event_type_code` | VARCHAR(32) | yes |  |  |
| `reviewer` | VARCHAR(64) | yes |  |  |
| `reviewed_at` | TIMESTAMP | yes |  |  |
| `split` | VARCHAR(16) | yes |  |  |
| `company_id` | UUID | yes |  | FK -> `companies.id` |
| `created_at` | TIMESTAMP | no | now() |  |
| `review_note` | TEXT | yes |  |  |

## `memberships`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `user_id` | UUID | no |  | FK -> `users.id` |
| `role` | VARCHAR(16) | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `invited_by` | UUID | yes |  | FK -> `users.id` |
| `created_at` | TIMESTAMP | no | now() |  |

Unique constraints: (tenant_id, user_id)

Check constraints: role::text = ANY (ARRAY['viewer'::character varying, 'analyst'::character varying, 'reviewer'::character varying, 'tenant_admin'::character varying]::text[]), status::text = ANY (ARRAY['invited'::character varying, 'active'::character varying, 'revoked'::character varying]::text[])

## `mentions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `version_id` | UUID | no |  | FK -> `document_versions.id` |
| `page_number` | INTEGER | no |  |  |
| `char_start` | INTEGER | no |  |  |
| `char_end` | INTEGER | no |  |  |
| `surface_text` | VARCHAR(512) | no |  |  |
| `guessed_entity_type` | VARCHAR(16) | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Unique constraints: (version_id, page_number, char_start, char_end)

## `model_registry`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `model_name` | VARCHAR(64) | no |  |  |
| `model_version` | VARCHAR(64) | no |  |  |
| `artifact_hash` | VARCHAR(64) | yes |  |  |
| `training_data_snapshot_hash` | VARCHAR(64) | yes |  |  |
| `params_json` | JSONB | yes |  |  |
| `metrics_json` | JSONB | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Unique constraints: (model_name, model_version)

## `outcomes`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `event_id` | UUID | no |  | FK -> `events.id` |
| `outcome_type` | VARCHAR(64) | yes |  |  |
| `outcome_value` | JSONB | yes |  |  |
| `observed_at` | TIMESTAMP | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `price_bars`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `source_id` | VARCHAR(64) | no |  | FK -> `sources.id` |
| `version_id` | UUID | no |  | FK -> `document_versions.id` |
| `row_number` | INTEGER | no |  |  |
| `trade_date` | DATE | no |  |  |
| `symbol` | VARCHAR(32) | no |  |  |
| `series` | VARCHAR(8) | no |  |  |
| `isin` | VARCHAR(16) | yes |  |  |
| `open` | NUMERIC(14, 4) | yes |  |  |
| `high` | NUMERIC(14, 4) | yes |  |  |
| `low` | NUMERIC(14, 4) | yes |  |  |
| `close` | NUMERIC(14, 4) | yes |  |  |
| `last` | NUMERIC(14, 4) | yes |  |  |
| `prev_close` | NUMERIC(14, 4) | yes |  |  |
| `volume` | BIGINT | yes |  |  |
| `turnover` | NUMERIC(20, 4) | yes |  |  |
| `trades` | BIGINT | yes |  |  |
| `raw_row` | TEXT | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |
| `updated_at` | TIMESTAMP | no | now() |  |

Indexes: ix_price_bars_symbol, ix_price_bars_trade_date

Unique constraints: (source_id, trade_date, symbol, series)

## `processing_attempts`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `run_id` | UUID | yes |  | FK -> `ingestion_runs.id` |
| `version_id` | UUID | yes |  | FK -> `document_versions.id` |
| `stage` | VARCHAR(32) | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `error_class` | VARCHAR(32) | yes |  |  |
| `error_message` | TEXT | yes |  |  |
| `duration_ms` | INTEGER | no |  |  |
| `attempt_number` | INTEGER | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `rate_limit_counters`

*No SQLAlchemy ORM model -- accessed only via raw SQL (see the table's own creating migration for why).*

| column | type | nullable | default | key |
|---|---|---|---|---|
| `key` | VARCHAR(300) | no |  | PK |
| `window_start` | TIMESTAMP | no |  |  |
| `count` | INTEGER | no | 0 |  |

## `review_assignments`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `review_task_id` | UUID | no |  | FK -> `review_tasks.id` |
| `assignee_user_id` | UUID | no |  | FK -> `users.id` |
| `assigned_by` | UUID | no |  | FK -> `users.id` |
| `status` | VARCHAR(16) | no |  |  |
| `assigned_at` | TIMESTAMP | no | now() |  |

Check constraints: status::text = ANY (ARRAY['open'::character varying, 'in_progress'::character varying, 'done'::character varying]::text[])

## `review_decisions_audit`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `review_task_id` | UUID | no |  | FK -> `review_tasks.id` |
| `actor` | VARCHAR(64) | no |  |  |
| `action` | VARCHAR(32) | no |  |  |
| `before` | JSONB | yes |  |  |
| `after` | JSONB | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `review_queue`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `item_type` | VARCHAR(32) | no |  |  |
| `reference_id` | UUID | no |  |  |
| `reason_code` | VARCHAR(64) | no |  |  |
| `priority` | INTEGER | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `resolution` | TEXT | yes |  |  |
| `reviewer` | VARCHAR(64) | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |
| `resolved_at` | TIMESTAMP | yes |  |  |

## `review_tasks`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `dossier_id` | UUID | yes |  | FK -> `dossiers.id` |
| `claim_id` | UUID | yes |  | FK -> `claims.id` |
| `reason_code` | VARCHAR(32) | no |  |  |
| `priority` | INTEGER | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `assignee` | VARCHAR(64) | yes |  |  |
| `decision` | VARCHAR(32) | yes |  |  |
| `decision_notes` | TEXT | yes |  |  |
| `decided_at` | TIMESTAMP | yes |  |  |
| `seeded_qc` | BOOLEAN | no |  |  |
| `expected_outcome` | VARCHAR(32) | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Check constraints: dossier_id IS NOT NULL OR claim_id IS NOT NULL

## `scores`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `company_id` | UUID | no |  | FK -> `companies.id` |
| `as_of` | DATE | no |  |  |
| `model_name` | VARCHAR(64) | no |  |  |
| `model_version` | VARCHAR(64) | no |  |  |
| `raw_probability` | DOUBLE PRECISION | no |  |  |
| `calibrated_probability` | DOUBLE PRECISION | no |  |  |
| `percentile` | DOUBLE PRECISION | yes |  |  |
| `top_shap_contributors` | JSONB | yes |  |  |
| `feature_set_version` | VARCHAR(32) | no |  |  |
| `outcome_spec_hash` | VARCHAR(64) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Indexes: ix_scores_as_of

Unique constraints: (company_id, as_of, model_name, model_version)

## `sessions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `user_id` | UUID | no |  | FK -> `users.id` |
| `session_token_hash` | VARCHAR(128) | no |  |  |
| `csrf_token` | VARCHAR(128) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |
| `expires_at` | TIMESTAMP | no |  |  |
| `last_seen_at` | TIMESTAMP | no | now() |  |
| `rotated_from_session_id` | UUID | yes |  | FK -> `sessions.id` |
| `revoked_at` | TIMESTAMP | yes |  |  |
| `ip` | VARCHAR(64) | yes |  |  |
| `user_agent` | VARCHAR(512) | yes |  |  |

Unique constraints: (session_token_hash)

## `sources`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | VARCHAR(64) | no |  | PK |
| `verdict` | VARCHAR(32) | no |  |  |
| `enabled` | BOOLEAN | no |  |  |
| `rate_limit_seconds` | NUMERIC(6, 2) | yes |  |  |
| `terms_url` | VARCHAR(512) | yes |  |  |
| `robots_status` | TEXT | yes |  |  |
| `synced_at` | TIMESTAMP | no |  |  |

## `taxonomy_versions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `version` | VARCHAR(16) | no |  |  |
| `loaded_at` | TIMESTAMP | no | now() |  |
| `source_file_hash` | VARCHAR(64) | no |  |  |
| `description` | TEXT | yes |  |  |

Unique constraints: (version)

## `tenants`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `name` | VARCHAR(200) | no |  |  |
| `slug` | VARCHAR(100) | no |  |  |
| `is_active` | BOOLEAN | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Unique constraints: (slug)

## `users`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `email` | VARCHAR(320) | no |  |  |
| `password_hash` | VARCHAR(512) | no |  |  |
| `is_active` | BOOLEAN | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Unique constraints: (tenant_id, email)

## `watchlist_items`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `watchlist_id` | UUID | no |  | FK -> `watchlists.id` |
| `company_id` | UUID | no |  | FK -> `companies.id` |
| `added_at` | TIMESTAMP | no | now() |  |

Unique constraints: (watchlist_id, company_id)

## `watchlists`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `user_id` | UUID | no |  | FK -> `users.id` |
| `name` | VARCHAR(200) | no |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

## `webhook_deliveries`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `webhook_id` | UUID | no |  | FK -> `webhooks.id` |
| `alert_id` | UUID | yes |  | FK -> `alerts.id` |
| `payload` | JSONB | no |  |  |
| `signature` | VARCHAR(128) | no |  |  |
| `attempt_count` | INTEGER | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `response_code` | INTEGER | yes |  |  |
| `next_retry_at` | TIMESTAMP | yes |  |  |
| `delivered_at` | TIMESTAMP | yes |  |  |
| `created_at` | TIMESTAMP | no | now() |  |

Check constraints: status::text = ANY (ARRAY['pending'::character varying, 'success'::character varying, 'failed'::character varying]::text[])

## `webhooks`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | UUID | no |  | PK |
| `tenant_id` | UUID | no |  | FK -> `tenants.id` |
| `url` | VARCHAR(2048) | no |  |  |
| `secret_encrypted` | TEXT | no |  |  |
| `is_active` | BOOLEAN | no |  |  |
| `created_by` | UUID | no |  | FK -> `users.id` |
| `created_at` | TIMESTAMP | no | now() |  |
