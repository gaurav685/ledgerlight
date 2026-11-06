# Data dictionary

Generated from the real, live SQLAlchemy model metadata by `scripts/generate_data_dictionary.py` -- never hand-written. 51 real tables, as of this run. Regenerate after any model change; do not hand-edit this file.

## `alert_rules`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `watchlist_id` | CHAR(32) | no |  | FK -> `watchlists.id` |
| `rule_type` | VARCHAR(32) | no |  |  |
| `config` | JSONB | no |  |  |
| `is_active` | BOOLEAN | no | True |  |
| `created_by` | CHAR(32) | no |  | FK -> `users.id` |
| `created_at` | DATETIME | no | now() |  |

Check constraints: rule_type IN ('new_event_type', 'score_percentile_threshold')

## `alerts`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `alert_rule_id` | CHAR(32) | no |  | FK -> `alert_rules.id` |
| `company_id` | CHAR(32) | no |  |  |
| `payload` | JSONB | no |  |  |
| `triggered_at` | DATETIME | no | now() |  |
| `acknowledged_at` | DATETIME | yes |  |  |
| `acknowledged_by` | CHAR(32) | yes |  | FK -> `users.id` |

## `api_keys`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `user_id` | CHAR(32) | no |  | FK -> `users.id` |
| `name` | VARCHAR(200) | no |  |  |
| `key_prefix` | VARCHAR(16) | no |  |  |
| `key_hash` | VARCHAR(128) | no |  | UNIQUE |
| `scopes` | JSONB | no | list |  |
| `expires_at` | DATETIME | yes |  |  |
| `revoked_at` | DATETIME | yes |  |  |
| `last_used_at` | DATETIME | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

Indexes: ix_api_keys_key_prefix

Unique constraints: (key_hash)

## `audit_logs`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `actor_user_id` | CHAR(32) | yes |  | FK -> `users.id` |
| `actor_api_key_id` | CHAR(32) | yes |  | FK -> `api_keys.id` |
| `action` | VARCHAR(100) | no |  |  |
| `target_type` | VARCHAR(64) | yes |  |  |
| `target_id` | VARCHAR(64) | yes |  |  |
| `request_id` | VARCHAR(64) | yes |  |  |
| `ip` | VARCHAR(64) | yes |  |  |
| `extra` | JSONB | no | dict |  |
| `created_at` | DATETIME | no | now() |  |

## `chunks`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `version_id` | CHAR(32) | no |  | FK -> `document_versions.id` |
| `page_number` | INTEGER | no |  |  |
| `char_start` | INTEGER | no |  |  |
| `char_end` | INTEGER | no |  |  |
| `text` | TEXT | no |  |  |
| `chunker_version` | VARCHAR(32) | no |  |  |
| `tsv` | TSVECTOR | yes |  |  |
| `embedding` | VECTOR(384) | yes |  |  |
| `embedding_model_name` | VARCHAR(128) | yes |  |  |
| `embedding_model_version` | VARCHAR(32) | yes |  |  |
| `known_at` | DATETIME | no |  |  |
| `created_at` | DATETIME | no | now() |  |

Indexes: ix_chunks_tsv

Unique constraints: (version_id, page_number, char_start, char_end, chunker_version)

Check constraints: char_end > char_start

## `claims`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `investigation_id` | CHAR(32) | no |  | FK -> `investigations.id` |
| `claim_type` | VARCHAR(16) | no |  |  |
| `payload` | JSONB | no |  |  |
| `evidence` | JSONB | no |  |  |
| `verification_status` | VARCHAR(16) | no | pending |  |
| `verification_checks` | JSONB | no | list |  |
| `created_at` | DATETIME | no | now() |  |

## `companies`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `display_name` | VARCHAR(256) | no |  |  |
| `created_at` | DATETIME | no | now() |  |

## `company_identifiers`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `company_id` | CHAR(32) | no |  | FK -> `companies.id` |
| `identifier_type` | VARCHAR(32) | no |  |  |
| `value` | VARCHAR(64) | no |  |  |
| `valid_from` | DATE | yes |  |  |
| `valid_to` | DATE | yes |  |  |
| `source_version_id` | CHAR(32) | yes |  | FK -> `document_versions.id` |
| `source_price_bar_id` | CHAR(32) | yes |  | FK -> `price_bars.id` |
| `note` | TEXT | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

