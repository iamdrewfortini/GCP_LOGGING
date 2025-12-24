-- =============================================================================
-- BigQuery Standardization DDL
-- Purpose: unified naming, labels, partitioning, clustering, tracing, and
--          enterprise org/workforce model across logging, finops, agent data.
-- Project: diatonic-ai-gcp
-- Date: 2025-12-24
-- Version: 2.1.0
-- =============================================================================

-- -----------------------------------------------------------------------------
-- SECTION 0: Label policy (apply to all new objects)
-- -----------------------------------------------------------------------------
-- Mandatory labels:
--   env, team, owner, data_product, cost_center, pii, retention_class, version, lineage_hash

-- -----------------------------------------------------------------------------
-- SECTION 1: Datasets (idempotent)
-- -----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `diatonic-ai-gcp.org_logs_canon`
OPTIONS (
  description = 'Canonical log fact tables with enforced labels/partitioning',
  labels = [
    ('env', 'prod'), ('team', 'observability'), ('owner', 'platform-data'),
    ('data_product', 'logs'), ('version', 'v2'), ('retention_class', 'standard')
  ]
);

CREATE SCHEMA IF NOT EXISTS `diatonic-ai-gcp.org_enterprise`
OPTIONS (
  description = 'Enterprise org / workforce dimensional model',
  labels = [
    ('env', 'prod'), ('team', 'enterprise-data'), ('owner', 'platform-data'),
    ('data_product', 'org-model'), ('version', 'v1'), ('retention_class', 'standard')
  ]
);

-- Label refresh on existing key datasets (safe, idempotent)
ALTER SCHEMA `diatonic-ai-gcp.org_logs_norm`
SET OPTIONS (labels = [('env','prod'),('team','observability'),('owner','platform-data'),('data_product','logs'),('version','v2')]);
ALTER SCHEMA `diatonic-ai-gcp.org_finops`
SET OPTIONS (labels = [('env','prod'),('team','finops'),('owner','platform-data'),('data_product','bq-costs'),('version','v2')]);
ALTER SCHEMA `diatonic-ai-gcp.org_agent`
SET OPTIONS (labels = [('env','prod'),('team','agent'),('owner','platform-data'),('data_product','agent-telemetry'),('version','v2')]);
ALTER SCHEMA `diatonic-ai-gcp.org_observability`
SET OPTIONS (labels = [('env','prod'),('team','observability'),('owner','platform-data'),('data_product','observability'),('version','v2')]);

-- -----------------------------------------------------------------------------
-- SECTION 2: Canonical log fact tables (new names) with partition/cluster
-- -----------------------------------------------------------------------------
-- Source: org_logs_norm.v_logs_all_entry_canon

CREATE OR REPLACE TABLE `diatonic-ai-gcp.org_logs_canon.fact_logs`
PARTITION BY log_date
CLUSTER BY severity, service_name, resource_type
OPTIONS (
  description = 'Canonical log facts with envelope + tracing',
  labels = [
    ('env','prod'),('team','observability'),('owner','platform-data'),
    ('data_product','logs'),('version','v2'),('lineage_hash','tbd_fact_logs_v2'),
    ('retention_class','standard')
  ],
  require_partition_filter = TRUE
)
AS
SELECT
  log_id,
  insert_id,
  universal_envelope,
  event_timestamp,
  receive_timestamp,
  etl_timestamp,
  log_date,
  severity,
  severity_level,
  log_type,
  source_dataset,
  source_table,
  source_log_name,
  stream_id,
  service_name,
  service_version,
  service_method,
  resource_type,
  message,
  message_summary,
  message_category,
  text_payload,
  json_payload,
  proto_payload,
  audit_payload,
  http_method,
  http_url,
  http_status,
  http_latency_ms,
  http_user_agent,
  http_remote_ip,
  http_request_size,
  http_response_size,
  trace_id,
  span_id,
  trace_sampled,
  parent_span_id,
  operation_id,
  error_message,
  error_code,
  error_stack_trace,
  error_group_id,
  is_error,
  is_audit,
  is_request,
  has_trace,
  etl_version,
  etl_batch_id,
  etl_status,
  -- tracing/lineage consistency
  COALESCE(universal_envelope.correlation.request_id, trace_id) AS correlation_id,
  'logs' AS source_system,
  'org_logs_norm.v_logs_all_entry_canon' AS source_view
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date IS NOT NULL;

