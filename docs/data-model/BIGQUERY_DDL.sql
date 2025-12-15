-- ============================================================================
-- BigQuery DDL for Universal Data Envelope Implementation
-- Project: diatonic-ai-gcp
-- Date: 2025-12-15
-- Version: 1.0.0
-- ============================================================================

-- ============================================================================
-- SECTION 1: Dataset Creation
-- ============================================================================

-- Create normalized logs dataset for canonical views
CREATE SCHEMA IF NOT EXISTS `diatonic-ai-gcp.org_logs_norm`
OPTIONS (
  description = 'Normalized log views with Universal Data Envelope',
  labels = [('team', 'observability'), ('env', 'production')]
);

-- ============================================================================
-- SECTION 2: Schema Additions to master_logs (Non-Breaking)
-- ============================================================================

-- Add missing columns for Universal Envelope support
-- These are additive changes - no breaking queries

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS schema_version STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS environment STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS correlation_request_id STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS correlation_session_id STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS correlation_conversation_id STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS privacy_pii_risk STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS privacy_redaction_state STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS privacy_retention_class STRING;

-- ============================================================================
-- SECTION 3: Helper Functions (UDFs)
-- ============================================================================

-- UDF: Parse labels JSON into ARRAY<STRUCT<k, v>>
CREATE OR REPLACE FUNCTION `diatonic-ai-gcp.org_logs_norm.fn_labels_to_array`(labels_json STRING)
RETURNS ARRAY<STRUCT<k STRING, v STRING>>
LANGUAGE js AS r"""
  if (!labels_json) return [];
  try {
    const obj = JSON.parse(labels_json);
    return Object.entries(obj).map(([k, v]) => ({k: k, v: String(v)}));
  } catch (e) {
    return [];
  }
""";

-- UDF: Extract tenant_id from labels
CREATE OR REPLACE FUNCTION `diatonic-ai-gcp.org_logs_norm.fn_extract_tenant_id`(labels_json STRING)
RETURNS STRING
LANGUAGE js AS r"""
  if (!labels_json) return null;
  try {
    const obj = JSON.parse(labels_json);
    return obj.tenant_id || obj.tenantId || obj.tenant || null;
  } catch (e) {
    return null;
  }
""";

-- UDF: Determine environment from labels or project
CREATE OR REPLACE FUNCTION `diatonic-ai-gcp.org_logs_norm.fn_derive_environment`(
  project_id STRING,
  labels_json STRING,
  service_name STRING
)
RETURNS STRING
LANGUAGE js AS r"""
  // Check labels first
  if (labels_json) {
    try {
      const obj = JSON.parse(labels_json);
      if (obj.env) return obj.env;
      if (obj.environment) return obj.environment;
    } catch (e) {}
  }

  // Derive from service name
  if (service_name) {
    const s = service_name.toLowerCase();
    if (s.includes('-dev') || s.includes('_dev')) return 'dev';
    if (s.includes('-staging') || s.includes('_staging')) return 'staging';
    if (s.includes('-prod') || s.includes('_prod')) return 'prod';
  }

  // Default to prod for this project
  return 'prod';
""";

-- UDF: Classify PII risk based on content patterns
CREATE OR REPLACE FUNCTION `diatonic-ai-gcp.org_logs_norm.fn_classify_pii_risk`(
  message STRING,
  json_payload STRING
)
RETURNS STRING
AS (
  CASE
    WHEN message IS NULL AND json_payload IS NULL THEN 'none'
    WHEN REGEXP_CONTAINS(COALESCE(message, '') || COALESCE(json_payload, ''),
         r'(?i)(password|secret|token|api[_-]?key|authorization|bearer|credit[_-]?card|ssn|social[_-]?security)')
         THEN 'high'
    WHEN REGEXP_CONTAINS(COALESCE(message, '') || COALESCE(json_payload, ''),
         r'(?i)(email|phone|address|ip[_-]?address|\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b)')
         THEN 'moderate'
    WHEN REGEXP_CONTAINS(COALESCE(message, '') || COALESCE(json_payload, ''),
         r'(?i)(user[_-]?id|account[_-]?id|customer)')
         THEN 'low'
    ELSE 'none'
  END
);

