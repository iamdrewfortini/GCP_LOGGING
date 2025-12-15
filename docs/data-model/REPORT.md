# BigQuery Log Schema Normalization Report

**Date:** 2025-12-15
**Project:** diatonic-ai-gcp
**Author:** Data Model & Observability Execution Agent

---

## Executive Summary

This report documents the inventory, analysis, and normalization plan for BigQuery log datasets in the Glass Pane observability platform. The system already has a well-structured ETL pipeline populating a `master_logs` table with 70+ columns. This plan enhances it with a Universal Data Envelope for cross-dataset compatibility while preserving backward compatibility.

---

## 1. Dataset/Table/View Inventory

### 1.1 Datasets Overview

| Dataset | Location | Tables | Views | Purpose | Status |
|---------|----------|--------|-------|---------|--------|
| `central_logging_v1` | US | 17 | 1 | Primary log storage | **Active** |
| `org_observability` | US | 0 | 1 | Canonical views | **Active** |
| `org_logs` | US | 5 | 0 | Date-sharded sink overflow | Legacy |
| `org_agent` | US | 0 | 0 | Agent events (planned) | Empty |
| `org_finops` | US | 0 | 0 | FinOps metrics (planned) | Empty |
| `firebase_messaging` | me-central1 | ? | 0 | FCM analytics | Separate region |

### 1.2 central_logging_v1 Tables

| Table | Rows | Size | Partitioning | Clustering | Writer |
|-------|------|------|--------------|------------|--------|
| `master_logs` | 56,580 | 131MB | `log_date` (DAY) | `severity, service_name, resource_type` | ETL Pipeline |
| `cloudaudit_googleapis_com_data_access` | 27,230 | 82MB | `timestamp` (DAY) | - | GCP Sink |
| `cloudbuild` | 25,703 | 10MB | `timestamp` (DAY) | - | GCP Sink |
| `run_googleapis_com_requests` | 1,919 | 2MB | `timestamp` (DAY) | - | GCP Sink |
| `cloudaudit_googleapis_com_activity` | 1,095 | 11MB | `timestamp` (DAY) | - | GCP Sink |
| `run_googleapis_com_varlog_system` | 302 | 188KB | `timestamp` (DAY) | - | GCP Sink |
| `cloudaudit_googleapis_com_system_event` | 230 | 963KB | `timestamp` (DAY) | - | GCP Sink |
| `run_googleapis_com_stderr` | 46 | 197KB | `timestamp` (DAY) | - | GCP Sink |
| `log_streams` | 18 | 8KB | - | - | ETL Pipeline |
| `cloudfunctions_googleapis_com_cloud_functions` | 12 | 8KB | `timestamp` (DAY) | - | GCP Sink |
| `clouderrorreporting_googleapis_com_insights` | 7 | 34KB | `timestamp` (DAY) | - | GCP Sink |
| `glass_pane_test` | 5 | 823B | `timestamp` (DAY) | - | Test |
| `bigquerydatatransfer_googleapis_com_transfer_config` | 3 | 979B | `timestamp` (DAY) | - | GCP Sink |
| `run_googleapis_com_stdout` | 3 | 272B | `timestamp` (DAY) | - | GCP Sink |
| `cloudscheduler_googleapis_com_executions` | 2 | 1KB | `timestamp` (DAY) | - | GCP Sink |
| `syslog` | 2 | 146B | `timestamp` (DAY) | - | GCP Sink |
| `etl_jobs` | 0 | 0B | - | - | ETL Pipeline |

### 1.3 Existing Views

| View | Dataset | Schema Columns | Purpose |
|------|---------|----------------|---------|
| `view_canonical_logs` | central_logging_v1 | 10 | Legacy: UNION of raw tables |
| `logs_canonical_v2` | org_observability | 13 | v2: Enhanced UNION with more fields |

### 1.4 org_logs Tables (Date-Sharded)