CREATE OR REPLACE TABLE `diatonic-ai-gcp.org_logs_canon.fact_logs_errors`
PARTITION BY log_date
CLUSTER BY service_name, severity, resource_type
OPTIONS (
  description = 'Error-only log facts (severity >= ERROR)',
  labels = [
    ('env','prod'),('team','observability'),('owner','platform-data'),
    ('data_product','logs'),('version','v2'),('lineage_hash','tbd_fact_logs_errors_v2'),
    ('retention_class','standard')
  ],
  require_partition_filter = TRUE
)
AS
SELECT * EXCEPT(source_system, source_view)
FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`
WHERE severity_level >= 500
  AND log_date IS NOT NULL;

CREATE OR REPLACE TABLE `diatonic-ai-gcp.org_logs_canon.fact_logs_services`
PARTITION BY log_date
CLUSTER BY service_name, environment, severity
OPTIONS (
  description = 'Service-level aggregates with latency/error metrics',
  labels = [
    ('env','prod'),('team','observability'),('owner','platform-data'),
    ('data_product','logs'),('version','v2'),('lineage_hash','tbd_fact_logs_services_v2'),
    ('retention_class','standard')
  ],
  require_partition_filter = TRUE
)
AS
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
FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`
WHERE log_date IS NOT NULL
GROUP BY 1,2,3,4,5;