Indexes: ix_company_identifiers_type_value

## `dead_letters`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `payload_ref` | VARCHAR(512) | no |  |  |
| `stage` | VARCHAR(32) | no |  |  |
| `last_error` | TEXT | no |  |  |
| `attempts` | INTEGER | no | 1 |  |
| `first_failed_at` | DATETIME | no |  |  |
| `resolved_at` | DATETIME | yes |  |  |
| `resolution` | TEXT | yes |  |  |

## `document_pages`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `version_id` | CHAR(32) | no |  | FK -> `document_versions.id` |
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
| `created_at` | DATETIME | no | now() |  |

Unique constraints: (version_id, page_number, extractor_version)

## `document_versions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `document_id` | CHAR(32) | no |  | FK -> `documents.id` |
| `sha256` | VARCHAR(64) | no |  |  |
| `content_sha256` | VARCHAR(64) | yes |  |  |
| `object_key` | VARCHAR(512) | no |  |  |
| `bytes` | BIGINT | no |  |  |
| `mime_type` | VARCHAR(128) | yes |  |  |
| `retrieval_method` | VARCHAR(32) | no |  |  |
| `retrieval_url` | VARCHAR(1024) | no |  |  |
| `http_status` | INTEGER | yes |  |  |
| `retrieved_at` | DATETIME | no |  |  |
| `published_at` | DATETIME | yes |  |  |
| `snapshot_at` | DATETIME | yes |  |  |
| `known_at` | DATETIME | no |  |  |
| `known_at_basis` | VARCHAR(16) | no |  |  |
| `tool_version` | VARCHAR(64) | no |  |  |
| `created_at` | DATETIME | no | now() |  |

Indexes: ix_document_versions_doc_content_sha256, ix_document_versions_sha256

Unique constraints: (document_id, sha256)

## `documents`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `source_id` | VARCHAR(64) | no |  | FK -> `sources.id` |
| `source_key` | VARCHAR(1024) | no |  |  |
| `bse_code` | VARCHAR(32) | yes |  |  |
| `nse_symbol` | VARCHAR(32) | yes |  |  |
| `isin` | VARCHAR(16) | yes |  |  |
| `company_name_raw` | VARCHAR(256) | yes |  |  |
| `document_type` | VARCHAR(64) | no | unknown |  |
| `created_at` | DATETIME | no | now() |  |

Unique constraints: (source_id, source_key)

## `dossiers`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `investigation_id` | CHAR(32) | no |  | FK -> `investigations.id` |
| `version` | INTEGER | no | 1 |  |
| `status` | VARCHAR(16) | no |  |  |
| `sections` | JSONB | no |  |  |
| `claim_id_map` | JSONB | no |  |  |
| `renderer_name` | VARCHAR(64) | no |  |  |
| `renderer_version` | VARCHAR(32) | no |  |  |
| `prompt_version` | VARCHAR(32) | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

Unique constraints: (investigation_id, version)

## `entities`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `entity_type` | VARCHAR(16) | no |  |  |
| `company_id` | CHAR(32) | yes |  | FK -> `companies.id` |
| `display_name` | VARCHAR(256) | no |  |  |
| `created_at` | DATETIME | no | now() |  |

## `entity_identifiers`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `entity_id` | CHAR(32) | no |  | FK -> `entities.id` |
| `identifier_type` | VARCHAR(32) | no |  |  |
| `value` | VARCHAR(64) | no |  |  |
| `evidence_version_id` | CHAR(32) | yes |  | FK -> `document_versions.id` |
| `evidence_page` | INTEGER | yes |  |  |
| `evidence_char_start` | INTEGER | yes |  |  |
| `evidence_char_end` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

## `entity_links`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `mention_id` | CHAR(32) | no |  | FK -> `mentions.id` |
| `entity_id` | CHAR(32) | no |  | FK -> `entities.id` |
| `method` | VARCHAR(32) | no |  |  |
| `score` | FLOAT | no |  |  |
| `status` | VARCHAR(16) | no | active |  |
| `created_at` | DATETIME | no | now() |  |

## `entity_merges`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `source_entity_id` | CHAR(32) | no |  | FK -> `entities.id` |
| `target_entity_id` | CHAR(32) | no |  | FK -> `entities.id` |
| `reason` | TEXT | no |  |  |
| `actor` | VARCHAR(64) | no |  |  |
| `created_at` | DATETIME | no | now() |  |
| `reversed_at` | DATETIME | yes |  |  |
| `reversed_by` | VARCHAR(64) | yes |  |  |

