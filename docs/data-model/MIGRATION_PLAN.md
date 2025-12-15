# Migration Plan: Universal Data Envelope Implementation

**Date:** 2025-12-15
**Project:** diatonic-ai-gcp
**Status:** Ready for Execution

---

## Overview

This migration plan implements the Universal Data Envelope across the Glass Pane observability platform. It follows a **safe, incremental, reversible** approach with zero downtime.

### Guiding Principles

1. **No breaking changes** - All changes are additive
2. **Views over rewrites** - Create canonical views, don't modify raw tables
3. **Backward compatible** - Existing queries continue to work
4. **Reversible** - Each step can be rolled back independently
5. **Incremental** - Small steps with validation between each

---

## Pre-Migration Checklist

- [ ] Backup `master_logs` schema definition
- [ ] Document current row counts per table
- [ ] Verify BigQuery admin permissions
- [ ] Notify team of migration window
- [ ] Ensure ETL pipeline is healthy (check `etl_jobs` table)

### Current State Snapshot

```bash
# Run before migration to capture baseline
bq query --use_legacy_sql=false \
  "SELECT table_id, row_count, TIMESTAMP_MILLIS(last_modified_time)
   FROM \`diatonic-ai-gcp.central_logging_v1.__TABLES__\`"
```

---

## Migration Steps

### Phase 1: Schema Preparation (Reversible)

**Duration:** ~5 minutes
**Risk:** Low
**Rollback:** DROP COLUMN

#### Step 1.1: Create `org_logs_norm` Dataset

```sql
CREATE SCHEMA IF NOT EXISTS `diatonic-ai-gcp.org_logs_norm`
OPTIONS (
  description = 'Normalized log views with Universal Data Envelope',
  labels = [('team', 'observability'), ('env', 'production')]
);
```

**Validation:**
```sql
SELECT schema_name, creation_time
FROM `diatonic-ai-gcp.INFORMATION_SCHEMA.SCHEMATA`
WHERE schema_name = 'org_logs_norm';
```

**Rollback:**
```sql
DROP SCHEMA IF EXISTS `diatonic-ai-gcp.org_logs_norm`;
```

#### Step 1.2: Add New Columns to master_logs

```sql
-- Run each ALTER separately to isolate failures
ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS schema_version STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS environment STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS correlation_request_id STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS correlation_session_id STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS correlation_conversation_id STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS privacy_pii_risk STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS privacy_redaction_state STRING;

ALTER TABLE `diatonic-ai-gcp.central_logging_v1.master_logs`
ADD COLUMN IF NOT EXISTS privacy_retention_class STRING;
```

**Validation:**
```sql
SELECT column_name, data_type, is_nullable
FROM `diatonic-ai-gcp.central_logging_v1.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'master_logs'
  AND column_name IN ('schema_version', 'environment', 'correlation_request_id',
                      'privacy_pii_risk', 'privacy_redaction_state');
```

**Rollback:** (Not recommended - columns are nullable and harmless)
```sql
-- Only if absolutely necessary - this loses data!
-- ALTER TABLE ... DROP COLUMN is not supported in BigQuery
-- Must recreate table without columns (expensive operation)
```

---

### Phase 2: Create Helper Functions (Reversible)

**Duration:** ~2 minutes
**Risk:** Low
**Rollback:** DROP FUNCTION

#### Step 2.1: Create UDFs

```sql
-- UDF: Parse labels JSON into ARRAY<STRUCT<k, v>>
CREATE OR REPLACE FUNCTION `diatonic-ai-gcp.org_logs_norm.fn_labels_to_array`(labels_json STRING)
RETURNS ARRAY<STRUCT<k STRING, v STRING>>
LANGUAGE js AS r"""
  if (!labels_json) return [];
  try {
    const obj = JSON.parse(labels_json);
    return Object.entries(obj).map(([k, v]) => ({k: k, v: String(v)}));
  } catch (e) {
    return [];
  }
""";

