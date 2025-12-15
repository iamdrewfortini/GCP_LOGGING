# Development Task Specification

## Organization Observability Schema Unification

**Version:** 1.0.0
**Date:** 2025-12-14
**Author:** Claude (Staff Observability Engineer + BigQuery Data Modeling Engineer)

---

## Executive Summary

This specification addresses the schema incompatibility issues preventing the Glass Pane Cloud Run service from querying logs across multiple BigQuery datasets. The solution introduces a canonical schema contract layer that unifies heterogeneous log table schemas into a single queryable view.

### Current State
- Glass Pane service attempts dynamic schema discovery on every request
- Queries fail due to column name mismatches (jsonPayload, protoPayload, etc.)
- An existing canonical view (`view_canonical_logs`) exists but is NOT used by the service
- Log Analytics linked datasets contain query cache tables, not raw logs

### Target State
- Service queries ONLY the canonical view
- All 11 source tables mapped to unified schema
- Parameterized queries with proper error handling
- Comprehensive test coverage

---

## Epic 1: Schema Inventory & Diff Automation

**Objective:** Establish authoritative schema tracking for all logging tables

### Story 1.1: Create Meta Tables
**Scope:** Create BigQuery tables to track schema inventory

**Implementation Steps:**
1. Create `org_observability` dataset if not exists
2. Create `meta_schema_inventory_v1` table
3. Create `meta_source_catalog_v1` table
4. Populate with discovered schema data

**Artifacts:**
- `infra/bigquery/01_meta_schema_inventory.sql`

**Acceptance Criteria:**
- [ ] org_observability dataset exists
- [ ] meta_schema_inventory_v1 table created
- [ ] meta_source_catalog_v1 populated with 12 source tables
- [ ] All tables have canonical_mapped status

**Rollback Plan:** Drop tables; no service dependency yet

---

### Story 1.2: Schema Discovery Automation
**Scope:** Script to refresh schema inventory

**Implementation Steps:**
1. Create shell script to query INFORMATION_SCHEMA
2. Insert results into meta_schema_inventory_v1
3. Generate diff report from previous run
4. Add to CI pipeline (optional)

**Artifacts:**
- `scripts/refresh_schema_inventory.sh`
- `infra/bigquery/queries/schema_diff.sql`

**Acceptance Criteria:**
- [ ] Script runs without errors
- [ ] Schema inventory updated with timestamp
- [ ] Diff report generated showing changes

**Rollback Plan:** Manual schema checks continue

---

## Epic 2: Canonical Contract + Mapping Views

**Objective:** Create unified schema layer for all log sources

### Story 2.1: Update Canonical View v2
**Scope:** Extend existing view to cover all tables

**Implementation Steps:**
1. Review existing `view_canonical_logs` definition
2. Add mapping for `clouderrorreporting_googleapis_com_insights`
3. Add mapping for `cloudscheduler_googleapis_com_executions`
4. Create v2 view in org_observability dataset
5. Validate with test queries

**Artifacts:**
- `infra/bigquery/02_canonical_contract.sql`
- `infra/bigquery/mapping_views/map_clouderrorreporting_to_canonical.sql`
- `infra/bigquery/mapping_views/map_cloudscheduler_to_canonical.sql`

**Acceptance Criteria:**
- [ ] View `org_observability.logs_canonical_v2` created
- [ ] Query returns data from all 11 source tables
- [ ] No schema errors on SELECT *
- [ ] source_table field correctly identifies origin

**Rollback Plan:** Keep v1 view; update service to use v1 if v2 fails

---

### Story 2.2: Document Canonical Contract
**Scope:** Create comprehensive schema documentation

**Implementation Steps:**
1. Document all fields with types and descriptions
2. Document severity values
3. Document payload normalization rules
4. Create query examples

**Artifacts:**
- `docs/specs/CANONICAL_CONTRACT.md`
- `docs/specs/LIST_OF_REQUIRED_FIELDS.md`

**Acceptance Criteria:**
- [ ] All 18 canonical fields documented
- [ ] Severity values enumerated
- [ ] Query examples tested and working

**Rollback Plan:** N/A (documentation only)

---

## Epic 3: Service Query Refactor

**Objective:** Refactor Glass Pane to use canonical view exclusively

### Story 3.1: Create Configuration Module
**Scope:** Centralize configuration with validation

**Implementation Steps:**
1. Create `config.py` with dataclass
2. Add environment variable parsing
3. Add validation method
4. Add startup validation

**Files to Create:**
- `app/glass-pane/config.py`

**Acceptance Criteria:**
- [ ] All config loaded from environment
- [ ] Validation errors logged at startup
- [ ] Default values appropriate for production