## `event_fields`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `event_id` | CHAR(32) | no |  | FK -> `events.id` |
| `field_name` | VARCHAR(64) | no |  |  |
| `value_json` | JSONB | yes |  |  |
| `normalized_value` | TEXT | yes |  |  |
| `evidence_version_id` | CHAR(32) | no |  | FK -> `document_versions.id` |
| `evidence_page` | INTEGER | no |  |  |
| `evidence_char_start` | INTEGER | no |  |  |
| `evidence_char_end` | INTEGER | no |  |  |
| `extractor_name` | VARCHAR(64) | no |  |  |
| `extractor_version` | VARCHAR(32) | no |  |  |
| `confidence` | FLOAT | no |  |  |
| `validation_status` | VARCHAR(16) | no |  |  |
| `created_at` | DATETIME | no | now() |  |

## `event_types`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `taxonomy_version_id` | CHAR(32) | no |  | FK -> `taxonomy_versions.id` |
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
| `id` | CHAR(32) | no | uuid4 | PK |
| `event_id` | CHAR(32) | no |  | FK -> `events.id` |
| `status` | VARCHAR(16) | no |  |  |
| `reviewer` | VARCHAR(64) | no |  |  |
| `review_task_id` | CHAR(32) | yes |  | FK -> `review_tasks.id` |
| `notes` | TEXT | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

## `events`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `event_type_id` | CHAR(32) | no |  | FK -> `event_types.id` |
| `company_id` | CHAR(32) | yes |  | FK -> `companies.id` |
| `event_time` | DATETIME | yes |  |  |
| `published_at` | DATETIME | yes |  |  |
| `known_at` | DATETIME | no |  |  |
| `severity` | VARCHAR(16) | no |  |  |
| `status` | VARCHAR(16) | no | candidate |  |
| `detector_name` | VARCHAR(64) | no |  |  |
| `detector_version` | VARCHAR(32) | no |  |  |
| `confidence` | FLOAT | no |  |  |
| `supersedes_event_id` | CHAR(32) | yes |  | FK -> `events.id` |
| `created_at` | DATETIME | no | now() |  |

## `experiments`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `config_json` | JSONB | no |  |  |
| `data_snapshot_hashes` | JSONB | no |  |  |
| `git_sha` | VARCHAR(40) | no |  |  |
| `metrics_json` | JSONB | no |  |  |
| `artifacts_uri` | VARCHAR(512) | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

## `feature_definitions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `name` | VARCHAR(64) | no |  |  |
| `version` | VARCHAR(32) | no |  |  |
| `description` | TEXT | no |  |  |
| `inputs` | JSONB | no |  |  |
| `provenance_tier` | VARCHAR(16) | no |  |  |
| `as_of_semantics` | TEXT | no |  |  |
| `lookback_days` | INTEGER | yes |  |  |
| `track` | VARCHAR(16) | no |  |  |
| `created_at` | DATETIME | no | now() |  |

Unique constraints: (name, version)

## `feature_snapshots`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `company_id` | CHAR(32) | no |  | FK -> `companies.id` |
| `as_of` | DATE | no |  |  |
| `feature_set_version` | VARCHAR(32) | no |  |  |
| `values` | JSONB | no |  |  |
| `max_input_known_at` | DATETIME | yes |  |  |
| `data_quality_flags` | JSONB | no | list |  |
| `created_at` | DATETIME | no | now() |  |

Indexes: ix_feature_snapshots_as_of

Unique constraints: (company_id, as_of, feature_set_version)

## `filings`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `version_id` | CHAR(32) | no |  | FK -> `document_versions.id` |
| `company_id` | CHAR(32) | no |  | FK -> `companies.id` |
| `link_method` | VARCHAR(32) | no |  |  |
| `confidence` | FLOAT | no |  |  |
| `created_at` | DATETIME | no | now() |  |

Unique constraints: (version_id, company_id)

