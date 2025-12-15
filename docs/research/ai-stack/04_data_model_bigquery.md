# BigQuery Data Model

**Date:** 2025-12-15
**Goal:** Schema design for long-term analytics and audit logs.

## 1. Dataset Layout

- **Project:** `glass_config.logs_project_id`
- **Dataset:** `glass_logging_v2` (or similar)

## 2. Table: `chat_events`

This is the primary append-only log for all system activity.

| Field Name | Type | Mode | Description |
| :--- | :--- | :--- | :--- |
| `event_id` | STRING | REQUIRED | UUIDv4 |
| `event_timestamp` | TIMESTAMP | REQUIRED | Partition Key |
| `session_id` | STRING | REQUIRED | Cluster Key |
| `user_id` | STRING | REQUIRED | Cluster Key |
| `event_type` | STRING | REQUIRED | `message_sent`, `tool_start`, `tool_end`, `error` |
| `content` | JSON | NULLABLE | The payload (message text, tool args) |
| `metadata` | JSON | NULLABLE | Latency, tokens, cost estimate |
| `client_info` | JSON | NULLABLE | User-Agent, IP (redacted), Locale |

**Partitioning:** By Day (`event_timestamp`).
**Clustering:** `session_id`, `user_id`, `event_type`.
**Retention:** 365 Days (Partition Expiration).

## 3. Table: `tool_executions` (Derived View or Materialized)

Useful for "Most used tools" or "Slowest tools" analytics.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `execution_id` | STRING | Unique ID |
| `tool_name` | STRING | e.g., `bq_list_tables` |
| `start_time` | TIMESTAMP | |
| `end_time` | TIMESTAMP | |
| `duration_ms` | INT64 | |
| `status` | STRING | `success`, `failure` |
| `error_message` | STRING | |
| `bytes_billed` | INT64 | For BQ queries run by the tool |

## 4. Table: `repo_snapshots`

Stores metadata about indexed repository states.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `commit_hash` | STRING | |
| `repo_url` | STRING | |
| `indexed_at` | TIMESTAMP | |
| `file_count` | INT64 | |
| `total_tokens` | INT64 | |
| `vector_index_path` | STRING | GCS path to index artifacts |

## 5. Cost Controls

- **Table Expiration:** Set `default_partition_expiration_ms` on the dataset (e.g., 1 year).
- **Billing Cap:** This is harder in BQ, but we enforce `max_bytes_billed` on all *queries* run by the Agent against these tables.