-- UDF: Extract tenant_id from labels
CREATE OR REPLACE FUNCTION `diatonic-ai-gcp.org_logs_norm.fn_extract_tenant_id`(labels_json STRING)
RETURNS STRING
LANGUAGE js AS r"""
  if (!labels_json) return null;
  try {
    const obj = JSON.parse(labels_json);
    return obj.tenant_id || obj.tenantId || obj.tenant || null;
  } catch (e) {
    return null;
  }
""";

-- UDF: Determine environment
CREATE OR REPLACE FUNCTION `diatonic-ai-gcp.org_logs_norm.fn_derive_environment`(
  project_id STRING, labels_json STRING, service_name STRING
)
RETURNS STRING
LANGUAGE js AS r"""
  if (labels_json) {
    try {
      const obj = JSON.parse(labels_json);
      if (obj.env) return obj.env;
      if (obj.environment) return obj.environment;
    } catch (e) {}
  }
  if (service_name) {
    const s = service_name.toLowerCase();
    if (s.includes('-dev') || s.includes('_dev')) return 'dev';
    if (s.includes('-staging') || s.includes('_staging')) return 'staging';
  }
  return 'prod';
""";

-- UDF: Classify PII risk (SQL, no JS)
CREATE OR REPLACE FUNCTION `diatonic-ai-gcp.org_logs_norm.fn_classify_pii_risk`(
  message STRING, json_payload STRING
)
RETURNS STRING
AS (
  CASE
    WHEN message IS NULL AND json_payload IS NULL THEN 'none'
    WHEN REGEXP_CONTAINS(COALESCE(message, '') || COALESCE(json_payload, ''),
         r'(?i)(password|secret|token|api[_-]?key|authorization|bearer)')
         THEN 'high'
    WHEN REGEXP_CONTAINS(COALESCE(message, '') || COALESCE(json_payload, ''),
         r'(?i)(email|phone|address|\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b)')
         THEN 'moderate'
    WHEN REGEXP_CONTAINS(COALESCE(message, '') || COALESCE(json_payload, ''),
         r'(?i)(user[_-]?id|account[_-]?id)')
         THEN 'low'
    ELSE 'none'
  END
);
```

**Validation:**
```sql
-- Test UDFs
SELECT
  `diatonic-ai-gcp.org_logs_norm.fn_labels_to_array`('{"foo":"bar","baz":"qux"}') AS parsed_labels,
  `diatonic-ai-gcp.org_logs_norm.fn_extract_tenant_id`('{"tenant_id":"acme"}') AS tenant_id,
  `diatonic-ai-gcp.org_logs_norm.fn_derive_environment`('proj', '{}', 'glass-pane-dev') AS env,
  `diatonic-ai-gcp.org_logs_norm.fn_classify_pii_risk`('user password: abc', NULL) AS pii_risk;
```

**Rollback:**
```sql
DROP FUNCTION IF EXISTS `diatonic-ai-gcp.org_logs_norm.fn_labels_to_array`;
DROP FUNCTION IF EXISTS `diatonic-ai-gcp.org_logs_norm.fn_extract_tenant_id`;
DROP FUNCTION IF EXISTS `diatonic-ai-gcp.org_logs_norm.fn_derive_environment`;
DROP FUNCTION IF EXISTS `diatonic-ai-gcp.org_logs_norm.fn_classify_pii_risk`;
```

---

### Phase 3: Create Canonical Views (Reversible)

**Duration:** ~5 minutes
**Risk:** Low (views don't affect underlying data)
**Rollback:** DROP VIEW

#### Step 3.1: Create Primary Canonical View

Run the full `CREATE OR REPLACE VIEW v_logs_all_entry_canon` from `BIGQUERY_DDL.sql`.

**Validation:**
```sql
-- Check view exists and returns data
SELECT COUNT(*) AS total_rows
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date = CURRENT_DATE();

