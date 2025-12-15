-- BigQuery Schema Inventory Tables
-- Project: diatonic-ai-gcp
-- Dataset: org_observability (meta tables)
-- Version: 1.0.0
-- Date: 2025-12-14

-- Create org_observability dataset if not exists
-- Run manually: bq mk --dataset --description "Observability metadata and canonical views" --location=US diatonic-ai-gcp:org_observability

-- =============================================================================
-- Schema Inventory Table
-- Stores discovered table/column information for tracking schema changes
-- =============================================================================

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_observability.meta_schema_inventory_v1` (
    discovery_timestamp TIMESTAMP NOT NULL,
    dataset_id STRING NOT NULL,
    table_id STRING NOT NULL,
    column_name STRING NOT NULL,
    column_type STRING NOT NULL,
    column_mode STRING,
    is_partitioning_column BOOL DEFAULT FALSE,
    is_clustering_column BOOL DEFAULT FALSE,
    column_description STRING,
    discovered_by STRING DEFAULT 'schema_inventory_job'
)
PARTITION BY DATE(discovery_timestamp)
CLUSTER BY dataset_id, table_id
OPTIONS (
    description = 'Schema inventory for tracking column-level changes across logging tables',
    labels = [('env', 'prod'), ('component', 'observability'), ('version', 'v1')]
);

-- =============================================================================
-- Source Table Catalog
-- Tracks which tables are mapped to canonical view
-- =============================================================================

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_observability.meta_source_catalog_v1` (
    source_dataset STRING NOT NULL,
    source_table STRING NOT NULL,
    canonical_mapped BOOL DEFAULT FALSE,
    mapping_view_name STRING,
    payload_type STRING,  -- 'json', 'text', 'proto', 'http', 'custom'
    custom_payload_field STRING,  -- Non-standard field name if applicable
    has_native_insert_id BOOL DEFAULT FALSE,
    has_native_log_name BOOL DEFAULT FALSE,
    has_resource_labels BOOL DEFAULT FALSE,
    service_name_path STRING,  -- JSON path to service name
    last_validated TIMESTAMP,
    notes STRING
)
CLUSTER BY source_dataset, source_table
OPTIONS (
    description = 'Catalog of source logging tables and their canonical mapping status',
    labels = [('env', 'prod'), ('component', 'observability'), ('version', 'v1')]
);

-- =============================================================================
-- Populate Source Catalog with discovered tables
-- =============================================================================

MERGE INTO `diatonic-ai-gcp.org_observability.meta_source_catalog_v1` AS target
USING (
    SELECT * FROM UNNEST([
        STRUCT(
            'central_logging_v1' AS source_dataset,
            'syslog' AS source_table,
            TRUE AS canonical_mapped,
            'view_canonical_logs' AS mapping_view_name,
            'json' AS payload_type,
            CAST(NULL AS STRING) AS custom_payload_field,
            FALSE AS has_native_insert_id,
            FALSE AS has_native_log_name,
            FALSE AS has_resource_labels,
            'compute' AS service_name_path,
            CURRENT_TIMESTAMP() AS last_validated,
            'Basic log table with jsonPayload and textPayload' AS notes
        ),
        STRUCT(
            'central_logging_v1', 'run_googleapis_com_stdout', TRUE, 'view_canonical_logs',
            'json', NULL, FALSE, FALSE, TRUE, 'resource.labels.service_name',
            CURRENT_TIMESTAMP(), 'Cloud Run stdout with service labels'
        ),
        STRUCT(
            'central_logging_v1', 'run_googleapis_com_stderr', TRUE, 'view_canonical_logs',
            'json', NULL, FALSE, FALSE, TRUE, 'resource.labels.service_name',
            CURRENT_TIMESTAMP(), 'Cloud Run stderr with service labels'
        ),
        STRUCT(
            'central_logging_v1', 'run_googleapis_com_requests', TRUE, 'view_canonical_logs',
            'http', 'httpRequest', TRUE, TRUE, TRUE, 'resource.labels.service_name',
            CURRENT_TIMESTAMP(), 'Cloud Run HTTP requests with httpRequest payload'
        ),
        STRUCT(
            'central_logging_v1', 'run_googleapis_com_varlog_system', TRUE, 'view_canonical_logs',
            'text', NULL, FALSE, FALSE, TRUE, 'resource.labels.service_name',
            CURRENT_TIMESTAMP(), 'Cloud Run varlog/system textPayload only'
        ),
        STRUCT(
            'central_logging_v1', 'cloudaudit_googleapis_com_activity', TRUE, 'view_canonical_logs',
            'proto', 'protoPayload', TRUE, TRUE, TRUE, 'resource.labels.service_name',
            CURRENT_TIMESTAMP(), 'Admin Activity audit logs with protoPayload'
        ),
        STRUCT(
            'central_logging_v1', 'cloudaudit_googleapis_com_data_access', TRUE, 'view_canonical_logs',
            'proto', 'protopayload_auditlog', TRUE, TRUE, TRUE, 'protopayload_auditlog.serviceName',
            CURRENT_TIMESTAMP(), 'Data Access audit logs - different payload field name'
        ),
        STRUCT(
            'central_logging_v1', 'cloudaudit_googleapis_com_system_event', TRUE, 'view_canonical_logs',
            'proto', 'protopayload_auditlog', TRUE, TRUE, TRUE, 'protopayload_auditlog.serviceName',
            CURRENT_TIMESTAMP(), 'System Event audit logs'
        ),
        STRUCT(
            'central_logging_v1', 'cloudbuild', TRUE, 'view_canonical_logs',
            'text', NULL, TRUE, TRUE, TRUE, 'resource.labels.build_id',
            CURRENT_TIMESTAMP(), 'Cloud Build logs with build_id'
        ),
        STRUCT(
            'central_logging_v1', 'clouderrorreporting_googleapis_com_insights', FALSE, NULL,
            'custom', 'jsonpayload_v1beta1_insight', TRUE, TRUE, TRUE, 'resource.labels.project_id',
            CURRENT_TIMESTAMP(), 'ERROR: Not in canonical view - uses non-standard payload field'
        ),
        STRUCT(
            'central_logging_v1', 'cloudscheduler_googleapis_com_executions', FALSE, NULL,
            'custom', 'jsonpayload_logging_attemptstarted', TRUE, TRUE, TRUE, 'resource.labels.job_id',
            CURRENT_TIMESTAMP(), 'ERROR: Not in canonical view - uses two non-standard payload fields'
        ),
        STRUCT(
            'central_logging_v1', 'glass_pane_test', FALSE, NULL,
            'unknown', NULL, TRUE, TRUE, TRUE, NULL,
            CURRENT_TIMESTAMP(), 'Test table - evaluate if needed in canonical view'
        )
    ])
) AS source
ON target.source_dataset = source.source_dataset AND target.source_table = source.source_table
WHEN MATCHED THEN UPDATE SET
    canonical_mapped = source.canonical_mapped,
    mapping_view_name = source.mapping_view_name,
    payload_type = source.payload_type,
    custom_payload_field = source.custom_payload_field,
    has_native_insert_id = source.has_native_insert_id,
    has_native_log_name = source.has_native_log_name,
    has_resource_labels = source.has_resource_labels,
    service_name_path = source.service_name_path,
    last_validated = source.last_validated,
    notes = source.notes
WHEN NOT MATCHED THEN INSERT ROW;