**Rollback Plan:** Revert to inline config; low risk

---

### Story 3.2: Create Query Builder Module
**Scope:** Type-safe parameterized query construction

**Implementation Steps:**
1. Create `query_builder.py`
2. Implement `LogQueryParams` dataclass
3. Implement `CanonicalQueryBuilder` class
4. Add methods for list, aggregate, trace lookup

**Files to Create:**
- `app/glass-pane/query_builder.py`

**Acceptance Criteria:**
- [ ] Queries parameterized (no string interpolation of user input)
- [ ] Validation on params before query build
- [ ] SQL output matches expected format

**Rollback Plan:** Use existing query construction; higher risk

---

### Story 3.3: Refactor main.py
**Scope:** Replace dynamic discovery with canonical view queries

**Implementation Steps:**
1. Remove `get_all_datasets()` function
2. Remove dynamic INFORMATION_SCHEMA queries
3. Import and use `CanonicalQueryBuilder`
4. Update `/` route to use canonical view
5. Add `/api/logs` REST endpoint
6. Add `/api/logs/aggregate` endpoint
7. Add structured error responses

**Files to Modify:**
- `app/glass-pane/main.py`

**Acceptance Criteria:**
- [ ] No INFORMATION_SCHEMA queries in main.py
- [ ] All queries use parameterization
- [ ] Error responses include correlation ID
- [ ] Health endpoint still works
- [ ] Index page displays logs correctly

**Rollback Plan:** Git revert; keep previous version deployable

---

### Story 3.4: Update Frontend Template
**Scope:** Update UI to match canonical schema

**Implementation Steps:**
1. Update column names (event_timestamp, not timestamp)
2. Add severity filter dropdown
3. Add service filter input
4. Add time window selector
5. Improve error display

**Files to Modify:**
- `app/glass-pane/templates/index.html`

**Acceptance Criteria:**
- [ ] All columns display correctly
- [ ] Filters work with API
- [ ] Errors displayed in user-friendly format

**Rollback Plan:** Revert template changes

---

## Epic 4: Testing & CI

**Objective:** Ensure reliability through automated testing

### Story 4.1: Unit Tests for Query Builder
**Scope:** Test query construction logic

**Implementation Steps:**
1. Create `tests/` directory
2. Create `tests/test_query_builder.py`
3. Add tests for parameter validation
4. Add tests for SQL generation
5. Add tests for error cases

**Files to Create:**
- `app/glass-pane/tests/__init__.py`
- `app/glass-pane/tests/test_query_builder.py`
- `app/glass-pane/tests/test_config.py`

**Acceptance Criteria:**
- [ ] 80%+ code coverage on query_builder.py
- [ ] All validation paths tested
- [ ] pytest runs successfully

**Rollback Plan:** N/A (new files only)

---

### Story 4.2: Integration Tests
**Scope:** Test against real BigQuery (dry-run mode)

**Implementation Steps:**
1. Create `tests/test_integration.py`
2. Add dry-run query tests
3. Add schema compatibility tests
4. Configure for CI execution

**Files to Create:**
- `app/glass-pane/tests/test_integration.py`

**Acceptance Criteria:**
- [ ] Dry-run queries validate successfully
- [ ] Tests can run in CI with service account
- [ ] Schema changes detected by tests

**Rollback Plan:** Skip integration tests in CI

---

### Story 4.3: Add pytest to Requirements
**Scope:** Update dependencies

**Implementation Steps:**
1. Add pytest, pytest-cov to requirements.txt
2. Create pytest.ini configuration
3. Update Dockerfile if needed

**Files to Modify:**
- `app/glass-pane/requirements.txt`

**Files to Create:**
- `app/glass-pane/pytest.ini`

**Acceptance Criteria:**
- [ ] `pytest` runs locally
- [ ] Coverage report generated

**Rollback Plan:** Remove test dependencies

---

## Epic 5: Deployment & Validation

**Objective:** Deploy changes safely with validation

### Story 5.1: Deploy BigQuery Views
**Scope:** Create canonical view v2 in production

**Implementation Steps:**
1. Run `01_meta_schema_inventory.sql`
2. Run `02_canonical_contract.sql`
3. Run `03_data_quality_checks.sql`
4. Validate with test queries

**Commands:**
```bash
bq query --use_legacy_sql=false < infra/bigquery/01_meta_schema_inventory.sql
bq query --use_legacy_sql=false < infra/bigquery/02_canonical_contract.sql
bq query --use_legacy_sql=false < infra/bigquery/03_data_quality_checks.sql
```

