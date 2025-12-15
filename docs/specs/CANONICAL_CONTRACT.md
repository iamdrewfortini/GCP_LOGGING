# Canonical Log Contract Specification

**Version:** 2.0.0
**Date:** 2025-12-14
**Status:** Approved for Implementation

## Overview

The Canonical Log Contract defines a unified schema for accessing log data across all GCP logging sources. This abstraction layer enables the Glass Pane service and other consumers to query logs without knowledge of underlying schema variations.

## Contract Location

```
View Name: org_observability.logs_canonical_v2
Project: diatonic-ai-gcp
Location: US
```

## Schema Definition

### Core Fields

| Field | Type | Mode | Description |
|-------|------|------|-------------|
| `insert_id` | STRING | REQUIRED | Unique log entry identifier |
| `event_timestamp` | TIMESTAMP | REQUIRED | When the event occurred |
| `severity` | STRING | REQUIRED | Normalized severity level |
| `log_name` | STRING | REQUIRED | Full log name path |
| `service_name` | STRING | REQUIRED | Service identifier |
| `display_message` | STRING | REQUIRED | Human-readable summary |

### Extended Fields

| Field | Type | Mode | Description |
|-------|------|------|-------------|
| `receive_timestamp` | TIMESTAMP | NULLABLE | When log was received |
| `resource_type` | STRING | NULLABLE | GCP resource type |
| `resource_labels` | STRING | NULLABLE | Labels as JSON string |
| `trace_id` | STRING | NULLABLE | Distributed trace ID |
| `span_id` | STRING | NULLABLE | Span ID within trace |
| `trace_sampled` | BOOL | NULLABLE | Whether trace was sampled |

### Payload Fields

| Field | Type | Mode | Description |
|-------|------|------|-------------|
| `text_payload` | STRING | NULLABLE | Plain text content |
| `json_payload` | STRING | NULLABLE | JSON content as string |
| `proto_payload` | STRING | NULLABLE | Proto as JSON string |

### Provenance Fields

| Field | Type | Mode | Description |
|-------|------|------|-------------|
| `source_dataset` | STRING | REQUIRED | Originating dataset |
| `source_table` | STRING | REQUIRED | Originating table |
| `source_bucket` | STRING | NULLABLE | Log Analytics bucket |
| `ingestion_method` | STRING | REQUIRED | sink/linked/direct |

## Severity Values

The `severity` field uses Google Cloud Logging standard values:

| Value | Numeric | Description |
|-------|---------|-------------|
| DEFAULT | 0 | Default log level |
| DEBUG | 100 | Debug information |
| INFO | 200 | Routine information |
| NOTICE | 300 | Normal but significant |
| WARNING | 400 | Warning conditions |
| ERROR | 500 | Error conditions |
| CRITICAL | 600 | Critical conditions |
| ALERT | 700 | Action required |
| EMERGENCY | 800 | System unusable |

## Source Table Coverage

### Covered Tables (v2.0)

| Table | Payload Type | Service Name Source |
|-------|--------------|---------------------|
| cloudaudit_googleapis_com_activity | protoPayload | resource.labels.service_name |
| cloudaudit_googleapis_com_data_access | protopayload_auditlog | protopayload_auditlog.serviceName |
| cloudaudit_googleapis_com_system_event | protopayload_auditlog | protopayload_auditlog.serviceName |
| run_googleapis_com_stdout | jsonPayload/textPayload | resource.labels.service_name |
| run_googleapis_com_stderr | jsonPayload/textPayload | resource.labels.service_name |
| run_googleapis_com_requests | httpRequest | resource.labels.service_name |
| run_googleapis_com_varlog_system | textPayload | resource.labels.service_name |
| syslog | jsonPayload/textPayload | 'compute' (hardcoded) |
| cloudbuild | textPayload | 'cloudbuild' (hardcoded) |
| clouderrorreporting_googleapis_com_insights | jsonpayload_v1beta1_insight | resource.labels.project_id |
| cloudscheduler_googleapis_com_executions | jsonpayload_logging_* | resource.labels.job_id |

## Query Examples

### Basic Log Listing
```sql
SELECT
    event_timestamp,
    severity,
    service_name,
    display_message
FROM `diatonic-ai-gcp.org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
ORDER BY event_timestamp DESC
LIMIT 100
```

### Filter by Severity
```sql
SELECT *
FROM `diatonic-ai-gcp.org_observability.logs_canonical_v2`
WHERE severity IN ('ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY')
  AND event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
ORDER BY event_timestamp DESC
```

### Group by Service
```sql
SELECT
    service_name,
    severity,
    COUNT(*) as log_count
FROM `diatonic-ai-gcp.org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY service_name, severity
ORDER BY log_count DESC
```

### Trace Correlation
```sql
SELECT *
FROM `diatonic-ai-gcp.org_observability.logs_canonical_v2`
WHERE trace_id = 'projects/diatonic-ai-gcp/traces/abc123...'
ORDER BY event_timestamp ASC
```

## Backward Compatibility

### Legacy View (v1.0)

The original `central_logging_v1.view_canonical_logs` remains available with the following mapping:

| v1 Field | v2 Field |
|----------|----------|
| insertId | insert_id |
| event_ts | event_timestamp |
| severity | severity |
| source_table | source_table |
| service | service_name |
| trace | trace_id |
| spanId | span_id |
| logName | log_name |
| json_payload_str | json_payload |
| display_message | display_message |

## Versioning Strategy

1. **Minor versions** (v2.1, v2.2): Add nullable fields, fix bugs
2. **Major versions** (v3.0): Schema-breaking changes require new view
3. **Deprecation**: Old views remain for 90 days after new version release

## Performance Considerations

1. **Partition Pruning**: Always filter on `event_timestamp`
2. **Avoid SELECT ***: Select only required fields
3. **Limit Results**: Use LIMIT for interactive queries
4. **Prefer WHERE over HAVING**: Push filters to source tables

## Adding New Tables

To add a new source table to the canonical view:

1. Analyze schema using `bq show --schema`
2. Create mapping view in `infra/bigquery/mapping_views/`
3. Add UNION ALL to `02_canonical_contract.sql`
4. Update `meta_source_catalog_v1` table
5. Test with dry-run query
6. Deploy view update
