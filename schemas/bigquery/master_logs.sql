-- Master Logs Table Schema
-- Unified schema for all GCP log types with stream tracking and ETL metadata
-- This is the single source of truth for the logging API

CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.central_logging_v1.master_logs` (
    -- Primary identifiers
    log_id STRING NOT NULL,                      -- Unique identifier (UUID)
    insert_id STRING,                            -- Original BigQuery insert ID

    -- Timestamps
    event_timestamp TIMESTAMP NOT NULL,          -- When the event occurred
    receive_timestamp TIMESTAMP,                 -- When GCP received the log
    etl_timestamp TIMESTAMP NOT NULL,            -- When ETL processed this record

    -- Severity and classification
    severity STRING NOT NULL,                    -- DEFAULT, DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL, ALERT, EMERGENCY
    severity_level INT64,                        -- Numeric severity (0-800)
    log_type STRING NOT NULL,                    -- audit, request, application, system, error, build

    -- Source tracking (Stream metadata)
    source_dataset STRING NOT NULL,              -- Origin dataset (central_logging_v1, org_logs)
    source_table STRING NOT NULL,                -- Origin table name
    source_log_name STRING,                      -- Original logName field
    stream_id STRING NOT NULL,                   -- Unique stream identifier
    stream_direction STRING,                     -- INBOUND, OUTBOUND, INTERNAL
    stream_flow STRING,                          -- REALTIME, BATCH, SCHEDULED
    stream_coordinates STRUCT<
        region STRING,
        zone STRING,
        project STRING,
        organization STRING
    >,

    -- Resource information (normalized)
    resource_type STRING,                        -- cloud_run_revision, cloud_function, gce_instance, etc.
    resource_project STRING,
    resource_name STRING,                        -- Service/function/instance name
    resource_location STRING,                    -- Region/zone
    resource_labels JSON,                        -- All resource labels as JSON

    -- Service identification
    service_name STRING,                         -- Extracted service name
    service_version STRING,
    service_method STRING,                       -- For audit logs: API method called

    -- Content (normalized payloads)
    message STRING,                              -- Primary message content (normalized from all payload types)
    message_summary STRING,                      -- AI-generated summary (Vertex)
    message_category STRING,                     -- AI-classified category

    -- Original payloads (preserved for reference)
    text_payload STRING,                         -- Original textPayload
    json_payload JSON,                           -- Original jsonPayload (normalized to JSON)
    proto_payload JSON,                          -- Original protoPayload (normalized to JSON)
    audit_payload JSON,                          -- Extracted audit log details

    -- HTTP request context
    http_method STRING,
    http_url STRING,
    http_status INT64,
    http_latency_ms FLOAT64,
    http_user_agent STRING,
    http_remote_ip STRING,
    http_request_size INT64,
    http_response_size INT64,
    http_full JSON,                              -- Full httpRequest object

    -- Trace context
    trace_id STRING,
    span_id STRING,
    trace_sampled BOOL,
    parent_span_id STRING,

    -- Operation context
    operation_id STRING,
    operation_producer STRING,
    operation_first BOOL,
    operation_last BOOL,

    -- Source location (code context)
    source_file STRING,
    source_line INT64,
    source_function STRING,

    -- Labels and metadata
    labels JSON,                                 -- All labels as JSON
    user_labels JSON,                            -- User-defined labels
    system_labels JSON,                          -- System labels

    -- Principal/Actor information (for audit logs)
    principal_email STRING,
    principal_type STRING,                       -- USER, SERVICE_ACCOUNT, etc.
    caller_ip STRING,
    caller_network STRING,

    -- Error context
    error_message STRING,
    error_code STRING,
    error_stack_trace STRING,
    error_group_id STRING,

    -- Analytics fields
    is_error BOOL,                               -- severity >= ERROR
    is_audit BOOL,                               -- From audit log tables
    is_request BOOL,                             -- HTTP request log
    has_trace BOOL,                              -- Has trace context

    -- ETL metadata
    etl_version STRING NOT NULL,                 -- ETL pipeline version
    etl_batch_id STRING,                         -- Batch processing ID
    etl_status STRING,                           -- SUCCESS, PARTIAL, ENRICHED
    etl_enrichments ARRAY<STRING>,               -- List of enrichments applied

    -- Partitioning and clustering support
    log_date DATE NOT NULL,                      -- For daily partitioning
    cluster_key STRING                           -- For clustering optimization
)
PARTITION BY log_date
CLUSTER BY severity, service_name, resource_type
OPTIONS (
    description = 'Unified master logs table - Single source of truth for all GCP logs',
    labels = [('env', 'production'), ('team', 'observability'), ('etl', 'v1')],
    require_partition_filter = true
);

-- Create a view for easy querying without partition filter
CREATE OR REPLACE VIEW `diatonic-ai-gcp.central_logging_v1.logs_unified` AS
SELECT * FROM `diatonic-ai-gcp.central_logging_v1.master_logs`
WHERE _partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY);

-- Stream metadata table for tracking data sources
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.central_logging_v1.log_streams` (
    stream_id STRING NOT NULL,
    stream_name STRING NOT NULL,
    source_dataset STRING NOT NULL,
    source_table STRING NOT NULL,
    stream_direction STRING,                     -- INBOUND, OUTBOUND, INTERNAL
    stream_flow STRING,                          -- REALTIME, BATCH, SCHEDULED
    stream_coordinates STRUCT<
        region STRING,
        zone STRING,
        project STRING,
        organization STRING
    >,
    is_active BOOL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP,
    last_sync_at TIMESTAMP,
    last_sync_offset INT64 DEFAULT 0,
    total_records_synced INT64 DEFAULT 0,
    config JSON                                  -- Stream-specific configuration
);

-- ETL job tracking table
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.central_logging_v1.etl_jobs` (
    job_id STRING NOT NULL,
    job_type STRING NOT NULL,                    -- EXTRACT, NORMALIZE, TRANSFORM, LOAD, FULL_ETL
    batch_id STRING,
    stream_id STRING,
    status STRING NOT NULL,                      -- PENDING, RUNNING, SUCCESS, FAILED, PARTIAL
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    records_processed INT64 DEFAULT 0,
    records_failed INT64 DEFAULT 0,
    error_message STRING,
    config JSON,
    metrics JSON                                 -- Performance metrics
);