-- ============================================================================
-- SECTION 4: Canonical View - v_logs_all_entry_canon
-- Primary view with Universal Data Envelope
-- ============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon` AS
SELECT
  -- Core identifiers
  log_id,
  insert_id,

  -- Universal Data Envelope (STRUCT)
  STRUCT(
    COALESCE(schema_version, '1.0.0') AS schema_version,
    log_id AS event_id,
    log_type AS event_type,
    source_table AS event_source,
    event_timestamp AS event_ts,
    etl_timestamp AS ingest_ts,
    resource_project AS project_id,
    COALESCE(
      environment,
      `diatonic-ai-gcp.org_logs_norm.fn_derive_environment`(resource_project, labels, service_name)
    ) AS environment,
    stream_coordinates.region AS region,
    stream_coordinates.zone AS zone,

    -- Service struct
    STRUCT(
      service_name AS name,
      service_version AS revision,
      JSON_VALUE(resource_labels, '$.instance_id') AS instance_id,
      resource_type AS runtime
    ) AS service,

    -- Trace struct
    STRUCT(
      trace_id,
      span_id,
      trace_sampled AS sampled
    ) AS trace,

    -- Actor struct
    STRUCT(
      principal_email AS user_id,
      `diatonic-ai-gcp.org_logs_norm.fn_extract_tenant_id`(labels) AS tenant_id,
      stream_coordinates.organization AS org_id,
      COALESCE(caller_ip, http_remote_ip) AS ip,
      http_user_agent AS user_agent
    ) AS actor,

    -- Lifecycle struct (logs are immutable)
    STRUCT(
      event_timestamp AS created_at,
      CAST(NULL AS TIMESTAMP) AS updated_at,
      CAST(NULL AS TIMESTAMP) AS deleted_at,
      FALSE AS is_deleted
    ) AS lifecycle,

    -- Versioning struct
    STRUCT(
      CAST(1 AS INT64) AS record_version,
      etl_version AS source_version,
      TO_HEX(MD5(CONCAT(source_table, ':', COALESCE(schema_version, '1.0.0')))) AS schema_hash
    ) AS versioning,

    -- Labels array
    `diatonic-ai-gcp.org_logs_norm.fn_labels_to_array`(labels) AS labels,

    -- Tags array (from user_labels)
    ARRAY(
      SELECT value
      FROM UNNEST(`diatonic-ai-gcp.org_logs_norm.fn_labels_to_array`(user_labels))
      WHERE key IN ('tag', 'tags')
    ) AS tags,

    -- Correlation struct
    STRUCT(
      COALESCE(correlation_request_id, operation_id) AS request_id,
      correlation_session_id AS session_id,
      correlation_conversation_id AS conversation_id,
      JSON_VALUE(resource_labels, '$.job_id') AS job_id,
      parent_span_id AS parent_event_id
    ) AS correlation,

    -- Privacy struct
    STRUCT(
      COALESCE(
        privacy_pii_risk,
        `diatonic-ai-gcp.org_logs_norm.fn_classify_pii_risk`(message, CAST(json_payload AS STRING))
      ) AS pii_risk,
      COALESCE(privacy_redaction_state, 'none') AS redaction_state,
      COALESCE(privacy_retention_class,
        CASE
          WHEN is_audit THEN 'audit'
          ELSE 'standard'
        END
      ) AS retention_class
    ) AS privacy
  ) AS universal_envelope,

  -- Flat timestamps (for partition pruning and filtering)
  event_timestamp,
  receive_timestamp,
  etl_timestamp,
  log_date,

  -- Classification (flat for clustering efficiency)
  severity,
  severity_level,
  log_type,

  -- Source tracking
  source_dataset,
  source_table,
  source_log_name,
  stream_id,

  -- Service (flat for filtering)
  service_name,
  service_version,
  service_method,
  resource_type,

  -- Content
  message,
  message_summary,
  message_category,
  text_payload,
  json_payload,
  proto_payload,
  audit_payload,

  -- HTTP context
  http_method,
  http_url,
  http_status,
  http_latency_ms,
  http_user_agent,
  http_remote_ip,
  http_request_size,
  http_response_size,

  -- Trace context (flat for join efficiency)
  trace_id,
  span_id,
  trace_sampled,
  parent_span_id,
  operation_id,

  -- Error context
  error_message,
  error_code,
  error_stack_trace,
  error_group_id,

  -- Flags
  is_error,
  is_audit,
  is_request,
  has_trace,

  -- ETL metadata
  etl_version,
  etl_batch_id,
  etl_status

FROM `diatonic-ai-gcp.central_logging_v1.master_logs`;

-- ============================================================================
-- SECTION 5: Canonical View - v_logs_errors_canon
-- Error-focused view with severity >= ERROR
-- ============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_logs_errors_canon` AS
SELECT *
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE severity_level >= 500;  -- ERROR and above

