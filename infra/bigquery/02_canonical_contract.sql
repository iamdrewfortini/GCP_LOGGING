-- Canonical Log Contract Definition
-- Project: diatonic-ai-gcp
-- Dataset: org_observability
-- Version: 2.0.0 (Extends existing view_canonical_logs)
-- Date: 2025-12-14

-- =============================================================================
-- Canonical Schema Contract v2.0
-- =============================================================================
-- This defines the target schema for unified log access across all datasets.
-- All source tables should be mapped through views that conform to this contract.

-- Field Definitions:
-- | Field             | Type      | Description                                    |
-- |-------------------|-----------|------------------------------------------------|
-- | insert_id         | STRING    | Unique identifier (native or synthetic)        |
-- | event_timestamp   | TIMESTAMP | When the event occurred (NOT receive time)     |
-- | receive_timestamp | TIMESTAMP | When log was received (nullable)               |
-- | severity          | STRING    | Normalized severity level                      |
-- | log_name          | STRING    | Full log name path                             |
-- | service_name      | STRING    | Service identifier for filtering               |
-- | resource_type     | STRING    | GCP resource type                              |
-- | resource_labels   | STRING    | Resource labels as JSON string                 |
-- | trace_id          | STRING    | Distributed trace ID                           |
-- | span_id           | STRING    | Span ID within trace                           |
-- | trace_sampled     | BOOL      | Whether trace was sampled (nullable)           |
-- | text_payload      | STRING    | Plain text log content (nullable)              |
-- | json_payload      | STRING    | JSON content as string (nullable)              |
-- | proto_payload     | STRING    | Proto content as JSON string (nullable)        |
-- | display_message   | STRING    | Human-readable summary for UI                  |
-- | source_dataset    | STRING    | Originating dataset name                       |
-- | source_table      | STRING    | Originating table name                         |
-- | source_bucket     | STRING    | Log Analytics bucket (nullable)                |
-- | ingestion_method  | STRING    | How log was ingested (sink/linked/direct)      |

-- =============================================================================
-- Extended Canonical View (org_observability.logs_canonical_v2)
-- Includes all tables from central_logging_v1 + new tables
-- =============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_observability.logs_canonical_v2` AS

-- =========================================
-- Cloud Audit: Admin Activity
-- =========================================
SELECT
    insertId AS insert_id,
    timestamp AS event_timestamp,
    CAST(NULL AS TIMESTAMP) AS receive_timestamp,
    COALESCE(severity, 'INFO') AS severity,
    logName AS log_name,
    COALESCE(resource.labels.service_name, resource.labels.module_id, 'audit') AS service_name,
    COALESCE(resource.type, 'audited_resource') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            COALESCE(resource.labels.service_name, 'audit'),
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(insertId)), 1, 16)) AS span_id,
    CAST(NULL AS BOOL) AS trace_sampled,
    CAST(NULL AS STRING) AS text_payload,
    TO_JSON_STRING(protoPayload) AS json_payload,
    TO_JSON_STRING(protoPayload) AS proto_payload,
    COALESCE(protoPayload.response.message, logName) AS display_message,
    'central_logging_v1' AS source_dataset,
    'cloudaudit_googleapis_com_activity' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.cloudaudit_googleapis_com_activity`

UNION ALL

-- =========================================
-- Cloud Audit: Data Access
-- =========================================
SELECT
    insertId AS insert_id,
    timestamp AS event_timestamp,
    CAST(NULL AS TIMESTAMP) AS receive_timestamp,
    COALESCE(severity, 'INFO') AS severity,
    logName AS log_name,
    COALESCE(protopayload_auditlog.serviceName, 'bigquery') AS service_name,
    COALESCE(resource.type, 'audited_resource') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            COALESCE(protopayload_auditlog.serviceName, 'bigquery'),
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(insertId)), 1, 16)) AS span_id,
    CAST(NULL AS BOOL) AS trace_sampled,
    CAST(NULL AS STRING) AS text_payload,
    TO_JSON_STRING(protopayload_auditlog) AS json_payload,
    TO_JSON_STRING(protopayload_auditlog) AS proto_payload,
    COALESCE(protopayload_auditlog.methodName, '') AS display_message,
    'central_logging_v1' AS source_dataset,
    'cloudaudit_googleapis_com_data_access' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.cloudaudit_googleapis_com_data_access`

UNION ALL

-- =========================================
-- Cloud Audit: System Event
-- =========================================
SELECT
    insertId AS insert_id,
    timestamp AS event_timestamp,
    CAST(NULL AS TIMESTAMP) AS receive_timestamp,
    COALESCE(severity, 'INFO') AS severity,
    logName AS log_name,
    COALESCE(protopayload_auditlog.serviceName, 'system') AS service_name,
    COALESCE(resource.type, 'audited_resource') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            COALESCE(protopayload_auditlog.serviceName, 'system'),
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(insertId)), 1, 16)) AS span_id,
    CAST(NULL AS BOOL) AS trace_sampled,
    CAST(NULL AS STRING) AS text_payload,
    TO_JSON_STRING(protopayload_auditlog) AS json_payload,
    TO_JSON_STRING(protopayload_auditlog) AS proto_payload,
    COALESCE(protopayload_auditlog.methodName, '') AS display_message,
    'central_logging_v1' AS source_dataset,
    'cloudaudit_googleapis_com_system_event' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.cloudaudit_googleapis_com_system_event`

