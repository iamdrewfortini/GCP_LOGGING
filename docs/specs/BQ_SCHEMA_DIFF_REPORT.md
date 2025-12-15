# BigQuery Schema Inventory & Diff Report

**Generated:** 2025-12-14
**Project:** diatonic-ai-gcp
**Location:** US

## Dataset Inventory

### Regular Datasets

| Dataset ID | Tables | Views | Description |
|------------|--------|-------|-------------|
| central_logging_v1 | 12 | 1 | Central logging destination for org sinks |
| org_observability | 0 | 0 | Reserved for observability artifacts |
| org_finops | 0 | 0 | Reserved for FinOps data |
| org_agent | 0 | 0 | Reserved for agent data |
| org_logs | 0 | 0 | Reserved (legacy) |

### Log Analytics Linked Datasets

| Dataset ID | Bucket | Content |
|------------|--------|---------|
| _1f6e581e1c8cdfee0ea501083a6509e8201c9423 | _Default | Query cache (ephemeral) |
| _a3d514c3dcba802a157fa22a2742f288c8e4133c | _Required | Query cache (ephemeral) |
| _bb367ebfb354adc186272bc63bcdb86d98c29ab9 | dacvisuals-org-logs | Query cache (ephemeral) |

**Note:** Log Analytics linked datasets do NOT contain raw log tables. They contain temporary query result caches with 24-hour expiration.

## Table Schema Inventory

### central_logging_v1.syslog

| Column | Type | Mode |
|--------|------|------|
| timestamp | TIMESTAMP | NULLABLE |
| severity | STRING | NULLABLE |
| trace | STRING | NULLABLE |
| spanId | STRING | NULLABLE |
| textPayload | STRING | NULLABLE |
| jsonPayload | JSON | NULLABLE |

**Partitioning:** DAY on `timestamp`

### central_logging_v1.cloudaudit_googleapis_com_activity

| Column | Type | Mode |
|--------|------|------|
| timestamp | TIMESTAMP | NULLABLE |
| severity | STRING | NULLABLE |
| trace | STRING | NULLABLE |
| spanId | STRING | NULLABLE |
| protoPayload | RECORD | NULLABLE |
| resource | RECORD | NULLABLE |
| logName | STRING | NULLABLE |

**Notable:** Uses `protoPayload` (RECORD), not jsonPayload

### central_logging_v1.run_googleapis_com_stdout

| Column | Type | Mode |
|--------|------|------|
| timestamp | TIMESTAMP | NULLABLE |
| severity | STRING | NULLABLE |
| trace | STRING | NULLABLE |
| spanId | STRING | NULLABLE |
| textPayload | STRING | NULLABLE |
| jsonPayload | JSON | NULLABLE |
| resource | RECORD | NULLABLE |

**Resource Labels:** service_name

### central_logging_v1.run_googleapis_com_stderr

Same schema as `run_googleapis_com_stdout`

### central_logging_v1.run_googleapis_com_requests

| Column | Type | Mode |
|--------|------|------|
| timestamp | TIMESTAMP | NULLABLE |
| severity | STRING | NULLABLE |
| trace | STRING | NULLABLE |
| spanId | STRING | NULLABLE |
| httpRequest | RECORD | NULLABLE |
| resource | RECORD | NULLABLE |
| logName | STRING | NULLABLE |
| insertId | STRING | NULLABLE |
| labels | RECORD | NULLABLE |

**Notable:** Has `httpRequest` structure, `insertId` native

### central_logging_v1.cloudbuild

| Column | Type | Mode |
|--------|------|------|
| timestamp | TIMESTAMP | NULLABLE |
| severity | STRING | NULLABLE |
| trace | STRING | NULLABLE |
| spanId | STRING | NULLABLE |
| textPayload | STRING | NULLABLE |
| logName | STRING | NULLABLE |
| resource | RECORD | NULLABLE |
| insertId | STRING | NULLABLE |
| receiveTimestamp | TIMESTAMP | NULLABLE |

**Resource Labels:** build_id, build_trigger_id, project_id

### central_logging_v1.clouderrorreporting_googleapis_com_insights

