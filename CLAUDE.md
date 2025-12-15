# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a centralized logging and visualization platform for Google Cloud Platform. It uses a Hub-and-Spoke architecture to aggregate logs from all projects in a GCP Organization into a central BigQuery dataset, with a React frontend ("Glass Pane") for visualization and an AI-powered log analysis agent.

## Core Architecture

### Data Flow
1. **Ingestion**: Organization-level logging sinks intercept all logs from all projects
2. **Storage Destinations**:
   - `org-central-sink-bq` → BigQuery Dataset `central_logging_v1` (hot storage for analytics)
   - `org-central-sink-gcs` → GCS Bucket `dacvisuals-central-logs-archive-v1` (cold storage, 1-year retention)
   - `org-central-sink-alerts` → Pub/Sub Topic `logging-critical-alerts` (triggers Cloud Function for ERROR/CRITICAL logs)

### Key Components
- **React Frontend** (`frontend/`): Vite + React + TypeScript application with TanStack Router/Query
- **FastAPI Backend** (`src/api/main.py`): REST API for logs, sessions, chat, and saved queries
- **Query Builder** (`src/glass_pane/`): Canonical BigQuery query builder for log retrieval
- **Log Processor** (`functions/log-processor/`): Cloud Function triggered by Pub/Sub for real-time alert processing
- **Agent** (`src/agent/`): LangGraph-based Gemini 2.5 Flash agent for AI-assisted log analysis
- **Firebase Service** (`src/services/firebase_service.py`): Firestore-based session and query persistence

### BigQuery Schema Strategy
Logs are centralized in a unified `master_logs` table (`central_logging_v1.master_logs`) via an ETL pipeline. This table contains all logs from all GCP services in a normalized schema:

**Key columns:**
- `log_id`: Unique identifier (UUID)
- `event_timestamp`: When the event occurred
- `severity`: Log severity level (DEFAULT, DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL, ALERT, EMERGENCY)
- `service_name`: Extracted service name
- `source_table`: Original sink table name
- `stream_id`: Stream identifier (dataset.table format)
- `message`: Normalized message content
- `trace_id`, `span_id`: Distributed tracing identifiers
- `http_*`: HTTP request context (method, url, status, latency_ms)
- `json_payload`, `proto_payload`: Original payloads as JSON

**Partition & Clustering:**
- Partitioned by `log_date` (DATE)
- Clustered by `severity`, `service_name`, `resource_type`

**ETL Pipeline (`src/etl/`):**
- Extracts logs from individual sink tables
- Normalizes to unified schema
- Loads into `master_logs` with deduplication
- Tracks sync state per stream
- Supports incremental and full ETL runs

## Development Commands

### Local Development (Full Stack)

```bash
# 1. Start Firebase Emulators (in terminal 1)
firebase emulators:start

# 2. Start Backend with Emulator connection (in terminal 2)
source .venv/bin/activate
export FIRESTORE_EMULATOR_HOST="127.0.0.1:8181"
export PROJECT_ID="diatonic-ai-gcp"
uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload

# 3. Start Frontend (in terminal 3)
cd frontend
npm run dev

# Access:
# - Frontend: http://localhost:5173
# - Backend API: http://localhost:8080/api
# - Firebase Emulator UI: http://localhost:4000
```

### Using the Dev Script

```bash
# Start everything (emulators + backend)
./scripts/dev_local.sh

# Start only emulators
./scripts/dev_local.sh --emulators-only

# Start only backend (assumes emulators running)
./scripts/dev_local.sh --app-only
```

### Backend Only (No Firebase)

```bash
source .venv/bin/activate
export FIREBASE_ENABLED=false
uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload
```

### Deployment

**Automated Deployment (Recommended)**:
The repository uses GitHub Actions for continuous deployment. Simply push to the `main` branch:
```bash
git push origin main
```

This triggers the workflow defined in `.github/workflows/deploy.yml` which:
1. Runs tests and linting
2. Builds the Docker image and pushes to GCR
3. Deploys to Cloud Run with proper environment variables
4. Updates traffic to the new revision

