-- Mapping View: Cloud Scheduler Executions -> Canonical Schema
-- Project: diatonic-ai-gcp
-- Source: central_logging_v1.cloudscheduler_googleapis_com_executions
-- Version: 1.0.0
-- Date: 2025-12-14

CREATE OR REPLACE VIEW `diatonic-ai-gcp.central_logging_v1.map_cloudscheduler_to_canonical_v1` AS
SELECT
    -- Identity
    insertId AS insert_id,

    -- Timestamps
    timestamp AS event_timestamp,
    receiveTimestamp AS receive_timestamp,

    -- Classification
    COALESCE(severity, 'INFO') AS severity,
    logName AS log_name,

    -- Service Context
    COALESCE(
        resource.labels.job_id,
        COALESCE(jsonpayload_logging_attemptstarted.jobname, jsonpayload_logging_attemptfinished.jobname),
        'cloud-scheduler'
    ) AS service_name,
    COALESCE(resource.type, 'cloud_scheduler_job') AS resource_type,
    TO_JSON_STRING(resource.labels) AS resource_labels,

    -- Tracing
    COALESCE(
        trace,
        CONCAT('projects/diatonic-ai-gcp/traces/', SUBSTR(TO_HEX(MD5(CONCAT(
            COALESCE(insertId, ''),
            '-',
            CAST(TIMESTAMP_TRUNC(timestamp, MINUTE) AS STRING)
        ))), 1, 32))
    ) AS trace_id,
    COALESCE(
        spanId,
        SUBSTR(TO_HEX(MD5(COALESCE(insertId, CAST(timestamp AS STRING)))), 1, 16)
    ) AS span_id,
    traceSampled AS trace_sampled,

    -- Payloads (normalized) - merge both payload types
    textPayload AS text_payload,
    CASE
        WHEN jsonpayload_logging_attemptstarted IS NOT NULL
            THEN TO_JSON_STRING(jsonpayload_logging_attemptstarted)
        WHEN jsonpayload_logging_attemptfinished IS NOT NULL
            THEN TO_JSON_STRING(jsonpayload_logging_attemptfinished)
        ELSE NULL
    END AS json_payload,
    CAST(NULL AS STRING) AS proto_payload,

    -- Display message extraction
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

    -- Provenance
    'central_logging_v1' AS source_dataset,
    'cloudscheduler_googleapis_com_executions' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method

FROM `diatonic-ai-gcp.central_logging_v1.cloudscheduler_googleapis_com_executions`
WHERE timestamp IS NOT NULL;