-- ============================================================================
-- SECTION 6: Canonical View - v_logs_service_canon
-- Service-level aggregates for dashboards
-- ============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_logs_service_canon` AS
SELECT
  log_date,
  TIMESTAMP_TRUNC(event_timestamp, HOUR) AS hour,
  universal_envelope.service.name AS service_name,
  universal_envelope.environment AS environment,
  severity,
  COUNT(*) AS log_count,
  COUNTIF(is_error) AS error_count,
  COUNTIF(is_request) AS request_count,
  AVG(http_latency_ms) AS avg_latency_ms,
  APPROX_QUANTILES(http_latency_ms, 100)[OFFSET(50)] AS p50_latency_ms,
  APPROX_QUANTILES(http_latency_ms, 100)[OFFSET(95)] AS p95_latency_ms,
  APPROX_QUANTILES(http_latency_ms, 100)[OFFSET(99)] AS p99_latency_ms
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE http_latency_ms IS NOT NULL OR is_request
GROUP BY 1, 2, 3, 4, 5;

-- ============================================================================
-- SECTION 7: Agent Events Table
-- For tracking agent tool invocations
-- ============================================================================

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_agent.tool_invocations` (
  -- Identifiers
  invocation_id STRING NOT NULL,
  session_id STRING NOT NULL,
  conversation_id STRING,

  -- Timestamps
  invoked_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,

  -- Tool info
  tool_name STRING NOT NULL,
  tool_version STRING,
  tool_input JSON,
  tool_output JSON,

  -- Execution
  duration_ms FLOAT64,
  status STRING,  -- 'success', 'error', 'timeout'
  error_message STRING,

  -- Context
  user_id STRING,
  model_name STRING,
  prompt_tokens INT64,
  completion_tokens INT64,

  -- Universal envelope fields
  schema_version STRING DEFAULT '1.0.0',
  environment STRING DEFAULT 'prod',
  trace_id STRING,
  span_id STRING,

  -- Partition/clustering
  invocation_date DATE NOT NULL
)
PARTITION BY invocation_date
CLUSTER BY tool_name, session_id, status
OPTIONS (
  description = 'Agent tool invocation events',
  labels = [('team', 'observability'), ('component', 'agent')]
);

