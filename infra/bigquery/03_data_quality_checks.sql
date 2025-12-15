-- Data Quality Checks for Canonical Log View
-- Project: diatonic-ai-gcp
-- Version: 1.0.0
-- Date: 2025-12-14

-- =============================================================================
-- DQ Check 1: Null Timestamp Rate
-- Target: < 0.01% null event_timestamp
-- =============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_observability.dq_null_timestamp_rate_v1` AS
SELECT
    source_table,
    COUNT(*) as total_rows,
    COUNTIF(event_timestamp IS NULL) as null_timestamp_count,
    SAFE_DIVIDE(COUNTIF(event_timestamp IS NULL), COUNT(*)) * 100 as null_timestamp_pct
FROM `diatonic-ai-gcp.org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
   OR event_timestamp IS NULL
GROUP BY source_table
HAVING null_timestamp_pct > 0
ORDER BY null_timestamp_pct DESC;

-- =============================================================================
-- DQ Check 2: Invalid Severity Rate
-- Target: 0% invalid severity values
-- =============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_observability.dq_invalid_severity_v1` AS
SELECT
    source_table,
    severity,
    COUNT(*) as count
FROM `diatonic-ai-gcp.org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
  AND severity NOT IN ('DEFAULT', 'DEBUG', 'INFO', 'NOTICE', 'WARNING', 'ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY')
GROUP BY source_table, severity
ORDER BY count DESC;

-- =============================================================================
-- DQ Check 3: Missing Service Name Rate
-- Target: < 1% null/empty service_name
-- =============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_observability.dq_missing_service_name_v1` AS
SELECT
    source_table,
    COUNT(*) as total_rows,
    COUNTIF(service_name IS NULL OR service_name = '') as missing_service_count,
    SAFE_DIVIDE(COUNTIF(service_name IS NULL OR service_name = ''), COUNT(*)) * 100 as missing_service_pct
FROM `diatonic-ai-gcp.org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY source_table
HAVING missing_service_pct > 0
ORDER BY missing_service_pct DESC;

-- =============================================================================
-- DQ Check 4: Invalid JSON Payload Rate
-- Target: < 0.1% invalid JSON in json_payload
-- =============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_observability.dq_invalid_json_payload_v1` AS
SELECT
    source_table,
    COUNT(*) as total_rows,
    COUNTIF(
        json_payload IS NOT NULL
        AND json_payload != ''
        AND json_payload != '{}'
        AND SAFE.PARSE_JSON(json_payload) IS NULL
    ) as invalid_json_count,
    SAFE_DIVIDE(
        COUNTIF(
            json_payload IS NOT NULL
            AND json_payload != ''
            AND json_payload != '{}'
            AND SAFE.PARSE_JSON(json_payload) IS NULL
        ),
        COUNT(*)
    ) * 100 as invalid_json_pct
FROM `diatonic-ai-gcp.org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY source_table
HAVING invalid_json_count > 0
ORDER BY invalid_json_pct DESC;

-- =============================================================================
-- DQ Check 5: Duplicate Insert ID Rate (within 1 hour window)
-- Target: < 0.01% duplicates
-- =============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_observability.dq_duplicate_insert_id_v1` AS
WITH duplicates AS (
    SELECT
        insert_id,
        source_table,
        COUNT(*) as occurrence_count
    FROM `diatonic-ai-gcp.org_observability.logs_canonical_v2`
    WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
    GROUP BY insert_id, source_table
    HAVING COUNT(*) > 1
)
SELECT
    source_table,
    COUNT(DISTINCT insert_id) as duplicate_ids,
    SUM(occurrence_count) as total_duplicate_rows
FROM duplicates
GROUP BY source_table
ORDER BY total_duplicate_rows DESC;

-- =============================================================================
-- DQ Check 6: Ingestion Latency (receive_timestamp - event_timestamp)
-- Target: P95 < 60 seconds
-- =============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_observability.dq_ingestion_latency_v1` AS
SELECT
    source_table,
    COUNT(*) as total_rows,
    AVG(TIMESTAMP_DIFF(receive_timestamp, event_timestamp, SECOND)) as avg_latency_sec,
    APPROX_QUANTILES(TIMESTAMP_DIFF(receive_timestamp, event_timestamp, SECOND), 100)[OFFSET(50)] as p50_latency_sec,
    APPROX_QUANTILES(TIMESTAMP_DIFF(receive_timestamp, event_timestamp, SECOND), 100)[OFFSET(95)] as p95_latency_sec,
    APPROX_QUANTILES(TIMESTAMP_DIFF(receive_timestamp, event_timestamp, SECOND), 100)[OFFSET(99)] as p99_latency_sec
FROM `diatonic-ai-gcp.org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
  AND receive_timestamp IS NOT NULL
GROUP BY source_table
ORDER BY p95_latency_sec DESC;

-- =============================================================================
-- DQ Summary View - Aggregated Health Check
-- =============================================================================

CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_observability.dq_summary_v1` AS
SELECT
    'data_quality_summary' as check_type,
    CURRENT_TIMESTAMP() as check_timestamp,
    (SELECT COUNT(*) FROM `diatonic-ai-gcp.org_observability.dq_null_timestamp_rate_v1`) as tables_with_null_timestamps,
    (SELECT COUNT(*) FROM `diatonic-ai-gcp.org_observability.dq_invalid_severity_v1`) as invalid_severity_count,
    (SELECT COUNT(*) FROM `diatonic-ai-gcp.org_observability.dq_missing_service_name_v1`) as tables_with_missing_service,
    (SELECT COUNT(*) FROM `diatonic-ai-gcp.org_observability.dq_duplicate_insert_id_v1`) as tables_with_duplicates,
    CASE
        WHEN (SELECT COUNT(*) FROM `diatonic-ai-gcp.org_observability.dq_null_timestamp_rate_v1`) = 0
         AND (SELECT COUNT(*) FROM `diatonic-ai-gcp.org_observability.dq_invalid_severity_v1`) = 0
        THEN 'HEALTHY'
        ELSE 'DEGRADED'
    END as overall_status;