| Column | Type | Mode |
|--------|------|------|
| timestamp | TIMESTAMP | NULLABLE |
| severity | STRING | NULLABLE |
| trace | STRING | NULLABLE |
| spanId | STRING | NULLABLE |
| textPayload | STRING | NULLABLE |
| **jsonpayload_v1beta1_insight** | RECORD | NULLABLE |
| resource | RECORD | NULLABLE |
| insertId | STRING | NULLABLE |
| labels | RECORD | NULLABLE |

**Notable:** Uses non-standard payload field `jsonpayload_v1beta1_insight`

### central_logging_v1.cloudscheduler_googleapis_com_executions

| Column | Type | Mode |
|--------|------|------|
| timestamp | TIMESTAMP | NULLABLE |
| severity | STRING | NULLABLE |
| trace | STRING | NULLABLE |
| spanId | STRING | NULLABLE |
| textPayload | STRING | NULLABLE |
| **jsonpayload_logging_attemptstarted** | RECORD | NULLABLE |
| **jsonpayload_logging_attemptfinished** | RECORD | NULLABLE |
| resource | RECORD | NULLABLE |
| insertId | STRING | NULLABLE |

**Notable:** Uses TWO non-standard payload fields

## Schema Diff Analysis

### Payload Field Variations

| Table | Standard Fields | Non-Standard Fields |
|-------|-----------------|---------------------|
| syslog | jsonPayload, textPayload | - |
| run_stdout | jsonPayload, textPayload | - |
| run_stderr | jsonPayload, textPayload | - |
| run_requests | - | httpRequest |
| run_varlog | textPayload | - |
| cloudaudit_activity | protoPayload | - |
| cloudaudit_data_access | - | protopayload_auditlog |
| cloudaudit_system_event | - | protopayload_auditlog |
| cloudbuild | textPayload | - |
| clouderrorreporting | textPayload | jsonpayload_v1beta1_insight |
| cloudscheduler | textPayload | jsonpayload_logging_attemptstarted, jsonpayload_logging_attemptfinished |

### Resource Labels Variations

| Table | Available Labels |
|-------|------------------|
| syslog | (none) |
| run_* | service_name, revision_name, configuration_name, location, project_id |
| cloudaudit_* | service_name, module_id, project_id, method, service |
| cloudbuild | build_id, build_trigger_id, project_id |
| cloudscheduler | location, project_id, job_id |

### Common Fields Across All Tables

| Field | Present In All | Notes |
|-------|----------------|-------|
| timestamp | YES | Partitioning key |
| severity | YES | Consistent STRING type |
| trace | YES | Nullable, sometimes synthetic needed |
| spanId | YES | Nullable, sometimes synthetic needed |
| resource.type | MOST | Missing in some tables |

### Divergent Fields

| Divergence | Tables Affected | Impact |
|------------|-----------------|--------|
| No insertId | syslog, run_stdout, run_stderr | Must generate synthetic ID |
| No logName | run_stdout, run_stderr, run_varlog | Must use hardcoded value |
| No resource | syslog | Must use fallback for service name |
| Non-standard payload | 4 tables | Requires special handling |

## Existing Canonical View Coverage

**View:** `central_logging_v1.view_canonical_logs`

### Covered Tables

| Table | Mapped | Notes |
|-------|--------|-------|
| cloudaudit_googleapis_com_activity | YES | Uses protoPayload |
| cloudaudit_googleapis_com_data_access | YES | Uses protopayload_auditlog |
| cloudaudit_googleapis_com_system_event | YES | Uses protopayload_auditlog |
| run_googleapis_com_stdout | YES | - |
| run_googleapis_com_stderr | YES | - |
| run_googleapis_com_requests | YES | Uses httpRequest |
| run_googleapis_com_varlog_system | YES | - |
| syslog | YES | - |
| cloudbuild | YES | - |

### NOT Covered (Gap)

| Table | Reason | Action Required |
|-------|--------|-----------------|
| clouderrorreporting_googleapis_com_insights | Non-standard payload | Add mapping |
| cloudscheduler_googleapis_com_executions | Non-standard payload | Add mapping |
| glass_pane_test | Unknown purpose | Evaluate & add if needed |

## Recommendations

1. **Update canonical view** to include clouderrorreporting and cloudscheduler tables
2. **Do NOT query Log Analytics linked datasets directly** - use Log Analytics UI/API instead
3. **Service should query ONLY the canonical view** - remove dynamic discovery
4. **Add schema versioning** to track canonical contract changes