| Table | Rows | Purpose |
|-------|------|---------|
| `cloudaudit_googleapis_com_activity_20251213` | 21 | Spillover from different sink |
| `cloudaudit_googleapis_com_data_access_20251215` | 1 | Spillover from different sink |
| `logging_googleapis_com_sink_error_*` | 0-1 | Sink error logs |

---

## 2. Current Schema Analysis

### 2.1 master_logs Schema (70 columns)

The current `master_logs` table has a **comprehensive flat schema**:

**Identifiers:**
- `log_id` (STRING, REQUIRED) - UUID primary key
- `insert_id` (STRING) - Cloud Logging insert ID

**Timestamps:**
- `event_timestamp` (TIMESTAMP, REQUIRED) - When event occurred
- `receive_timestamp` (TIMESTAMP) - When received by Cloud Logging
- `etl_timestamp` (TIMESTAMP, REQUIRED) - When processed by ETL
- `log_date` (DATE, REQUIRED) - Partition key

**Classification:**
- `severity` (STRING, REQUIRED) - DEFAULT/DEBUG/INFO/NOTICE/WARNING/ERROR/CRITICAL/ALERT/EMERGENCY
- `severity_level` (INTEGER) - Numeric severity (0-800)
- `log_type` (STRING, REQUIRED) - application/audit/request/build/error/system

**Source Tracking:**
- `source_dataset` (STRING, REQUIRED)
- `source_table` (STRING, REQUIRED)
- `source_log_name` (STRING)
- `stream_id` (STRING, REQUIRED)
- `stream_direction` (STRING)
- `stream_flow` (STRING)
- `stream_coordinates` (RECORD) - region, zone, project, organization

**Resource:**
- `resource_type` (STRING)
- `resource_project` (STRING)
- `resource_name` (STRING)
- `resource_location` (STRING)
- `resource_labels` (JSON)

**Service:**
- `service_name` (STRING)
- `service_version` (STRING)
- `service_method` (STRING)

**Content:**
- `message` (STRING) - Unified message
- `message_summary` (STRING)
- `message_category` (STRING)
- `text_payload` (STRING)
- `json_payload` (JSON)
- `proto_payload` (JSON)
- `audit_payload` (JSON)

**HTTP Context:**
- `http_method`, `http_url`, `http_status`, `http_latency_ms`
- `http_user_agent`, `http_remote_ip`
- `http_request_size`, `http_response_size`
- `http_full` (JSON)

**Tracing:**
- `trace_id`, `span_id`, `trace_sampled`, `parent_span_id`
- `operation_id`, `operation_producer`, `operation_first`, `operation_last`

**Error Context:**
- `error_message`, `error_code`, `error_stack_trace`, `error_group_id`

**Principal (Audit):**
- `principal_email`, `principal_type`, `caller_ip`, `caller_network`

**Labels:**
- `labels` (JSON), `user_labels` (JSON), `system_labels` (JSON)

**Flags:**
- `is_error`, `is_audit`, `is_request`, `has_trace` (BOOLEAN)

**ETL Metadata:**
- `etl_version`, `etl_batch_id`, `etl_status`, `etl_enrichments`
- `cluster_key` (STRING) - Composite key for clustering

### 2.2 Gap Analysis vs Universal Data Envelope

| TOON Envelope Field | Current Status | Gap |
|---------------------|----------------|-----|
| `schema_version` | Missing | **Add** |
| `event_id` | `log_id` exists | Map |
| `event_type` | `log_type` exists | Rename in view |
| `event_source` | `source_table` exists | Map |
| `event_ts` | `event_timestamp` exists | Map |
| `ingest_ts` | `etl_timestamp` exists | Map |
| `project_id` | `resource_project` exists | Map |
| `environment` | Missing | **Add** (derive from labels) |
| `region/zone` | In `stream_coordinates` | Map |
| `service` struct | Flat columns exist | Wrap in struct |
| `trace` struct | Flat columns exist | Wrap in struct |
| `actor` struct | Partial (`principal_*`) | **Enhance** |
| `location` struct | Missing | **Add** (optional) |
| `lifecycle` struct | Missing | **Add** |
| `versioning` struct | Partial (`etl_version`) | Enhance |
| `labels/tags` | `labels` JSON exists | Map |
| `correlation` struct | Partial (`trace_id`, `span_id`) | **Enhance** |
| `privacy` struct | Missing | **Add** |
| `route` struct | HTTP columns exist | Wrap in struct |
| `resource` struct | Flat columns exist | Wrap in struct |
| `payload_refs` struct | JSON columns exist | Map |