**Acceptance Criteria:**
- [ ] org_observability.logs_canonical_v2 exists
- [ ] DQ check views exist
- [ ] Query returns recent logs

**Rollback Plan:** Drop v2 view; v1 still available

---

### Story 5.2: Update Service Environment
**Scope:** Configure Cloud Run with new variables

**Implementation Steps:**
1. Set CANONICAL_VIEW=org_observability.logs_canonical_v2
2. Set DEFAULT_LIMIT=100
3. Set MAX_LIMIT=1000
4. Set DEFAULT_TIME_WINDOW_HOURS=24

**Commands:**
```bash
gcloud run services update glass-pane \
  --set-env-vars="CANONICAL_VIEW=org_observability.logs_canonical_v2" \
  --set-env-vars="DEFAULT_LIMIT=100" \
  --set-env-vars="MAX_LIMIT=1000" \
  --set-env-vars="DEFAULT_TIME_WINDOW_HOURS=24" \
  --region=us-central1
```

**Acceptance Criteria:**
- [ ] Environment variables set
- [ ] Service reads new config

**Rollback Plan:** Revert to old env vars

---

### Story 5.3: Deploy Updated Service
**Scope:** Build and deploy refactored service

**Implementation Steps:**
1. Run unit tests locally
2. Build container image
3. Deploy to Cloud Run
4. Verify health endpoint
5. Verify log display

**Commands:**
```bash
cd app/glass-pane
pytest tests/
gcloud builds submit --tag gcr.io/diatonic-ai-gcp/glass-pane:v2.0.0
gcloud run deploy glass-pane \
  --image gcr.io/diatonic-ai-gcp/glass-pane:v2.0.0 \
  --platform managed \
  --region us-central1
```

**Acceptance Criteria:**
- [ ] Health check passes
- [ ] Logs display from all source tables
- [ ] No schema errors in Cloud Run logs
- [ ] Filters work correctly

**Rollback Plan:**
```bash
gcloud run services update-traffic glass-pane \
  --to-revisions=glass-pane-<previous-revision>=100
```

---

### Story 5.4: Smoke Test & Validation
**Scope:** End-to-end validation

**Implementation Steps:**
1. Generate test traffic (scripts/generate_traffic.sh)
2. Wait for BigQuery ingestion (2-5 minutes)
3. Verify logs appear in UI
4. Test severity filter
5. Test service filter
6. Check Cloud Run logs for errors

**Acceptance Criteria:**
- [ ] New logs appear within 5 minutes
- [ ] All severity levels displayed correctly
- [ ] Service filter returns correct results
- [ ] No 500 errors in Cloud Run logs

**Rollback Plan:** Full rollback to previous revision

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Canonical view query timeout | Low | High | Add LIMIT, time filters required |
| Missing table schema change | Medium | Medium | Schema inventory automation |
| Service deployment failure | Low | High | Keep previous revision available |
| Data quality issues | Low | Medium | DQ checks and monitoring |

---

## Timeline Estimate (Not Prescriptive)

| Epic | Stories | Dependencies |
|------|---------|--------------|
| E1: Schema Inventory | 2 | None |
| E2: Canonical Contract | 2 | E1 |
| E3: Service Refactor | 4 | E2 |
| E4: Testing | 3 | E3 |
| E5: Deployment | 4 | E3, E4 |

---

## Appendix: File Inventory

### New Files to Create
```
infra/bigquery/
├── 01_meta_schema_inventory.sql
├── 02_canonical_contract.sql
├── 03_data_quality_checks.sql
└── mapping_views/
    ├── map_clouderrorreporting_to_canonical.sql
    └── map_cloudscheduler_to_canonical.sql

app/glass-pane/
├── config.py
├── query_builder.py
├── pytest.ini
└── tests/
    ├── __init__.py
    ├── test_query_builder.py
    ├── test_config.py
    └── test_integration.py

docs/specs/
├── DEV_TASK_SPEC.md (this file)
├── GAP_REPORT_CODE.md
├── LIST_OF_REQUIRED_FIELDS.md
├── BQ_SCHEMA_DIFF_REPORT.md
├── CANONICAL_CONTRACT.md
├── CODE_TASKS.md
└── PERF_GUIDE.md
```

### Files to Modify
```
app/glass-pane/
├── main.py (major refactor)
├── requirements.txt (add pytest)
└── templates/
    └── index.html (update columns, add filters)
```

---

## Approval Checklist

- [ ] Technical lead review
- [ ] Security review (parameterized queries)
- [ ] Cost estimate for canonical view queries
- [ ] Rollback procedure tested
- [ ] Monitoring alerts configured