UNION ALL

-- =========================================
-- Cloud Run: stdout
-- =========================================
SELECT
    TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(trace, ''), COALESCE(spanId, ''), COALESCE(textPayload, ''), COALESCE(resource.labels.service_name, '')))) AS insert_id,
    timestamp AS event_timestamp,
    CAST(NULL AS TIMESTAMP) AS receive_timestamp,
    COALESCE(severity, 'INFO') AS severity,
    'run.googleapis.com/stdout' AS log_name,
    resource.labels.service_name AS service_name,
    COALESCE(resource.type, 'cloud_run_revision') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            resource.labels.service_name,
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(textPayload, '')))), 1, 16)) AS span_id,
    CAST(NULL AS BOOL) AS trace_sampled,
    textPayload AS text_payload,
    TO_JSON_STRING(jsonPayload) AS json_payload,
    CAST(NULL AS STRING) AS proto_payload,
    textPayload AS display_message,
    'central_logging_v1' AS source_dataset,
    'run_googleapis_com_stdout' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.run_googleapis_com_stdout`

UNION ALL

-- =========================================
-- Cloud Run: stderr
-- =========================================
SELECT
    TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(trace, ''), COALESCE(spanId, ''), COALESCE(textPayload, ''), COALESCE(resource.labels.service_name, '')))) AS insert_id,
    timestamp AS event_timestamp,
    CAST(NULL AS TIMESTAMP) AS receive_timestamp,
    COALESCE(severity, 'ERROR') AS severity,
    'run.googleapis.com/stderr' AS log_name,
    resource.labels.service_name AS service_name,
    COALESCE(resource.type, 'cloud_run_revision') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            resource.labels.service_name,
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(textPayload, '')))), 1, 16)) AS span_id,
    CAST(NULL AS BOOL) AS trace_sampled,
    textPayload AS text_payload,
    TO_JSON_STRING(jsonPayload) AS json_payload,
    CAST(NULL AS STRING) AS proto_payload,
    textPayload AS display_message,
    'central_logging_v1' AS source_dataset,
    'run_googleapis_com_stderr' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.run_googleapis_com_stderr`

UNION ALL

-- =========================================
-- Cloud Run: requests
-- =========================================
SELECT
    COALESCE(insertId, TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(trace, ''), COALESCE(httpRequest.requestUrl, ''))))) AS insert_id,
    timestamp AS event_timestamp,
    receiveTimestamp AS receive_timestamp,
    COALESCE(severity, 'INFO') AS severity,
    COALESCE(logName, 'run.googleapis.com/requests') AS log_name,
    resource.labels.service_name AS service_name,
    COALESCE(resource.type, 'cloud_run_revision') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            resource.labels.service_name,
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(httpRequest.requestUrl, '')))), 1, 16)) AS span_id,
    traceSampled AS trace_sampled,
    CAST(NULL AS STRING) AS text_payload,
    TO_JSON_STRING(httpRequest) AS json_payload,
    CAST(NULL AS STRING) AS proto_payload,
    CONCAT(COALESCE(httpRequest.requestMethod, 'GET'), ' ', COALESCE(httpRequest.requestUrl, '/')) AS display_message,
    'central_logging_v1' AS source_dataset,
    'run_googleapis_com_requests' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.run_googleapis_com_requests`

UNION ALL

-- =========================================
-- Cloud Run: varlog/system
-- =========================================
SELECT
    TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(trace, ''), COALESCE(textPayload, ''), COALESCE(resource.labels.service_name, '')))) AS insert_id,
    timestamp AS event_timestamp,
    CAST(NULL AS TIMESTAMP) AS receive_timestamp,
    COALESCE(severity, 'INFO') AS severity,
    'run.googleapis.com/varlog/system' AS log_name,
    resource.labels.service_name AS service_name,
    COALESCE(resource.type, 'cloud_run_revision') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            resource.labels.service_name,
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(textPayload, '')))), 1, 16)) AS span_id,
    CAST(NULL AS BOOL) AS trace_sampled,
    textPayload AS text_payload,
    '{}' AS json_payload,
    CAST(NULL AS STRING) AS proto_payload,
    textPayload AS display_message,
    'central_logging_v1' AS source_dataset,
    'run_googleapis_com_varlog_system' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.run_googleapis_com_varlog_system`

UNION ALL