---

## 3. Naming Standard & Mapping

### 3.1 Dataset Naming Convention

| Current | Canonical | Purpose |
|---------|-----------|---------|
| `central_logging_v1` | `org_logs_raw` | Raw sink tables (rename optional) |
| *(new)* | `org_logs_norm` | Normalized views + tables |
| `org_observability` | `org_observability` | Keep (observability views) |
| `org_logs` | `org_logs_overflow` | Date-sharded overflow (deprecate) |
| `org_agent` | `org_agent` | Agent/tool events |
| `org_finops` | `org_finops` | Cost/billing metrics |

### 3.2 Table Naming Pattern

```
{domain}_{source}_{event}_{granularity}_{version}
```

| Current | Canonical Name |
|---------|----------------|
| `master_logs` | `logs_gcp_all_entry_stream_v1` |
| `cloudaudit_googleapis_com_activity` | `logs_gcp_audit_activity_stream_v1` |
| `run_googleapis_com_requests` | `logs_gcp_cloudrun_request_stream_v1` |
| `cloudbuild` | `logs_gcp_build_step_stream_v1` |
| `log_streams` | `meta_etl_stream_config_v1` |
| `etl_jobs` | `meta_etl_job_status_v1` |

### 3.3 View Naming Pattern

```
v_{domain}_{scope}_{entity}_canon
```

| View Name | Purpose |
|-----------|---------|
| `v_logs_all_entry_canon` | All logs with Universal Envelope |
| `v_logs_errors_canon` | Errors only (severity >= ERROR) |
| `v_logs_service_canon` | Service-level aggregates |
| `v_agent_tool_event_canon` | Agent tool invocations |
| `v_observability_metrics_canon` | Unified metrics view |

---

## 4. Universal Data Envelope Implementation

### 4.1 Approach: Views Over Rewrite

Given the hard requirements (`prefer_views_over_rewrite: true`), we will:

1. **Keep `master_logs` as-is** - No schema changes to avoid breaking ETL
2. **Create canonical views** that project existing columns into the Universal Envelope STRUCT
3. **Add missing columns incrementally** via ALTER TABLE for truly missing data
4. **App queries will use views** that expose the canonical interface

### 4.2 Universal Envelope STRUCT Definition

```sql
STRUCT<
  schema_version STRING,          -- "1.0.0"
  event_id STRING,                -- log_id
  event_type STRING,              -- log_type
  event_source STRING,            -- source_table
  event_ts TIMESTAMP,             -- event_timestamp
  ingest_ts TIMESTAMP,            -- etl_timestamp
  project_id STRING,              -- resource_project
  environment STRING,             -- derived: "prod"/"staging"/"dev"
  region STRING,                  -- stream_coordinates.region
  zone STRING,                    -- stream_coordinates.zone

  service STRUCT<
    name STRING,                  -- service_name
    revision STRING,              -- service_version
    instance_id STRING,           -- from resource_labels
    runtime STRING                -- derived from resource_type
  >,

  trace STRUCT<
    trace_id STRING,              -- trace_id
    span_id STRING,               -- span_id
    sampled BOOL                  -- trace_sampled
  >,

  actor STRUCT<
    user_id STRING,               -- principal_email
    tenant_id STRING,             -- from labels
    org_id STRING,                -- from stream_coordinates.organization
    ip STRING,                    -- caller_ip OR http_remote_ip
    user_agent STRING             -- http_user_agent
  >,

  lifecycle STRUCT<
    created_at TIMESTAMP,         -- event_timestamp
    updated_at TIMESTAMP,         -- NULL (immutable logs)
    deleted_at TIMESTAMP,         -- NULL
    is_deleted BOOL               -- FALSE
  >,

  versioning STRUCT<
    record_version INT64,         -- 1 (first version)
    source_version STRING,        -- etl_version
    schema_hash STRING            -- MD5 of schema
  >,

  labels ARRAY<STRUCT<k STRING, v STRING>>,  -- from labels JSON
  tags ARRAY<STRING>,             -- from user_labels

  correlation STRUCT<
    request_id STRING,            -- operation_id
    session_id STRING,            -- from labels
    conversation_id STRING,       -- from labels
    job_id STRING,                -- from resource_labels
    parent_event_id STRING        -- from parent_span_id
  >,

  privacy STRUCT<
    pii_risk STRING,              -- "none"/"low"/"moderate"/"high"
    redaction_state STRING,       -- "none"/"partial"/"full"
    retention_class STRING        -- "standard"/"audit"
  >
> AS universal_envelope
```