-- Compatibility views (old names -> new tables)
CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
OPTIONS (labels = [('alias_for','org_logs_canon_fact_logs'),('version','v2')]) AS
SELECT * FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`;

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_logs_errors_canon`
OPTIONS (labels = [('alias_for','org_logs_canon_fact_logs_errors'),('version','v2')]) AS
SELECT * FROM `diatonic-ai-gcp.org_logs_canon.fact_logs_errors`;

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_logs_service_canon`
OPTIONS (labels = [('alias_for','org_logs_canon_fact_logs_services'),('version','v2')]) AS
SELECT * FROM `diatonic-ai-gcp.org_logs_canon.fact_logs_services`;

-- -----------------------------------------------------------------------------
-- SECTION 3: FinOps & Agent label/partition/cluster alignment
-- -----------------------------------------------------------------------------
-- FinOps: create v2 table with clustering; keep original as source
CREATE OR REPLACE TABLE `diatonic-ai-gcp.org_finops.bq_jobs_daily_v2`
PARTITION BY dt
CLUSTER BY project_id, statement_type, cache_hit
OPTIONS (
  description = 'BigQuery job cost/usage (clustered, labeled)',
  labels = [
    ('env','prod'),('team','finops'),('owner','platform-data'),
    ('data_product','bq-costs'),('version','v2'),('lineage_hash','tbd_bq_jobs_daily_v2'),
    ('retention_class','finance')
  ],
  require_partition_filter = TRUE
)
AS
SELECT * FROM `diatonic-ai-gcp.org_finops.bq_jobs_daily`
WHERE dt IS NOT NULL;

-- Agent telemetry: enforce labels & partition filter (table already partitioned)
ALTER TABLE `diatonic-ai-gcp.org_agent.tool_invocations`
SET OPTIONS (
  labels = [
    ('env','prod'),('team','agent'),('owner','platform-data'),
    ('data_product','agent-telemetry'),('version','v2'),('retention_class','standard')
  ],
  require_partition_filter = TRUE
);

-- -----------------------------------------------------------------------------
-- SECTION 4: Enterprise org/workforce dimensional model (SCD2)
-- -----------------------------------------------------------------------------
-- Dim tables
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.dim_org` (
  org_id STRING NOT NULL,
  org_name STRING,
  parent_org_id STRING,
  region STRING,
  active_from DATE NOT NULL,
  active_to DATE,
  is_current BOOL DEFAULT TRUE,
  source_system STRING,
  trace_id STRING,
  span_id STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP,
  labels JSON
)
PARTITION BY active_from
CLUSTER BY org_id
OPTIONS (labels=[('data_product','org-model'),('team','enterprise-data'),('version','v1'),('env','prod')]);

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.dim_project` (
  project_id STRING NOT NULL,
  project_number STRING,
  org_id STRING,
  project_name STRING,
  folder_id STRING,
  lifecycle_state STRING,
  billing_account STRING,
  active_from DATE NOT NULL,
  active_to DATE,
  is_current BOOL DEFAULT TRUE,
  source_system STRING,
  trace_id STRING,
  span_id STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP,
  labels JSON
)
PARTITION BY active_from
CLUSTER BY project_id, org_id
OPTIONS (labels=[('data_product','org-model'),('team','enterprise-data'),('version','v1'),('env','prod')]);

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.dim_environment` (
  environment_id STRING NOT NULL,
  project_id STRING,
  env STRING, -- dev|stage|prod|test|sandbox
  region STRING,
  active_from DATE NOT NULL,
  active_to DATE,
  is_current BOOL DEFAULT TRUE,
  source_system STRING,
  trace_id STRING,
  span_id STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP,
  labels JSON
)
PARTITION BY active_from
CLUSTER BY env, project_id
OPTIONS (labels=[('data_product','org-model'),('team','enterprise-data'),('version','v1'),('env','prod')]);

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.dim_service` (
  service_id STRING NOT NULL,
  service_name STRING,
  application_id STRING,
  project_id STRING,
  runtime STRING,
  owner_team STRING,
  active_from DATE NOT NULL,
  active_to DATE,
  is_current BOOL DEFAULT TRUE,
  source_system STRING,
  trace_id STRING,
  span_id STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP,
  labels JSON
)
PARTITION BY active_from
CLUSTER BY service_id, project_id
OPTIONS (labels=[('data_product','org-model'),('team','enterprise-data'),('version','v1'),('env','prod')]);

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.dim_application` (
  application_id STRING NOT NULL,
  app_name STRING,
  business_domain STRING,
  owner_team STRING,
  active_from DATE NOT NULL,
  active_to DATE,
  is_current BOOL DEFAULT TRUE,
  source_system STRING,
  trace_id STRING,
  span_id STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP,
  labels JSON
)
PARTITION BY active_from
CLUSTER BY application_id
OPTIONS (labels=[('data_product','org-model'),('team','enterprise-data'),('version','v1'),('env','prod')]);

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.dim_workforce_member` (
  member_id STRING NOT NULL,
  email STRING,
  display_name STRING,
  org_id STRING,
  manager_id STRING,
  employment_type STRING,
  active_from DATE NOT NULL,
  active_to DATE,
  is_current BOOL DEFAULT TRUE,
  source_system STRING,
  trace_id STRING,
  span_id STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP,
  labels JSON
)
PARTITION BY active_from
CLUSTER BY member_id, org_id
OPTIONS (labels=[('data_product','org-model'),('team','enterprise-data'),('version','v1'),('env','prod')]);

-- Bridge tables
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.bridge_service_project` (
  service_id STRING,
  project_id STRING,
  environment_id STRING,
  active_from DATE NOT NULL,
  active_to DATE,
  is_current BOOL DEFAULT TRUE,
  trace_id STRING,
  span_id STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP
)
PARTITION BY active_from
CLUSTER BY service_id, project_id
OPTIONS (labels=[('data_product','org-model'),('team','enterprise-data'),('version','v1'),('env','prod')]);

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.bridge_member_service` (
  member_id STRING,
  service_id STRING,
  role STRING,
  active_from DATE NOT NULL,
  active_to DATE,
  is_current BOOL DEFAULT TRUE,
  trace_id STRING,
  span_id STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP
)
PARTITION BY active_from
CLUSTER BY member_id, service_id
OPTIONS (labels=[('data_product','org-model'),('team','enterprise-data'),('version','v1'),('env','prod')]);

-- Fact tables
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.fact_usage` (
  usage_date DATE NOT NULL,
  project_id STRING,
  service_id STRING,
  application_id STRING,
  environment_id STRING,
  request_count INT64,
  error_count INT64,
  success_count INT64,
  latency_p50_ms FLOAT64,
  latency_p95_ms FLOAT64,
  cost_usd NUMERIC,
  trace_id STRING,
  span_id STRING,
  source_system STRING,
  ingestion_method STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP
)
PARTITION BY usage_date
CLUSTER BY project_id, service_id, application_id
OPTIONS (labels=[('data_product','org-model'),('team','enterprise-data'),('version','v1'),('env','prod')], require_partition_filter=TRUE);

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.fact_policy` (
  policy_snapshot_date DATE NOT NULL,
  project_id STRING,
  resource STRING,
  member STRING,
  role STRING,
  condition STRING,
  origin STRING, -- asset_inventory | admin_sdk | gcloud
  trace_id STRING,
  span_id STRING,
  source_system STRING,
  ingestion_method STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY policy_snapshot_date
CLUSTER BY project_id, member, role
OPTIONS (labels=[('data_product','org-model'),('team','enterprise-data'),('version','v1'),('env','prod')], require_partition_filter=TRUE);

-- Staging tables for external API pulls (populated by pipelines)
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.stg_admin_users` (
  fetched_at TIMESTAMP,
  payload JSON
) OPTIONS (labels=[('source_system','admin_sdk'),('team','enterprise-data'),('env','prod')]);

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.stg_asset_inventory` (
  fetched_at TIMESTAMP,
  asset_type STRING,
  payload JSON
) OPTIONS (labels=[('source_system','cloud_asset_inventory'),('team','enterprise-data'),('env','prod')]);

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.stg_service_usage` (
  fetched_at TIMESTAMP,
  service_name STRING,
  payload JSON
) OPTIONS (labels=[('source_system','service_usage'),('team','enterprise-data'),('env','prod')]);