-- =========================================
-- Syslog
-- =========================================
SELECT
    TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(trace, ''), COALESCE(spanId, ''), COALESCE(textPayload, '')))) AS insert_id,
    timestamp AS event_timestamp,
    CAST(NULL AS TIMESTAMP) AS receive_timestamp,
    COALESCE(severity, 'INFO') AS severity,
    'syslog' AS log_name,
    'compute' AS service_name,
    'global' AS resource_type,
    '{}' AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            'compute',
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(textPayload, '')))), 1, 16)) AS span_id,
    CAST(NULL AS BOOL) AS trace_sampled,
    textPayload AS text_payload,
    TO_JSON_STRING(jsonPayload) AS json_payload,
    CAST(NULL AS STRING) AS proto_payload,
    textPayload AS display_message,
    'central_logging_v1' AS source_dataset,
    'syslog' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.syslog`

UNION ALL

-- =========================================
-- Cloud Build
-- =========================================
SELECT
    COALESCE(insertId, TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(textPayload, ''), COALESCE(resource.labels.build_id, ''))))) AS insert_id,
    timestamp AS event_timestamp,
    receiveTimestamp AS receive_timestamp,
    COALESCE(severity, 'INFO') AS severity,
    COALESCE(logName, 'cloudbuild') AS log_name,
    'cloudbuild' AS service_name,
    COALESCE(resource.type, 'build') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            'cloudbuild',
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING),
            '-',
            COALESCE(resource.labels.build_id, '')
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(CONCAT(CAST(timestamp AS STRING), COALESCE(resource.labels.build_id, '')))), 1, 16)) AS span_id,
    traceSampled AS trace_sampled,
    textPayload AS text_payload,
    CONCAT('{"build_id":"', COALESCE(resource.labels.build_id, ''), '"}') AS json_payload,
    CAST(NULL AS STRING) AS proto_payload,
    textPayload AS display_message,
    'central_logging_v1' AS source_dataset,
    'cloudbuild' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.cloudbuild`

UNION ALL

-- =========================================
-- Cloud Error Reporting (NEW in v2)
-- =========================================
SELECT
    insertId AS insert_id,
    timestamp AS event_timestamp,
    receiveTimestamp AS receive_timestamp,
    COALESCE(severity, 'ERROR') AS severity,
    logName AS log_name,
    COALESCE(resource.labels.project_id, 'error-reporting') AS service_name,
    COALESCE(resource.type, 'global') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            COALESCE(insertId, ''),
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(COALESCE(insertId, CAST(timestamp AS STRING)))), 1, 16)) AS span_id,
    traceSampled AS trace_sampled,
    textPayload AS text_payload,
    TO_JSON_STRING(jsonpayload_v1beta1_insight) AS json_payload,
    CAST(NULL AS STRING) AS proto_payload,
    COALESCE(
        jsonpayload_v1beta1_insight.message,
        jsonpayload_v1beta1_insight.exceptioninfo.message,
        jsonpayload_v1beta1_insight.errorevent.message,
        textPayload,
        'Error Reporting Insight'
    ) AS display_message,
    'central_logging_v1' AS source_dataset,
    'clouderrorreporting_googleapis_com_insights' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.clouderrorreporting_googleapis_com_insights`

UNION ALL

-- =========================================
-- Cloud Scheduler (NEW in v2)
-- =========================================
SELECT
    insertId AS insert_id,
    timestamp AS event_timestamp,
    receiveTimestamp AS receive_timestamp,
    COALESCE(severity, 'INFO') AS severity,
    logName AS log_name,
    COALESCE(
        resource.labels.job_id,
        COALESCE(jsonpayload_logging_attemptstarted.jobname, jsonpayload_logging_attemptfinished.jobname),
        'cloud-scheduler'
    ) AS service_name,
    COALESCE(resource.type, 'cloud_scheduler_job') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            COALESCE(insertId, ''),
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(spanId, SUBSTR(TO_HEX(MD5(COALESCE(insertId, CAST(timestamp AS STRING)))), 1, 16)) AS span_id,
    traceSampled AS trace_sampled,
    textPayload AS text_payload,
    CASE
        WHEN jsonpayload_logging_attemptstarted IS NOT NULL
            THEN TO_JSON_STRING(jsonpayload_logging_attemptstarted)
        WHEN jsonpayload_logging_attemptfinished IS NOT NULL
            THEN TO_JSON_STRING(jsonpayload_logging_attemptfinished)
        ELSE NULL
    END AS json_payload,
    CAST(NULL AS STRING) AS proto_payload,
    COALESCE(
        CONCAT(
            'Job: ',
            COALESCE(jsonpayload_logging_attemptstarted.jobname, jsonpayload_logging_attemptfinished.jobname, 'unknown'),
            ' - ',
            CASE
                WHEN jsonpayload_logging_attemptstarted IS NOT NULL THEN 'Started'
                WHEN jsonpayload_logging_attemptfinished IS NOT NULL THEN
                    CONCAT('Finished: ', COALESCE(jsonpayload_logging_attemptfinished.status, 'unknown'))
                ELSE 'Unknown'
            END
        ),
        textPayload,
        'Scheduler Execution'
    ) AS display_message,
    'central_logging_v1' AS source_dataset,
    'cloudscheduler_googleapis_com_executions' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method
FROM `diatonic-ai-gcp.central_logging_v1.cloudscheduler_googleapis_com_executions`;
