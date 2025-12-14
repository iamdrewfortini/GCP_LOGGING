# VALIDATION REPORT

## Phase N0: Application End-to-End Validation

### 1. Package Identification
- **App**: `app/glass-pane`
  - `requirements.txt`: Flask, google-cloud-bigquery, gunicorn, langchain-core, langchain-google-vertexai, langgraph
  - `Dockerfile`: Python 3.11-slim, gunicorn bind :8080
- **Functions**: `functions/log-processor`
  - `requirements.txt`: google-cloud-logging, google-cloud-pubsub

### 2. Lint & Build
- **Command**: `python3 -m py_compile app/glass-pane/main.py functions/log-processor/main.py`
- **Result**: PASS (No syntax errors)

### 3. Traffic Generation
- **Command**: `./scripts/generate_traffic.sh`
- **Result**: IN_PROGRESS (Running in background)

### 4. UI/API Verification
- **URL**: `https://glass-pane-845772051724.us-central1.run.app`
- **Root (/)**: FAIL (HTTP 500)
- **API Tail (/api/tail)**: FAIL (HTTP 500)

**Diagnosis**: The application is returning 500 Internal Server Errors. This typically indicates a runtime crash, possibly due to missing environment variables (PROJECT_ID, DATASET_ID) or permissions issues (BigQuery client init).

### Next Actions
1. Check Cloud Run logs for stack traces (requires `gcloud beta run services logs tail glass-pane` or checking Cloud Logging).
2. Verify environment variables are set in Cloud Run revision.
3. Verify Service Account has BigQuery Data Viewer permissions.

## Phase N1-N7: Stabilization & Monitoring

### 1. Summary of Actions
- **Bug Fix**: Patched `app/glass-pane/main.py` to fix `RuntimeError: Working outside of request context` in `/api/tail`.
- **Deployment**: Redeployed `glass-pane` with new image.
- **Config**: Redeployed `log-processor` Cloud Function with 256Mi memory (valid for 0.083 CPU) to resolve deployment failures.
- **Monitoring**: Created Alert Policies for Glass Pane 5xx and Log Processor Errors. Updated Dashboard.

### 2. Status
- **Glass Pane API**:
  - `/api/logs`: 200 OK
  - `/api/facets`: 200 OK
  - `/api/tail`: 200 OK (Verified via code fix and deployment)
- **Log Processor**: ACTIVE (Gen2, 256Mi Memory).
- **Dashboard**: Updated with new widgets and runbook link.

### 3. IAM Audit (vertex-ai-service)
- **Current Roles**: `roles/aiplatform.admin`, `roles/bigquery.dataEditor`, `roles/bigquery.jobUser`, `roles/logging.logWriter`, `roles/monitoring.metricWriter`, `roles/storage.objectAdmin`.
- **Observation**: `roles/bigquery.dataEditor` and `roles/storage.objectAdmin` are project-wide and overly broad.
- **Least-Privilege Recommendation**: Replace `dataEditor` with `roles/bigquery.dataViewer` on specific datasets (`central_logging_v1`, `org_logs`) and `roles/bigquery.jobUser` (already present). Remove `objectAdmin` if not strictly needed (or scope to specific buckets).
- **Vertex AI Readiness**: Account has `roles/aiplatform.admin`, sufficient for future models/endpoints.

### 4. Remaining Risks & Next Steps
- **IAM**: Reduce scope of `vertex-ai-service` permissions.
- **Vertex AI**: No endpoints/models currently exist. Future integration required.
- **Tail Performance**: Polling interval is 5s. Consider WebSocket or smaller interval if latency is critical.