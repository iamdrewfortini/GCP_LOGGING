-- Mapping View: Cloud Error Reporting Insights -> Canonical Schema
-- Project: diatonic-ai-gcp
-- Source: central_logging_v1.clouderrorreporting_googleapis_com_insights
-- Version: 1.0.0
-- Date: 2025-12-14

CREATE OR REPLACE VIEW `diatonic-ai-gcp.central_logging_v1.map_clouderrorreporting_to_canonical_v1` AS
SELECT
    -- Identity
    insertId AS insert_id,

    -- Timestamps
    timestamp AS event_timestamp,
    receiveTimestamp AS receive_timestamp,

    -- Classification
    COALESCE(severity, 'ERROR') AS severity,
    logName AS log_name,

    -- Service Context
    COALESCE(
        resource.labels.project_id,
        'error-reporting'
    ) AS service_name,
    COALESCE(resource.type, 'global') AS resource_type,
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

    -- Payloads (normalized)
    textPayload AS text_payload,
    TO_JSON_STRING(jsonpayload_v1beta1_insight) AS json_payload,
    CAST(NULL AS STRING) AS proto_payload,

    -- Display message extraction
    COALESCE(
        jsonpayload_v1beta1_insight.message,
        jsonpayload_v1beta1_insight.exceptioninfo.message,
        jsonpayload_v1beta1_insight.errorevent.message,
        textPayload,
        'Error Reporting Insight'
    ) AS display_message,

    -- Provenance
    'central_logging_v1' AS source_dataset,
    'clouderrorreporting_googleapis_com_insights' AS source_table,
    CAST(NULL AS STRING) AS source_bucket,
    'sink' AS ingestion_method

FROM `diatonic-ai-gcp.central_logging_v1.clouderrorreporting_googleapis_com_insights`
WHERE timestamp IS NOT NULL;