## `identifier_window_corrections`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `identifier_id` | CHAR(32) | yes |  | FK -> `company_identifiers.id` |
| `identifier_type` | VARCHAR(32) | no |  |  |
| `value` | VARCHAR(64) | no |  |  |
| `old_valid_from` | DATE | no |  |  |
| `new_valid_from` | DATE | no |  |  |
| `reason` | TEXT | no |  |  |
| `script_name` | VARCHAR(128) | no |  |  |
| `script_version` | VARCHAR(32) | no |  |  |
| `applied_at` | DATETIME | no | now() |  |

## `ingestion_runs`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `source_id` | VARCHAR(64) | yes |  | FK -> `sources.id` |
| `stage` | VARCHAR(32) | no |  |  |
| `status` | VARCHAR(16) | no | running |  |
| `started_at` | DATETIME | no |  |  |
| `finished_at` | DATETIME | yes |  |  |
| `fetched` | INTEGER | no | 0 |  |
| `new` | INTEGER | no | 0 |  |
| `unchanged` | INTEGER | no | 0 |  |
| `failed` | INTEGER | no | 0 |  |
| `ocr_pages` | INTEGER | no | 0 |  |
| `rows_parsed` | INTEGER | no | 0 |  |
| `rows_quarantined` | INTEGER | no | 0 |  |

## `investigation_steps`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `investigation_id` | CHAR(32) | no |  | FK -> `investigations.id` |
| `step_no` | INTEGER | no |  |  |
| `state` | VARCHAR(16) | no |  |  |
| `tool_calls` | JSONB | no | list |  |
| `outputs` | JSONB | no | dict |  |
| `started_at` | DATETIME | no | now() |  |
| `finished_at` | DATETIME | yes |  |  |

Unique constraints: (investigation_id, step_no)

## `investigations`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `company_id` | CHAR(32) | no |  | FK -> `companies.id` |
| `as_of` | DATE | no |  |  |
| `requested_by` | VARCHAR(64) | no |  |  |
| `tenant_id` | CHAR(32) | yes |  |  |
| `state` | VARCHAR(16) | no | PLAN |  |
| `final_status` | VARCHAR(16) | yes |  |  |
| `failure_reason` | TEXT | yes |  |  |
| `budget_config` | JSONB | no |  |  |
| `usage` | JSONB | no |  |  |
| `started_at` | DATETIME | no | now() |  |
| `finished_at` | DATETIME | yes |  |  |

## `label_item_fields`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `label_item_id` | CHAR(32) | no |  | FK -> `label_items.id` |
| `field_name` | VARCHAR(64) | no |  |  |
| `proposed_value_json` | JSONB | yes |  |  |
| `proposed_char_start` | INTEGER | yes |  |  |
| `proposed_char_end` | INTEGER | yes |  |  |
| `review_status` | VARCHAR(16) | no | pending |  |
| `corrected_value_json` | JSONB | yes |  |  |
| `reviewer` | VARCHAR(64) | yes |  |  |
| `reviewed_at` | DATETIME | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

## `label_items`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `version_id` | CHAR(32) | no |  | FK -> `document_versions.id` |
| `page_number` | INTEGER | no |  |  |
| `chunk_id` | CHAR(32) | yes |  | FK -> `chunks.id` |
| `proposed_event_type_code` | VARCHAR(32) | no |  |  |
| `proposed_confidence` | FLOAT | yes |  |  |
| `proposer_name` | VARCHAR(64) | no |  |  |
| `proposer_version` | VARCHAR(32) | no |  |  |
| `label_source` | VARCHAR(32) | no | ai_assisted_unreviewed |  |
| `review_status` | VARCHAR(16) | no | pending |  |
| `corrected_event_type_code` | VARCHAR(32) | yes |  |  |
| `reviewer` | VARCHAR(64) | yes |  |  |
| `reviewed_at` | DATETIME | yes |  |  |
| `review_note` | TEXT | yes |  |  |
| `split` | VARCHAR(16) | yes |  |  |
| `company_id` | CHAR(32) | yes |  | FK -> `companies.id` |
| `created_at` | DATETIME | no | now() |  |

## `memberships`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `user_id` | CHAR(32) | no |  | FK -> `users.id` |
| `role` | VARCHAR(16) | no |  |  |
| `status` | VARCHAR(16) | no | active |  |
| `invited_by` | CHAR(32) | yes |  | FK -> `users.id` |
| `created_at` | DATETIME | no | now() |  |

Unique constraints: (tenant_id, user_id)

Check constraints: status IN ('invited', 'active', 'revoked'), role IN ('viewer', 'analyst', 'reviewer', 'tenant_admin')