**Manual Deployment**:
```bash
# Deploy entire infrastructure (GCS, BigQuery, Pub/Sub, Cloud Run, Cloud Function)
cd scripts
./deploy_scaffold.sh

# Deploy unified Cloud Run service manually
gcloud builds submit --tag gcr.io/diatonic-ai-gcp/glass-pane

gcloud run deploy glass-pane \
  --image gcr.io/diatonic-ai-gcp/glass-pane \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars PROJECT_ID_LOGS=diatonic-ai-gcp,PROJECT_ID_AGENT=diatonic-ai-gcp,PROJECT_ID_FINOPS=diatonic-ai-gcp,CANONICAL_VIEW=org_observability.logs_canonical_v2

# Deploy only Log Processor function
gcloud functions deploy log-processor \
  --trigger-topic=logging-critical-alerts \
  --runtime=python312 \
  --entry-point=process_log_entry \
  --source=functions/log-processor \
  --region=us-central1
```

**Important**: When making code changes, always push to `main` to trigger auto-deployment. The GitHub Actions workflow ensures consistent deployments with proper testing.

### Testing
```bash
# Generate sample traffic to populate BigQuery
./scripts/generate_traffic.sh

# Test API endpoints
curl "http://localhost:8080/api/logs?severity=ERROR&limit=10"
curl "http://localhost:8080/api/stats/severity"
curl "http://localhost:8080/api/stats/services"
curl "http://localhost:8080/health"
```

## Configuration

### Backend Environment Variables
- `PROJECT_ID`: GCP project ID (default: `diatonic-ai-gcp`)
- `DATASET_ID`: BigQuery dataset name (default: `central_logging_v1`)
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account key (for local dev)
- `FIRESTORE_EMULATOR_HOST`: Firestore emulator connection (e.g., `127.0.0.1:8181`)
- `FIREBASE_ENABLED`: Set to `false` to disable Firebase (default: `true`)
- `PORT`: Server port (default: `8080`)

### Frontend Environment Variables (in `frontend/.env.local`)
- `VITE_API_URL`: Backend API URL (default: Cloud Run URL)
- `VITE_USE_FIREBASE_EMULATORS`: Set to `true` for local emulators
- `VITE_FIREBASE_PROJECT_ID`: Firebase project ID
- See `frontend/.env.example` for full list

### Key Configuration Files
- `firebase.json`: Firebase emulator configuration (ports: Auth 9099, Firestore 8181, Storage 9199, etc.)
- `config/gcs_lifecycle.json`: GCS bucket lifecycle policy (30d Standard → 90d Coldline → 365d Archive)
- `dashboards/glass_pane.json`: Cloud Monitoring dashboard definition
- `scripts/deploy_scaffold.sh`: Master deployment script with all resource names and IAM bindings
- `scripts/dev_local.sh`: Local development script with emulator setup

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

### API Endpoints
All endpoints are defined in `src/api/main.py`:
- `GET /`: API info and available endpoints
- `GET /health`: Health check endpoint
- `GET /api/logs`: Paginated, filterable log retrieval (query params: `hours`, `severity`, `service`, `search`, `limit`)
- `GET /api/stats/severity`: Log counts by severity level
- `GET /api/stats/services`: Log counts by service
- `POST /api/sessions`: Create a new chat session
- `GET /api/sessions`: List user's sessions
- `GET /api/sessions/{id}`: Get session with messages
- `POST /api/sessions/{id}/archive`: Archive a session
- `POST /api/saved-queries`: Save a reusable log query
- `GET /api/saved-queries`: List user's saved queries
- `POST /api/chat`: Gemini agent SSE streaming for log analysis

### Agent Tool Development
The Gemini agent uses LangGraph with custom tools defined in `src/agent/tools.py`. To add a new tool:
1. Define a function decorated with `@tool`
2. Add it to the agent's tools list in `src/agent/graph.py`
3. The agent workflow handles routing automatically (diagnose → verify → optimize → persist)

**Security Note**: The agent redacts sensitive information (API keys, tokens, passwords) before sending log context to the LLM.

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
- CORS is configured to allow specific frontend origins only.
- Firestore security rules restrict access by user ID.
- Sensitive data is redacted before LLM processing.

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
- Frontend architecture: `docs/FRONTEND_ARCHITECTURE.md`
- Operational runbook: `docs/RUNBOOK.md`
- Log storage ADR: `docs/ADR_0001_LOG_STORAGE.md`
- GCP Organization ID: `93534264368`
- Project ID: `diatonic-ai-gcp`
- Region: `us-central1`