-- Check Universal Envelope structure
SELECT
  log_id,
  universal_envelope.event_id,
  universal_envelope.service.name,
  universal_envelope.trace.trace_id,
  universal_envelope.actor.user_id,
  universal_envelope.privacy.pii_risk
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date = CURRENT_DATE()
LIMIT 5;
```

**Rollback:**
```sql
DROP VIEW IF EXISTS `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`;
```

#### Step 3.2: Create Error View

```sql
CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_logs_norm.v_logs_errors_canon` AS
SELECT *
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE severity_level >= 500;
```

**Validation:**
```sql
SELECT COUNT(*) AS error_count
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_errors_canon`
WHERE log_date = CURRENT_DATE();
```

#### Step 3.3: Create Service Aggregates View

Run `CREATE OR REPLACE VIEW v_logs_service_canon` from `BIGQUERY_DDL.sql`.

**Validation:**
```sql
SELECT * FROM `diatonic-ai-gcp.org_logs_norm.v_logs_service_canon`
WHERE log_date = CURRENT_DATE()
LIMIT 10;
```

---

### Phase 4: Create Validation Views (Reversible)

**Duration:** ~2 minutes
**Risk:** Low

Run the validation view creation statements from `BIGQUERY_DDL.sql`:
- `v_validation_schema_coverage`
- `v_validation_null_rates`
- `v_validation_ingest_latency`

**Validation:**
```sql
-- Check schema coverage
SELECT * FROM `diatonic-ai-gcp.org_logs_norm.v_validation_schema_coverage`;

-- Check null rates
SELECT * FROM `diatonic-ai-gcp.org_logs_norm.v_validation_null_rates`;
```

---

### Phase 5: Create Agent Events Table (Reversible)

**Duration:** ~2 minutes
**Risk:** Low (new table, no existing data affected)

Run the `CREATE TABLE org_agent.tool_invocations` from `BIGQUERY_DDL.sql`.

**Validation:**
```sql
SELECT table_name, creation_time
FROM `diatonic-ai-gcp.org_agent.INFORMATION_SCHEMA.TABLES`
WHERE table_name = 'tool_invocations';
```

**Rollback:**
```sql
DROP TABLE IF EXISTS `diatonic-ai-gcp.org_agent.tool_invocations`;
```

---

### Phase 6: Update ETL Pipeline (Code Change)

**Duration:** ~30 minutes (including testing)
**Risk:** Medium (code change)
**Rollback:** Git revert

#### Step 6.1: Update Normalizer

Edit `src/etl/normalizer.py` to populate new columns:

```python
# Add to NormalizedLog dataclass:
schema_version: str = "1.0.0"
environment: Optional[str] = None
correlation_request_id: Optional[str] = None
correlation_session_id: Optional[str] = None
correlation_conversation_id: Optional[str] = None
privacy_pii_risk: Optional[str] = None
privacy_redaction_state: Optional[str] = None
privacy_retention_class: Optional[str] = None

# Add to normalize() method:
normalized.schema_version = "1.0.0"
normalized.environment = self._derive_environment(raw, normalized)
normalized.privacy_pii_risk = self._classify_pii_risk(normalized)
normalized.privacy_retention_class = "audit" if normalized.is_audit else "standard"
```

#### Step 6.2: Update Loader

Edit `src/etl/loader.py` to include new columns in `_to_bq_row()`.

#### Step 6.3: Test Locally

```bash
# Run ETL with test data
python -m src.etl.pipeline --dry-run --limit 100

# Verify new columns populated
bq query --use_legacy_sql=false \
  "SELECT schema_version, environment, privacy_pii_risk
   FROM \`diatonic-ai-gcp.central_logging_v1.master_logs\`
   WHERE log_date = CURRENT_DATE() AND schema_version IS NOT NULL
   LIMIT 10"
```

**Rollback:**
```bash
git revert HEAD
```

---

### Phase 7: Update Application (Code Change)

**Duration:** ~1 hour (including testing)
**Risk:** Medium

See `APP_WIRING_NOTES.md` for detailed changes required in:
- `src/glass_pane/query_builder.py`
- `src/api/main.py`
- Frontend queries (if any direct BQ access)

---

## Post-Migration Validation

### 7.1 Data Integrity Checks

