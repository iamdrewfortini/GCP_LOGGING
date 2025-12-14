# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a centralized logging and visualization platform for Google Cloud Platform. It uses a Hub-and-Spoke architecture to aggregate logs from all projects in a GCP Organization into a central BigQuery dataset, with a Flask web UI ("Glass Pane") for visualization and an AI-powered log analysis agent.

## Core Architecture

### Data Flow
1. **Ingestion**: Organization-level logging sinks intercept all logs from all projects
2. **Storage Destinations**:
   - `org-central-sink-bq` → BigQuery Dataset `central_logging_v1` (hot storage for analytics)
   - `org-central-sink-gcs` → GCS Bucket `dacvisuals-central-logs-archive-v1` (cold storage, 1-year retention)
   - `org-central-sink-alerts` → Pub/Sub Topic `logging-critical-alerts` (triggers Cloud Function for ERROR/CRITICAL logs)

### Key Components
- **Glass Pane** (`app/glass-pane/`): Flask Cloud Run app that queries BigQuery and serves the visualization UI
- **Log Processor** (`functions/log-processor/`): Cloud Function triggered by Pub/Sub for real-time alert processing
- **Query Builder** (`app/glass-pane/services/query_builder.py`): Constructs SQL queries over the canonical log view
- **Agent Service** (`app/glass-pane/services/agent_service.py`): LangGraph-based Gemini agent for AI-assisted log analysis

### BigQuery Schema Strategy
Logs are stored in multiple tables by resource type (e.g., `cloudaudit_googleapis_com_activity`, `run_googleapis_com_stdout`, `syslog`). The `QueryBuilder` unions these tables with a canonical schema:
- `event_ts`: Timestamp
- `severity`: Log severity level
- `source_table`: Which sink table the log came from
- `service`: Service name extracted from resource labels
- `trace`, `spanId`: Distributed tracing identifiers
- `json_payload_str`: Serialized JSON payload
- `display_message`: Human-readable message text

**Important**: The system was designed to use a BigQuery VIEW called `view_canonical_logs` to unify tables (see ADR_0001_LOG_STORAGE.md), but the current implementation uses inline CTEs in `QueryBuilder.get_canonical_sql()` to avoid DDL requirements.

## Development Commands

### Local Development
```bash
# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Glass Pane dependencies
pip install -r app/glass-pane/requirements.txt

# Run Glass Pane locally (requires GCP credentials)
cd app/glass-pane
export PROJECT_ID=diatonic-ai-gcp
export DATASET_ID=central_logging_v1
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
python main.py
# Access at http://localhost:8080
```

### Deployment
```bash
# Deploy entire infrastructure (GCS, BigQuery, Pub/Sub, Cloud Run, Cloud Function)
cd scripts
./deploy_scaffold.sh

# Deploy only Glass Pane app
cd app/glass-pane
gcloud builds submit --tag gcr.io/diatonic-ai-gcp/glass-pane
gcloud run deploy glass-pane \
  --image gcr.io/diatonic-ai-gcp/glass-pane \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars PROJECT_ID=diatonic-ai-gcp,DATASET_ID=central_logging_v1

# Deploy only Log Processor function
gcloud functions deploy log-processor \
  --trigger-topic=logging-critical-alerts \
  --runtime=python312 \
  --entry-point=process_log_entry \
  --source=functions/log-processor \
  --region=us-central1
```

### Testing
```bash
# Generate sample traffic to populate BigQuery
./scripts/generate_traffic.sh

# Test Glass Pane API endpoints
curl "http://localhost:8080/api/logs?severity=ERROR&limit=10"
curl "http://localhost:8080/api/facets"
curl "http://localhost:8080/health"
```

## Configuration

### Environment Variables
- `PROJECT_ID`: GCP project ID (default: `diatonic-ai-gcp`)
- `DATASET_ID`: BigQuery dataset name (default: `central_logging_v1`)
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account key (for local dev)
- `PORT`: Flask server port (default: `8080`)