### 4.3 Canonical Column Set for Views

The canonical view will expose both:
- **Flat columns** for backward compatibility
- **Universal Envelope STRUCT** for new consumers

```sql
-- Core identifiers
log_id, insert_id,

-- Universal Envelope
universal_envelope,

-- Timestamps (flat for filtering)
event_timestamp, receive_timestamp, etl_timestamp, log_date,

-- Classification (flat for clustering)
severity, severity_level, log_type,

-- Source (flat for filtering)
source_table, stream_id, service_name,

-- Content
message, message_summary,
text_payload, json_payload, proto_payload,

-- HTTP (for request logs)
http_method, http_url, http_status, http_latency_ms,

-- Trace (flat for join/filter)
trace_id, span_id, parent_span_id,

-- Error context
is_error, error_message, error_code,

-- Flags
is_audit, is_request, has_trace
```

---

## 5. Performance Considerations

### 5.1 Partitioning Strategy

| Table/View | Partition Column | Granularity | Rationale |
|------------|------------------|-------------|-----------|
| `master_logs` | `log_date` | DAY | Time-range queries dominant |
| Raw sink tables | `timestamp` | DAY | GCP default |
| Canonical views | Inherits from `master_logs` | DAY | Partition pruning works |

### 5.2 Clustering Strategy

| Table | Cluster Columns | Query Patterns Optimized |
|-------|-----------------|--------------------------|
| `master_logs` | `severity, service_name, resource_type` | Filter by severity → service |
| Canonical views | N/A (views) | Pushed to base table |

**Recommended clustering order** (based on cardinality and query frequency):
1. `severity` - Low cardinality (9 values), frequent filter
2. `service_name` - Medium cardinality, frequent filter
3. `resource_type` - Medium cardinality, occasional filter
4. `trace_id` - High cardinality, trace correlation queries

### 5.3 Query Pagination Targets

| Page Size | Use Case | Expected Latency |
|-----------|----------|------------------|
| 50 | UI list view | < 500ms |
| 100 | Default pagination | < 1s |
| 240 | Dashboard refresh | < 2s |
| 500 | Bulk export | < 5s |
| 1000 | Agent context | < 10s |

**Key optimizations:**
- Always include partition filter (`log_date BETWEEN ...`)
- Use clustered columns in WHERE clause
- Avoid `SELECT *` - use explicit column list
- Use parameterized queries for caching

---

## 6. Schema Version Policy

### 6.1 Version Numbering

```
MAJOR.MINOR.PATCH

- MAJOR: Breaking changes (new table suffix required)
- MINOR: Additive changes (new columns, non-breaking)
- PATCH: Bug fixes, documentation
```

### 6.2 Change Management Rules