-- ============================================================================
-- SECTION 8: Agent Events Canonical View
-- ============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_agent_tool_event_canon` AS
SELECT
  invocation_id,

  STRUCT(
    COALESCE(schema_version, '1.0.0') AS schema_version,
    invocation_id AS event_id,
    'tool_invocation' AS event_type,
    'app.agent' AS event_source,
    invoked_at AS event_ts,
    invoked_at AS ingest_ts,
    'diatonic-ai-gcp' AS project_id,
    COALESCE(environment, 'prod') AS environment,
    'us-central1' AS region,
    CAST(NULL AS STRING) AS zone,

    STRUCT(
      'glass-pane-agent' AS name,
      tool_version AS revision,
      CAST(NULL AS STRING) AS instance_id,
      model_name AS runtime
    ) AS service,

    STRUCT(
      trace_id,
      span_id,
      CAST(NULL AS BOOL) AS sampled
    ) AS trace,

    STRUCT(
      user_id,
      CAST(NULL AS STRING) AS tenant_id,
      CAST(NULL AS STRING) AS org_id,
      CAST(NULL AS STRING) AS ip,
      CAST(NULL AS STRING) AS user_agent
    ) AS actor,

    STRUCT(
      invoked_at AS created_at,
      completed_at AS updated_at,
      CAST(NULL AS TIMESTAMP) AS deleted_at,
      FALSE AS is_deleted
    ) AS lifecycle,

    STRUCT(
      CAST(1 AS INT64) AS record_version,
      schema_version AS source_version,
      CAST(NULL AS STRING) AS schema_hash
    ) AS versioning,

    CAST([] AS ARRAY<STRUCT<k STRING, v STRING>>) AS labels,
    CAST([] AS ARRAY<STRING>) AS tags,

    STRUCT(
      invocation_id AS request_id,
      session_id,
      conversation_id,
      CAST(NULL AS STRING) AS job_id,
      CAST(NULL AS STRING) AS parent_event_id
    ) AS correlation,

    STRUCT(
      'low' AS pii_risk,
      'none' AS redaction_state,
      'standard' AS retention_class
    ) AS privacy
  ) AS universal_envelope,

  -- Tool-specific fields
  session_id,
  conversation_id,
  tool_name,
  tool_version,
  tool_input,
  tool_output,
  duration_ms,
  status,
  error_message,
  user_id,
  model_name,
  prompt_tokens,
  completion_tokens,
  invoked_at,
  completed_at,
  invocation_date

FROM `diatonic-ai-gcp.org_agent.tool_invocations`;

-- ============================================================================
-- SECTION 9: Validation Queries
-- ============================================================================

-- Validation: Check schema coverage
CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_validation_schema_coverage` AS
SELECT
  log_date,
  COUNT(*) AS total_rows,
  COUNTIF(universal_envelope.event_id IS NOT NULL) AS has_event_id,
  COUNTIF(universal_envelope.event_ts IS NOT NULL) AS has_event_ts,
  COUNTIF(universal_envelope.service.name IS NOT NULL) AS has_service_name,
  COUNTIF(universal_envelope.trace.trace_id IS NOT NULL) AS has_trace_id,
  COUNTIF(universal_envelope.actor.user_id IS NOT NULL) AS has_actor_user_id,
  COUNTIF(universal_envelope.correlation.request_id IS NOT NULL) AS has_correlation_request_id,
  COUNTIF(universal_envelope.privacy.pii_risk IS NOT NULL) AS has_privacy_pii_risk
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY log_date
ORDER BY log_date DESC;

-- Validation: Check null rates for required fields
CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_validation_null_rates` AS
SELECT
  'log_id' AS field,
  COUNTIF(log_id IS NULL) / COUNT(*) AS null_rate
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date = CURRENT_DATE()

UNION ALL

SELECT 'event_timestamp', COUNTIF(event_timestamp IS NULL) / COUNT(*)
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date = CURRENT_DATE()

UNION ALL

SELECT 'severity', COUNTIF(severity IS NULL) / COUNT(*)
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date = CURRENT_DATE()

UNION ALL

SELECT 'service_name', COUNTIF(service_name IS NULL) / COUNT(*)
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date = CURRENT_DATE()

UNION ALL

SELECT 'message', COUNTIF(message IS NULL OR message = '') / COUNT(*)
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date = CURRENT_DATE();

-- Validation: Latency distribution (event_ts to ingest_ts)
CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_validation_ingest_latency` AS
SELECT
  log_date,
  AVG(TIMESTAMP_DIFF(etl_timestamp, event_timestamp, SECOND)) AS avg_latency_seconds,
  APPROX_QUANTILES(TIMESTAMP_DIFF(etl_timestamp, event_timestamp, SECOND), 100)[OFFSET(50)] AS p50_latency_seconds,
  APPROX_QUANTILES(TIMESTAMP_DIFF(etl_timestamp, event_timestamp, SECOND), 100)[OFFSET(95)] AS p95_latency_seconds,
  MAX(TIMESTAMP_DIFF(etl_timestamp, event_timestamp, SECOND)) AS max_latency_seconds
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  AND etl_timestamp IS NOT NULL
  AND event_timestamp IS NOT NULL
GROUP BY log_date
ORDER BY log_date DESC;

-- ============================================================================
-- SECTION 10: Permissions (Run as admin)
-- ============================================================================

-- Grant read access to views for the glass-pane service account
-- GRANT `roles/bigquery.dataViewer`
-- ON SCHEMA `diatonic-ai-gcp.org_logs_norm`
-- TO 'serviceAccount:agent-sa@diatonic-ai-gcp.iam.gserviceaccount.com';

-- ============================================================================
-- END OF DDL
-- ============================================================================
