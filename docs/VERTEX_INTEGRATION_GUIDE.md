# Vertex AI Integration Guide

## Architecture
-   **Backend**: Cloud Run (Python/Flask)
-   **AI Provider**: Vertex AI (Gemini 1.5 Pro/Flash)
-   **Auth**: Workload Identity (Service Account)
-   **Client**: `langchain-google-vertexai`

## Prerequisites
1.  **API Enabled**: `aiplatform.googleapis.com`
2.  **Service Account Permissions**: `roles/aiplatform.user`
3.  **Region**: `us-central1` (Standard for Vertex AI)

## Implementation Plan

### 1. Service Account & IAM
The Cloud Run service account `vertex-ai-service@diatonic-ai-gcp.iam.gserviceaccount.com` (or the default compute one) needs:
-   `roles/aiplatform.user`
-   `roles/bigquery.dataViewer` (for log access)
-   `roles/logging.logWriter` (for audit logging)

### 2. Application Code
**Location**: `app/glass-pane/services/agent_service.py`

**Key Components**:
-   **VertexAIWrapper**: Wraps the SDK call with retry logic (exponential backoff).
-   **Redactor**: Regex-based PII scrubber (IPs, Emails, SSNs) before prompt construction.
-   **Token Counter**: Estimates input/output tokens for cost tracking.
-   **Streaming**: Use `stream=True` and yield Server-Sent Events (SSE) to frontend.

### 3. API Design
**POST /api/ai/chat**
-   **Input**: `{ "query": "string", "context": "optional_log_data" }`
-   **Output**: Streaming JSON chunks `{ "chunk": "...", "citations": [...] }`

### 4. Safety & Guardrails
-   **Feature Flag**: `VERTEX_ENABLED` (default: false)
-   **Budgeting**: Hard limit on daily tokens (implemented via Redis or simply Logging metrics alerting).
-   **Context Limit**: Truncate log data to fit model context window (1M tokens for Gemini 1.5, but we should limit to ~30k for latency).

## Verification
1.  **Smoke Test**: `curl -X POST /api/ai/chat -d '{"query": "Hello"}'`
2.  **Load Test**: Ensure 429s are handled gracefully.