## `mentions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `version_id` | CHAR(32) | no |  | FK -> `document_versions.id` |
| `page_number` | INTEGER | no |  |  |
| `char_start` | INTEGER | no |  |  |
| `char_end` | INTEGER | no |  |  |
| `surface_text` | VARCHAR(512) | no |  |  |
| `guessed_entity_type` | VARCHAR(16) | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

Unique constraints: (version_id, page_number, char_start, char_end)

## `model_registry`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `model_name` | VARCHAR(64) | no |  |  |
| `model_version` | VARCHAR(64) | no |  |  |
| `artifact_hash` | VARCHAR(64) | yes |  |  |
| `training_data_snapshot_hash` | VARCHAR(64) | yes |  |  |
| `params_json` | JSONB | yes |  |  |
| `metrics_json` | JSONB | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

Unique constraints: (model_name, model_version)

## `outcomes`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `event_id` | CHAR(32) | no |  | FK -> `events.id` |
| `outcome_type` | VARCHAR(64) | yes |  |  |
| `outcome_value` | JSONB | yes |  |  |
| `observed_at` | DATETIME | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

## `price_bars`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `source_id` | VARCHAR(64) | no |  | FK -> `sources.id` |
| `version_id` | CHAR(32) | no |  | FK -> `document_versions.id` |
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
| `created_at` | DATETIME | no | now() |  |
| `updated_at` | DATETIME | no | now() |  |

Indexes: ix_price_bars_symbol, ix_price_bars_trade_date

Unique constraints: (source_id, trade_date, symbol, series)

## `processing_attempts`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `run_id` | CHAR(32) | yes |  | FK -> `ingestion_runs.id` |
| `version_id` | CHAR(32) | yes |  | FK -> `document_versions.id` |
| `stage` | VARCHAR(32) | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `error_class` | VARCHAR(32) | yes |  |  |
| `error_message` | TEXT | yes |  |  |
| `duration_ms` | INTEGER | no | 0 |  |
| `attempt_number` | INTEGER | no | 1 |  |
| `created_at` | DATETIME | no | now() |  |

## `review_assignments`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `review_task_id` | CHAR(32) | no |  |  |
| `assignee_user_id` | CHAR(32) | no |  | FK -> `users.id` |
| `assigned_by` | CHAR(32) | no |  | FK -> `users.id` |
| `status` | VARCHAR(16) | no | open |  |
| `assigned_at` | DATETIME | no | now() |  |

Check constraints: status IN ('open', 'in_progress', 'done')

## `review_decisions_audit`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `review_task_id` | CHAR(32) | no |  | FK -> `review_tasks.id` |
| `actor` | VARCHAR(64) | no |  |  |
| `action` | VARCHAR(32) | no |  |  |
| `before` | JSONB | yes |  |  |
| `after` | JSONB | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

## `review_queue`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `item_type` | VARCHAR(32) | no |  |  |
| `reference_id` | CHAR(32) | no |  |  |
| `reason_code` | VARCHAR(64) | no |  |  |
| `priority` | INTEGER | no | 3 |  |
| `status` | VARCHAR(16) | no | open |  |
| `resolution` | TEXT | yes |  |  |
| `reviewer` | VARCHAR(64) | yes |  |  |
| `created_at` | DATETIME | no | now() |  |
| `resolved_at` | DATETIME | yes |  |  |

## `review_tasks`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `dossier_id` | CHAR(32) | yes |  | FK -> `dossiers.id` |
| `claim_id` | CHAR(32) | yes |  | FK -> `claims.id` |
| `reason_code` | VARCHAR(32) | no |  |  |
| `priority` | INTEGER | no | 0 |  |
| `status` | VARCHAR(16) | no | open |  |
| `assignee` | VARCHAR(64) | yes |  |  |
| `decision` | VARCHAR(32) | yes |  |  |
| `decision_notes` | TEXT | yes |  |  |
| `decided_at` | DATETIME | yes |  |  |
| `seeded_qc` | BOOLEAN | no | False |  |
| `expected_outcome` | VARCHAR(32) | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

Check constraints: dossier_id IS NOT NULL OR claim_id IS NOT NULL