| Change Type | Action | Example |
|-------------|--------|---------|
| Add nullable column | ALTER TABLE ADD COLUMN | Add `privacy` struct |
| Add required column | New table version (_v2) | N/A (avoid) |
| Remove column | Never (soft deprecate) | Mark in docs |
| Rename column | View alias only | `log_type AS event_type` |
| Change type | New table version | N/A (avoid) |

### 6.3 Current Schema Versions

| Component | Version | Last Updated |
|-----------|---------|--------------|
| `master_logs` schema | 1.0.0 | 2025-12-15 |
| ETL pipeline | 1.0.0 | 2025-12-15 |
| `v_logs_all_entry_canon` | 1.0.0 | (new) |
| Universal Envelope spec | 1.0.0 | 2025-12-15 |

---

## 7. Service Writer/Reader Matrix

### 7.1 Writers

| Service | Writes To | Method | Data Type |
|---------|-----------|--------|-----------|
| GCP Cloud Logging Sink | `cloudaudit_*`, `run_*`, etc. | Streaming | Raw logs |
| ETL Pipeline (`src/etl/`) | `master_logs`, `log_streams`, `etl_jobs` | Batch insert | Normalized |
| log-processor (Cloud Function) | Pub/Sub only | N/A | Alerts |
| generate-log-embedding | Qdrant | N/A | Embeddings |
| glass-pane-agent | Firestore | Sessions | Chat history |

### 7.2 Readers

| Service | Reads From | Access Pattern |
|---------|------------|----------------|
| Glass Pane API (`src/api/`) | `master_logs` via `CanonicalQueryBuilder` | Paginated, filtered |
| Glass Pane Agent | `master_logs` (via tools) | Context retrieval |
| Frontend | API only | N/A |
| ETL Pipeline | Raw sink tables | Full scan per stream |

---

## 8. Recommendations

### 8.1 Immediate Actions (No Breaking Changes)

1. **Create `org_logs_norm` dataset** for canonical views
2. **Create `v_logs_all_entry_canon` view** with Universal Envelope projection
3. **Create `v_logs_errors_canon` view** for error-specific queries
4. **Update `CanonicalQueryBuilder`** to optionally use canonical views

### 8.2 Short-term Enhancements

1. **Add columns to `master_logs`:**
   - `schema_version` (STRING)
   - `environment` (STRING)
   - `correlation_request_id` (STRING)
   - `privacy_pii_risk` (STRING)

2. **Update ETL normalizer** to populate new columns

3. **Create `org_agent.tool_invocations` table** for agent events

### 8.3 Long-term Considerations

1. **Deprecate `org_logs` dataset** (date-sharded tables)
2. **Migrate `view_canonical_logs`** consumers to canonical views
3. **Implement privacy classification** in ETL (PII detection)
4. **Add geographic enrichment** (IP to location)

---

## Appendix A: Example Queries

### A.1 Query with Universal Envelope

```sql
SELECT
  universal_envelope.event_id,
  universal_envelope.event_ts,
  universal_envelope.service.name,
  universal_envelope.trace.trace_id,
  universal_envelope.actor.user_id,
  message
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date = CURRENT_DATE()
  AND universal_envelope.service.name = 'glass-pane'
  AND severity IN ('ERROR', 'CRITICAL')
ORDER BY universal_envelope.event_ts DESC
LIMIT 100
```

### A.2 Correlation Query (Request → Logs)

```sql
SELECT
  l.universal_envelope.event_ts,
  l.severity,
  l.message
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon` l
WHERE log_date = CURRENT_DATE()
  AND l.trace_id = 'abc123def456'
ORDER BY l.universal_envelope.event_ts
```

### A.3 Service Health Dashboard

```sql
SELECT
  universal_envelope.service.name,
  COUNTIF(severity IN ('ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY')) as errors,
  COUNTIF(severity = 'WARNING') as warnings,
  COUNT(*) as total,
  AVG(http_latency_ms) as avg_latency_ms
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
GROUP BY 1
ORDER BY errors DESC
```

---

## Appendix B: Data Dictionary

See `BIGQUERY_DDL.sql` for complete column definitions.
