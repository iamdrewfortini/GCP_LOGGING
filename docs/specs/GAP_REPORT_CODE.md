# Code Gap Analysis Report

## Executive Summary

The Glass Pane service (`main.py`) has a **critical architectural flaw**: it attempts dynamic schema discovery and query construction at runtime instead of using the existing canonical view `view_canonical_logs` which already provides schema unification.

## Key Findings

### 1. Existing Canonical View (NOT USED)

A well-designed canonical view already exists:
```
diatonic-ai-gcp.central_logging_v1.view_canonical_logs
```

**Canonical Schema:**
| Field | Type | Description |
|-------|------|-------------|
| insertId | STRING | Unique log entry identifier |
| event_ts | TIMESTAMP | Event timestamp |
| severity | STRING | Log severity level |
| source_table | STRING | Originating table name |
| service | STRING | Service name |
| trace | STRING | Trace ID (with synthetic fallback) |
| spanId | STRING | Span ID (with synthetic fallback) |
| logName | STRING | Log name |
| json_payload_str | STRING | JSON payload as string |
| display_message | STRING | Human-readable message |

### 2. Current Service Implementation Issues

**File:** `/home/daclab-ai/GCP_LOGGING/app/glass-pane/main.py`

#### Issue 2.1: Dynamic Schema Discovery (Lines 62-177)
```python
# PROBLEMATIC: Dynamically queries INFORMATION_SCHEMA for every request
tables_query = f"""
    SELECT table_name
    FROM `{PROJECT_ID}.{dataset_id}.INFORMATION_SCHEMA.TABLES`
    WHERE table_type = 'BASE TABLE'
"""
```
**Impact:**
- Runtime failures when table schemas don't match assumptions
- Performance overhead (multiple metadata queries per request)
- Brittleness to schema changes

#### Issue 2.2: Hardcoded Column Assumptions (Lines 99-130)
```python
# FRAGILE: Assumes specific columns exist
column_name IN ('timestamp', 'severity', 'logName', 'log_name',
               'textPayload', 'jsonPayload', 'protoPayload')
```
**Impact:**
- Fails on tables with different payload structures (e.g., `jsonpayload_v1beta1_insight`)
- Misses columns like `protopayload_auditlog`

#### Issue 2.3: Missing Dataset Configuration (Lines 15)
```python
KNOWN_DATASETS = ["central_logging_v1", "org_observability", "org_finops", "org_agent"]
```
**Impact:**
- Hardcoded list doesn't reflect actual queryable datasets
- Log Analytics linked datasets (_*) have different schemas

### 3. Schema Variations Discovered

| Table | Has jsonPayload | Has textPayload | Has protoPayload | Payload Field Name |
|-------|-----------------|-----------------|------------------|-------------------|
| syslog | JSON | STRING | - | jsonPayload |
| run_stdout | JSON | STRING | - | jsonPayload |
| cloudaudit_activity | - | - | RECORD | protoPayload |
| cloudaudit_data_access | - | - | RECORD | protopayload_auditlog |
| clouderrorreporting | - | STRING | - | jsonpayload_v1beta1_insight |
| cloudscheduler | - | STRING | - | jsonpayload_logging_attemptstarted |

### 4. Log Analytics Linked Datasets

**Critical Finding:** The 3 Log Analytics linked datasets contain **ephemeral query result tables**, NOT raw log data.

| Dataset ID | Content Type | Queryable as Logs |
|------------|--------------|-------------------|
| _1f6e581e1c8cdfee0ea501083a6509e8201c9423 | Query cache | NO |
| _a3d514c3dcba802a157fa22a2742f288c8e4133c | Query cache | NO |
| _bb367ebfb354adc186272bc63bcdb86d98c29ab9 | Query cache | NO |

### 5. Tables Missing from Canonical View

The existing `view_canonical_logs` does NOT include:
1. `clouderrorreporting_googleapis_com_insights`
2. `cloudscheduler_googleapis_com_executions`
3. `glass_pane_test`

## Missing Abstraction Layers

1. **No Query Builder Layer**
   - Queries constructed via string concatenation
   - No parameterized query templates
   - No query validation before execution

2. **No Dataset Registry**
   - No configuration-driven dataset enumeration
   - No schema validation at startup
   - No versioning for canonical contract

3. **No Error Handling Abstraction**
   - Raw BigQuery errors exposed to users
   - No structured error responses
   - No correlation IDs for debugging

4. **No Caching Layer**
   - Every request hits BigQuery
   - No metadata caching
   - No query result caching

## Missing Tests

1. No unit tests for query construction
2. No integration tests against BigQuery
3. No schema compatibility regression tests
4. No end-to-end API tests

## Missing Config Validation

1. Environment variables not validated at startup
2. No schema version checking
3. No dataset availability validation

## Recommendations

1. **Immediate:** Refactor service to use `view_canonical_logs` directly
2. **Short-term:** Update canonical view to include missing tables
3. **Medium-term:** Add query builder abstraction with templates
4. **Long-term:** Implement comprehensive test suite