```sql
-- Check row counts match
SELECT
  (SELECT COUNT(*) FROM `diatonic-ai-gcp.central_logging_v1.master_logs` WHERE log_date = CURRENT_DATE()) AS master_logs_count,
  (SELECT COUNT(*) FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon` WHERE log_date = CURRENT_DATE()) AS canonical_view_count;

-- Should return identical counts
```

### 7.2 Performance Checks

```sql
-- Run sample query and check execution time
SELECT
  universal_envelope.service.name,
  COUNT(*) AS cnt
FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
WHERE log_date = CURRENT_DATE()
  AND severity IN ('ERROR', 'CRITICAL')
GROUP BY 1
ORDER BY 2 DESC;

-- Target: < 5 seconds for 1 day of data
```

### 7.3 Application Health Checks

```bash
# Health endpoint
curl https://glass-pane-845772051724.us-central1.run.app/health

# Test logs endpoint
curl "https://glass-pane-845772051724.us-central1.run.app/api/logs?limit=10&hours=1"
```

---

## Rollback Plan

### Full Rollback Sequence

If critical issues are found, execute in reverse order:

1. **Revert application code** (git revert)
2. **Drop canonical views:**
   ```sql
   DROP VIEW IF EXISTS `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`;
   DROP VIEW IF EXISTS `diatonic-ai-gcp.org_logs_norm.v_logs_errors_canon`;
   DROP VIEW IF EXISTS `diatonic-ai-gcp.org_logs_norm.v_logs_service_canon`;
   DROP VIEW IF EXISTS `diatonic-ai-gcp.org_logs_norm.v_validation_schema_coverage`;
   DROP VIEW IF EXISTS `diatonic-ai-gcp.org_logs_norm.v_validation_null_rates`;
   DROP VIEW IF EXISTS `diatonic-ai-gcp.org_logs_norm.v_validation_ingest_latency`;
   DROP VIEW IF EXISTS `diatonic-ai-gcp.org_logs_norm.v_agent_tool_event_canon`;
   ```
3. **Drop UDFs:**
   ```sql
   DROP FUNCTION IF EXISTS `diatonic-ai-gcp.org_logs_norm.fn_labels_to_array`;
   DROP FUNCTION IF EXISTS `diatonic-ai-gcp.org_logs_norm.fn_extract_tenant_id`;
   DROP FUNCTION IF EXISTS `diatonic-ai-gcp.org_logs_norm.fn_derive_environment`;
   DROP FUNCTION IF EXISTS `diatonic-ai-gcp.org_logs_norm.fn_classify_pii_risk`;
   ```
4. **Drop agent table (if no data):**
   ```sql
   DROP TABLE IF EXISTS `diatonic-ai-gcp.org_agent.tool_invocations`;
   ```
5. **Drop dataset (if empty):**
   ```sql
   DROP SCHEMA IF EXISTS `diatonic-ai-gcp.org_logs_norm`;
   ```

**Note:** New columns on `master_logs` cannot be easily dropped but are harmless (nullable, no data).

---

## Timeline Summary

| Phase | Duration | Risk | Reversible |
|-------|----------|------|------------|
| 1. Schema Preparation | 5 min | Low | Yes |
| 2. Helper Functions | 2 min | Low | Yes |
| 3. Canonical Views | 5 min | Low | Yes |
| 4. Validation Views | 2 min | Low | Yes |
| 5. Agent Table | 2 min | Low | Yes |
| 6. ETL Updates | 30 min | Medium | Yes (git) |
| 7. App Updates | 1 hour | Medium | Yes (git) |
| **Total** | **~2 hours** | | |

---

## Success Criteria

- [ ] `v_logs_all_entry_canon` returns data with Universal Envelope
- [ ] `v_logs_errors_canon` filters correctly (severity >= ERROR)
- [ ] ETL populates new columns (`schema_version`, `environment`, `privacy_*`)
- [ ] Application health checks pass
- [ ] Query performance within targets (< 5s for day queries)
- [ ] No errors in Cloud Logging for app or ETL