-- -----------------------------------------------------------------------------
-- SECTION 5: Unified tracing view (glass pane)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_observability.v_traces_unified` AS
WITH
logs AS (
  SELECT
    trace_id,
    span_id,
    COALESCE(universal_envelope.correlation.request_id, trace_id) AS correlation_id,
    event_timestamp AS event_ts,
    severity,
    service_name,
    CAST(NULL AS STRING) AS project_id,
    resource_type,
    universal_envelope.actor.user_id AS user_id,
    CAST(NULL AS NUMERIC) AS cost_usd,
    is_error AS is_error,
    'logs' AS source_system,
    source_dataset,
    source_table,
    etl_batch_id AS etl_job_id,
    etl_version
  FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`
),
finops AS (
  SELECT
    SAFE_CONVERT_BYTES_TO_STRING(SHA256(CONCAT(project_id, '-', CAST(dt AS STRING), '-', job_id))) AS trace_id,
    CAST(NULL AS STRING) AS span_id,
    job_id AS correlation_id,
    TIMESTAMP(dt) AS event_ts,
    'INFO' AS severity,
    'bigquery' AS service_name,
    CAST(project_id AS STRING) AS project_id,
    'bigquery_job' AS resource_type,
    user_email AS user_id,
    total_bytes_processed * 0.000000001 AS cost_usd, -- rough GB processed
    FALSE AS is_error,
    'finops' AS source_system,
    'org_finops' AS source_dataset,
    'bq_jobs_daily_v2' AS source_table,
    job_id AS etl_job_id,
    'v2' AS etl_version
  FROM `diatonic-ai-gcp.org_finops.bq_jobs_daily_v2`
),
agent AS (
  SELECT
    COALESCE(trace_id, invocation_id) AS trace_id,
    span_id,
    session_id AS correlation_id,
    invoked_at AS event_ts,
    'INFO' AS severity,
    tool_name AS service_name,
    CAST(NULL AS STRING) AS project_id,
    'agent_tool' AS resource_type,
    user_id,
    NULL AS cost_usd,
    status = 'error' AS is_error,
    'agent' AS source_system,
    'org_agent' AS source_dataset,
    'tool_invocations' AS source_table,
    invocation_id AS etl_job_id,
    COALESCE(schema_version, '1.0.0') AS etl_version
  FROM `diatonic-ai-gcp.org_agent.tool_invocations`
),
org_fact AS (
  SELECT
    trace_id,
    span_id,
    CONCAT(project_id, ':', resource) AS correlation_id,
    TIMESTAMP(policy_snapshot_date) AS event_ts,
    'INFO' AS severity,
    'policy' AS service_name,
    CAST(project_id AS STRING) AS project_id,
    'policy_binding' AS resource_type,
    member AS user_id,
    NULL AS cost_usd,
    FALSE AS is_error,
    'org_model' AS source_system,
    'org_enterprise' AS source_dataset,
    'fact_policy' AS source_table,
    CAST(NULL AS STRING) AS etl_job_id,
    'v1' AS etl_version
  FROM `diatonic-ai-gcp.org_enterprise.fact_policy`
)
SELECT * FROM logs
UNION ALL SELECT * FROM finops
UNION ALL SELECT * FROM agent
UNION ALL SELECT * FROM org_fact;

-- -----------------------------------------------------------------------------
-- SECTION 6: Schema change log (governance)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_logs_canon.schema_changelog` (
  change_version STRING NOT NULL,
  change_type STRING, -- add/alter/drop/rename
  object_type STRING, -- table/view/schema
  object_name STRING,
  applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  applied_by STRING,
  description STRING
)
OPTIONS (labels=[('data_product','logs'),('team','observability'),('env','prod'),('version','v2')]);

-- -----------------------------------------------------------------------------
-- SECTION 7: Operational notes (execution order)
-- -----------------------------------------------------------------------------
-- 1) Run this script (idempotent).
-- 2) Backfill org_logs_canon.fact_logs from source view (already CTAS here).
-- 3) Validate counts/hash vs org_logs_norm views.
-- 4) Switch consumers to org_logs_canon.fact_* tables; keep compatibility views until deprecation.
-- 5) For finops, use bq_jobs_daily_v2 and plan cutover; drop legacy after validation.
-- 6) Populate org_enterprise dims/bridges via Admin SDK, Cloud Asset Inventory, Service Usage exports.
-- 7) Enable Cloud Scheduler / Workflows to refresh staging tables and merge into SCD2 dims.

