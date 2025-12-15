# Required Fields for Canonical Log Contract

## UI/API Requirements Analysis

Based on analysis of `templates/index.html` and `main.py`, the Glass Pane UI requires these fields:

## Minimum Required Fields

| Field Name | Type | Required For | UI Display |
|------------|------|--------------|------------|
| event_timestamp | TIMESTAMP | Sorting, filtering, display | "Timestamp" column |
| severity | STRING | Filtering, color coding | "Severity" badge |
| log_name | STRING | Service identification | "Service/Log" column |
| message | STRING | Log content display | "Message" column (truncated to 200 chars) |
| source_table | STRING | Provenance tracking | "Source" column |

## Extended Fields (For Full Functionality)

| Field Name | Type | Required For | Priority |
|------------|------|--------------|----------|
| insert_id | STRING | Deduplication, unique reference | HIGH |
| service_name | STRING | Service filtering, grouping | HIGH |
| trace_id | STRING | Distributed tracing correlation | MEDIUM |
| span_id | STRING | Span-level tracing | MEDIUM |
| json_payload | STRING | Detailed log inspection | MEDIUM |
| resource_type | STRING | Resource filtering | MEDIUM |
| resource_labels | JSON | Resource context | LOW |
| receive_timestamp | TIMESTAMP | Latency analysis | LOW |
| http_request | JSON | HTTP request details | LOW |

## Canonical Contract v1.0 Schema

```sql
CREATE OR REPLACE VIEW `{PROJECT}.{DATASET}.logs_canonical_v1` AS
SELECT
    -- Identity & Provenance
    insert_id,                          -- STRING: Unique identifier
    source_dataset,                     -- STRING: Source dataset name
    source_table,                       -- STRING: Source table name
    source_bucket,                      -- STRING: Log Analytics bucket (if applicable)
    ingestion_method,                   -- STRING: 'sink' | 'linked' | 'direct'

    -- Timestamps
    event_timestamp,                    -- TIMESTAMP: When event occurred
    receive_timestamp,                  -- TIMESTAMP: When event received (nullable)

    -- Classification
    severity,                           -- STRING: DEFAULT/DEBUG/INFO/NOTICE/WARNING/ERROR/CRITICAL/ALERT/EMERGENCY
    log_name,                           -- STRING: Full log name path

    -- Service Context
    service_name,                       -- STRING: Service identifier
    resource_type,                      -- STRING: GCP resource type
    resource_labels,                    -- JSON: Resource labels as JSON string

    -- Tracing
    trace_id,                           -- STRING: Trace identifier
    span_id,                            -- STRING: Span identifier
    trace_sampled,                      -- BOOLEAN: Whether trace was sampled

    -- Payloads (normalized)
    text_payload,                       -- STRING: Plain text content
    json_payload,                       -- STRING: JSON content as string
    proto_payload,                      -- STRING: Proto content as JSON string

    -- Display
    display_message,                    -- STRING: Human-readable summary

    -- Raw (for forward compatibility)
    raw_json                            -- STRING: Complete raw entry as JSON
FROM ...
```

## Field Mapping Requirements

Each source table must map to canonical fields using:

### Timestamp Handling
```sql
-- Always use event timestamp, not receive timestamp for display
COALESCE(timestamp, receiveTimestamp) AS event_timestamp
```

### Severity Normalization
```sql
-- Ensure consistent severity values
UPPER(COALESCE(severity, 'DEFAULT')) AS severity
```

### Payload Normalization
```sql
-- Convert all payloads to STRING
COALESCE(
    textPayload,
    SAFE.TO_JSON_STRING(jsonPayload),
    SAFE.TO_JSON_STRING(protoPayload)
) AS json_payload
```

### Service Name Extraction
```sql
-- Extract service name from various sources
COALESCE(
    resource.labels.service_name,
    resource.labels.module_id,
    REGEXP_EXTRACT(logName, r'projects/[^/]+/logs/(.*)'),
    'unknown'
) AS service_name
```

## Validation Rules

1. **event_timestamp** must not be NULL
2. **severity** must be one of: DEFAULT, DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL, ALERT, EMERGENCY
3. **insert_id** should be unique within a time window
4. **source_table** must always be populated for provenance
