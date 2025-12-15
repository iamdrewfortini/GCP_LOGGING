# Performance Guide for Canonical Log Queries

## Overview

This guide provides best practices for querying the canonical log view efficiently.

## Query Optimization

### 1. Always Filter on event_timestamp

The canonical view unions multiple source tables. Without a time filter, queries scan all partitions.

**Good:**
```sql
SELECT * FROM `org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
```

**Bad:**
```sql
SELECT * FROM `org_observability.logs_canonical_v2`
-- No time filter = full table scan
```

### 2. Select Only Required Columns

Avoid `SELECT *` - it retrieves all columns including large payloads.

**Good:**
```sql
SELECT event_timestamp, severity, service_name, display_message
FROM `org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
```

**Bad:**
```sql
SELECT * FROM `org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
```

### 3. Use Parameterized Queries

Parameterized queries enable query plan caching.

**Good:**
```python
query = """
    SELECT * FROM `org_observability.logs_canonical_v2`
    WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
    AND severity = @severity
    LIMIT @limit
"""
params = [
    bigquery.ScalarQueryParameter("hours", "INT64", 1),
    bigquery.ScalarQueryParameter("severity", "STRING", "ERROR"),
    bigquery.ScalarQueryParameter("limit", "INT64", 100),
]
```

### 4. Apply LIMIT

Always use LIMIT for interactive queries.

**Good:**
```sql
SELECT * FROM `org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
ORDER BY event_timestamp DESC
LIMIT 100
```

### 5. Filter Early (WHERE before HAVING)

Push filters to WHERE clause, not HAVING.

**Good:**
```sql
SELECT service_name, COUNT(*)
FROM `org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
  AND severity = 'ERROR'
GROUP BY service_name
```

**Bad:**
```sql
SELECT service_name, severity, COUNT(*) as cnt
FROM `org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY service_name, severity
HAVING severity = 'ERROR'  -- Filter should be in WHERE
```

## Cost Considerations

### Bytes Scanned

BigQuery charges by bytes scanned. Key strategies:

1. **Time filters** - Partition pruning
2. **Column selection** - Only scan needed columns
3. **Wildcard tables** - Avoid if possible

### Slot Usage

Complex queries consume more slots:

1. **Avoid CROSS JOIN**
2. **Limit window functions**
3. **Use approximate functions** (APPROX_COUNT_DISTINCT)

## Query Templates

### Basic Log Listing (Fast)
```sql
-- ~0.1 GB scanned for 1 hour window
SELECT
    event_timestamp,
    severity,
    service_name,
    display_message
FROM `org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
ORDER BY event_timestamp DESC
LIMIT 100
```

### Severity Aggregation
```sql
-- ~0.05 GB scanned (aggregation reduces output)
SELECT
    severity,
    COUNT(*) as count
FROM `org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY severity
ORDER BY count DESC
```

### Service Health Dashboard
```sql
-- ~0.1 GB scanned
SELECT
    service_name,
    COUNTIF(severity IN ('ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY')) as error_count,
    COUNT(*) as total_count,
    SAFE_DIVIDE(
        COUNTIF(severity IN ('ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY')),
        COUNT(*)
    ) * 100 as error_rate_pct
FROM `org_observability.logs_canonical_v2`
WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY service_name
ORDER BY error_count DESC
```

### Trace Lookup
```sql
-- Very fast if trace_id is known
SELECT *
FROM `org_observability.logs_canonical_v2`
WHERE trace_id = 'projects/diatonic-ai-gcp/traces/abc123...'
ORDER BY event_timestamp ASC
```

## Monitoring Query Performance

### Check Query Stats
```sql
SELECT
    job_id,
    total_bytes_processed,
    total_slot_ms,
    creation_time,
    end_time
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE statement_type = 'SELECT'
  AND creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
ORDER BY total_bytes_processed DESC
LIMIT 10
```

### Dry Run Validation
```python
# Always dry-run before executing
job_config = bigquery.QueryJobConfig(dry_run=True)
job = client.query(query, job_config=job_config)
print(f"Bytes to be processed: {job.total_bytes_processed}")
```

## Caching Strategies

### Application-Level Caching

For dashboard queries:
- Cache aggregation results for 1-5 minutes
- Use Redis or in-memory cache
- Invalidate on data refresh

### BigQuery Query Cache

BigQuery caches query results for 24 hours if:
- Deterministic query
- Table not modified
- Same query text

**Enable caching:**
```python
job_config = bigquery.QueryJobConfig(
    use_query_cache=True,
    use_legacy_sql=False
)
```

## Materialized Views (Future)

For high-frequency dashboards, consider materialized views:

```sql
CREATE MATERIALIZED VIEW `org_observability.mv_hourly_severity_counts`
PARTITION BY DATE(hour_bucket)
CLUSTER BY service_name
AS
SELECT
    TIMESTAMP_TRUNC(event_timestamp, HOUR) as hour_bucket,
    service_name,
    severity,
    COUNT(*) as count
FROM `org_observability.logs_canonical_v2`
GROUP BY hour_bucket, service_name, severity
```