## `scores`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `company_id` | CHAR(32) | no |  | FK -> `companies.id` |
| `as_of` | DATE | no |  |  |
| `model_name` | VARCHAR(64) | no |  |  |
| `model_version` | VARCHAR(64) | no |  |  |
| `raw_probability` | FLOAT | no |  |  |
| `calibrated_probability` | FLOAT | no |  |  |
| `percentile` | FLOAT | yes |  |  |
| `top_shap_contributors` | JSONB | yes |  |  |
| `feature_set_version` | VARCHAR(32) | no |  |  |
| `outcome_spec_hash` | VARCHAR(64) | no |  |  |
| `created_at` | DATETIME | no | now() |  |

Indexes: ix_scores_as_of

Unique constraints: (company_id, as_of, model_name, model_version)

## `sessions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `user_id` | CHAR(32) | no |  | FK -> `users.id` |
| `session_token_hash` | VARCHAR(128) | no |  | UNIQUE |
| `csrf_token` | VARCHAR(128) | no |  |  |
| `created_at` | DATETIME | no | now() |  |
| `expires_at` | DATETIME | no |  |  |
| `last_seen_at` | DATETIME | no | now() |  |
| `rotated_from_session_id` | CHAR(32) | yes |  | FK -> `sessions.id` |
| `revoked_at` | DATETIME | yes |  |  |
| `ip` | VARCHAR(64) | yes |  |  |
| `user_agent` | VARCHAR(512) | yes |  |  |

Unique constraints: (session_token_hash)

## `sources`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | VARCHAR(64) | no |  | PK |
| `verdict` | VARCHAR(32) | no |  |  |
| `enabled` | BOOLEAN | no | False |  |
| `rate_limit_seconds` | NUMERIC(6, 2) | yes |  |  |
| `terms_url` | VARCHAR(512) | yes |  |  |
| `robots_status` | TEXT | yes |  |  |
| `synced_at` | DATETIME | no |  |  |

## `taxonomy_versions`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `version` | VARCHAR(16) | no |  | UNIQUE |
| `loaded_at` | DATETIME | no | now() |  |
| `source_file_hash` | VARCHAR(64) | no |  |  |
| `description` | TEXT | yes |  |  |

Unique constraints: (version)

## `tenants`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `name` | VARCHAR(200) | no |  |  |
| `slug` | VARCHAR(100) | no |  | UNIQUE |
| `is_active` | BOOLEAN | no | True |  |
| `created_at` | DATETIME | no | now() |  |

Unique constraints: (slug)

## `users`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `email` | VARCHAR(320) | no |  |  |
| `password_hash` | VARCHAR(512) | no |  |  |
| `is_active` | BOOLEAN | no | True |  |
| `created_at` | DATETIME | no | now() |  |

Unique constraints: (tenant_id, email)

## `watchlist_items`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `watchlist_id` | CHAR(32) | no |  | FK -> `watchlists.id` |
| `company_id` | CHAR(32) | no |  |  |
| `added_at` | DATETIME | no | now() |  |

Unique constraints: (watchlist_id, company_id)

## `watchlists`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `user_id` | CHAR(32) | no |  | FK -> `users.id` |
| `name` | VARCHAR(200) | no |  |  |
| `created_at` | DATETIME | no | now() |  |

## `webhook_deliveries`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `webhook_id` | CHAR(32) | no |  | FK -> `webhooks.id` |
| `alert_id` | CHAR(32) | yes |  | FK -> `alerts.id` |
| `payload` | JSONB | no |  |  |
| `signature` | VARCHAR(128) | no |  |  |
| `attempt_count` | INTEGER | no | 0 |  |
| `status` | VARCHAR(16) | no | pending |  |
| `response_code` | INTEGER | yes |  |  |
| `next_retry_at` | DATETIME | yes |  |  |
| `delivered_at` | DATETIME | yes |  |  |
| `created_at` | DATETIME | no | now() |  |

Check constraints: status IN ('pending', 'success', 'failed')

## `webhooks`

| column | type | nullable | default | key |
|---|---|---|---|---|
| `id` | CHAR(32) | no | uuid4 | PK |
| `tenant_id` | CHAR(32) | no |  | FK -> `tenants.id` |
| `url` | VARCHAR(2048) | no |  |  |
| `secret_encrypted` | TEXT | no |  |  |
| `is_active` | BOOLEAN | no | True |  |
| `created_by` | CHAR(32) | no |  | FK -> `users.id` |
| `created_at` | DATETIME | no | now() |  |