### Key Configuration Files
- `config/gcs_lifecycle.json`: GCS bucket lifecycle policy (30d Standard → 90d Coldline → 365d Archive)
- `dashboards/glass_pane.json`: Cloud Monitoring dashboard definition
- `scripts/deploy_scaffold.sh`: Master deployment script with all resource names and IAM bindings

## Development Patterns

### Adding Support for a New Log Table
When a new log table appears in the BigQuery dataset, update `QueryBuilder.get_canonical_sql()` to add a `UNION ALL` clause that maps the table's fields to the canonical schema. Ensure you extract:
1. `timestamp` → `event_ts`
2. `severity`
3. A descriptive `source_table` name
4. `service` (from `resource.labels.service_name` or similar)
5. `trace`, `spanId` (if available)
6. `json_payload_str` (serialized JSON)
7. `display_message` (textPayload or relevant message field)

### Flask API Endpoints
All endpoints are defined in `app/glass-pane/main.py`:
- `GET /api/logs`: Paginated, filterable log retrieval (query params: `from`, `to`, `severity`, `service`, `limit`, `cursor`)
- `GET /api/logs/:trace_id/:span_id`: Single log retrieval by trace and span
- `GET /api/facets`: Aggregated facet data (severities, services, source_tables)
- `GET /api/tail`: Server-Sent Events (SSE) for real-time log tailing
- `POST /api/chat`: Gemini agent interaction for log analysis
- `GET /health`: Health check endpoint

### Agent Tool Development
The Gemini agent uses LangGraph with custom tools defined in `app/glass-pane/services/agent_service.py`. To add a new tool:
1. Define a function decorated with `@tool`
2. Add it to `LogDebuggerAgent.tools` list
3. Update `decide_what_to_do()` router logic if the tool requires specific routing

**Security Note**: The agent redacts sensitive information (API keys, tokens, passwords) before sending log context to the LLM. Update `_redact_sensitive_info()` regex patterns as needed.

## IAM and Permissions

### Required Roles
- **Log Sink Writer Identities**: Automatically created by `gcloud logging sinks create`
  - GCS Sink: `roles/storage.objectCreator` on archive bucket
  - BigQuery Sink: `roles/bigquery.dataEditor` on dataset
  - Pub/Sub Sink: `roles/pubsub.publisher` on topic
- **Glass Pane Service Account**: `roles/bigquery.dataViewer` or `jobUser` + `dataViewer` on the central dataset
- **Agent Service**: `roles/aiplatform.user` for Vertex AI (Gemini) access

### Security Considerations
- The Cloud Run service is currently `--allow-unauthenticated` for demo purposes. In production, protect with Identity-Aware Proxy (IAP).
- Content Security Policy (CSP) headers are enforced via `@app.after_request` in `main.py`.
- Sensitive data is redacted before LLM processing, but audit the redaction patterns regularly.

## Troubleshooting

### "BigQuery client not initialized"
- Ensure `GOOGLE_APPLICATION_CREDENTIALS` is set or the Cloud Run service account has BigQuery permissions
- Verify `PROJECT_ID` and `DATASET_ID` environment variables are correct

### "Agent failed: 500 Internal Server Error"
- Check Cloud Logging for backend tracebacks
- Verify the service account has `roles/aiplatform.user` for Vertex AI
- Confirm Vertex AI API is enabled in the project

### Logs not appearing in real-time tail
- BigQuery streaming ingestion has latency (typically seconds to minutes)
- Check the `from` timestamp parameter in `/api/tail` requests

### Organization Sink Permissions Issues
- Run `scripts/deploy_scaffold.sh` which handles IAM binding creation for sink writer identities
- Verify you are authenticated as an Org Admin: `gcloud auth login`
- Check sink configurations: `gcloud logging sinks describe <sink-name> --organization=<org-id>`

## Reference Documentation

- Architecture overview: `docs/ARCHITECTURE.md`
- Operational runbook: `docs/RUNBOOK.md`
- Log storage ADR: `docs/ADR_0001_LOG_STORAGE.md`
- GCP Organization ID: `93534264368`
- Project ID: `diatonic-ai-gcp`
- Region: `us-central1`
