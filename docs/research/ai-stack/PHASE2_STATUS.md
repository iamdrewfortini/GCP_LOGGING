# Phase 2 Status Report: Vector Search & Embeddings

**Date:** 2025-12-15
**Status:** COMPLETED

## Summary

Phase 2 implementation (Tasks 2.1-2.8) has been successfully completed. The AI Stack now includes:

- VectorService for unified embedding and search operations
- Semantic search tools for natural language log queries
- Embedding worker Cloud Function for async processing
- Retrieval node in LangGraph for context-aware analysis
- BigQuery embeddings_metadata table for analytics

## Completed Tasks

### Task 2.1: Create Vector Search Infrastructure

**Approach:** Using existing Qdrant service instead of Vertex AI Vector Search for cost efficiency and faster iteration.

**Components:**
- `src/services/qdrant_service.py` - Existing Qdrant client
- `src/services/embedding_service.py` - Existing Vertex AI embeddings
- Collection: `log_embeddings` with 768-dim vectors

**Indexes Created:**
- `project_id` (KEYWORD) - Tenant isolation
- `severity` (KEYWORD) - Log filtering
- `service` (KEYWORD) - Service filtering
- `timestamp.year/month/day` (INTEGER) - Time filtering

### Task 2.2: Create VectorService Module

**Files Created:**
- `src/services/vector_service.py` - Unified vector operations service

**Key Features:**
```python
class VectorService:
    def embed_and_store(text, project_id, source_type, metadata, deduplicate)
    def semantic_search(query, project_id, top_k, filters, score_threshold)
    def semantic_search_logs(query, project_id, severity, service, hours)
    def get_similar_logs(log_text, project_id, top_k, exclude_self)
    def delete_by_project(project_id, collection)
```

**Dataclasses:**
- `EmbeddingResult` - Result of embedding operation
- `SearchResult` - Result of semantic search

**Feature Flags:**
```bash
ENABLE_VECTOR_SEARCH=true|false
ENABLE_LOG_EMBEDDINGS=true|false
```

### Task 2.3: Create embedding-jobs Pub/Sub Topic

**Infrastructure (manual deployment required):**
```bash
# Create topic
gcloud pubsub topics create embedding-jobs

# Create subscription
gcloud pubsub subscriptions create embedding-jobs-to-worker \
    --topic=embedding-jobs \
    --ack-deadline=120
```

### Task 2.4: Deploy Embedding Worker Cloud Function

**Files Created:**
- `functions/embedding-worker/main.py` - Cloud Function entry point
- `functions/embedding-worker/requirements.txt` - Dependencies

**Message Format:**
```json
{
    "action": "embed_log" | "embed_batch" | "delete_project",
    "project_id": "diatonic-ai-gcp",
    "text": "Log message to embed",
    "texts": ["msg1", "msg2"],
    "metadata": {
        "severity": "ERROR",
        "service": "my-service"
    }
}
```

**Deployment:**
```bash
gcloud functions deploy embedding-worker \
    --trigger-topic=embedding-jobs \
    --runtime=python312 \
    --entry-point=process_embedding_job \
    --source=functions/embedding-worker \
    --region=us-central1 \
    --set-env-vars=PROJECT_ID=diatonic-ai-gcp,QDRANT_URL=<url>,ENABLE_EMBEDDINGS=true
```

### Task 2.5: Add semantic_search_logs Tool

**Files Modified:**
- `src/agent/tools/definitions.py` - Added semantic search tools
- `src/agent/nodes.py` - Added tools to agent

**New Tools:**
1. `semantic_search_logs(query, top_k, severity, service, score_threshold)` - Natural language search
2. `find_similar_logs(log_text, top_k, exclude_self)` - Find similar log entries

**Usage Examples:**
```python
# Natural language search
semantic_search_logs(query="authentication failures", severity="ERROR")

# Find similar logs
find_similar_logs(log_text="Connection timeout to database", top_k=5)
```

### Task 2.6: Update Analytics Worker to Trigger Embeddings

**Files Modified:**
- `functions/analytics-worker/main.py` - Added embedding trigger
- `functions/analytics-worker/requirements.txt` - Added pubsub dependency

**Changes:**
- Added `trigger_embedding()` function to publish to embedding-jobs topic
- User messages are now embedded for semantic search
- Feature flag: `ENABLE_EMBEDDINGS=true|false`

### Task 2.7: Create embeddings_metadata BigQuery Table

**Files Modified:**
- `src/cli/provision_bq.py` - Added embeddings_metadata schema

**Table Schema:**
```
embeddings_metadata
├── embedding_id (STRING, REQUIRED)
├── created_at (TIMESTAMP, REQUIRED) [partition key]
├── project_id (STRING, REQUIRED)
├── source_type (STRING, REQUIRED)
├── text_hash (STRING, REQUIRED)
├── content_preview (STRING)
├── embedding_model (STRING, REQUIRED)
├── embedding_dim (INT64, REQUIRED)
├── collection_name (STRING, REQUIRED)
├── metadata (JSON)
├── processing_time_ms (INT64)
├── status (STRING, REQUIRED)
└── error_message (STRING)
```

**View Created:**
- `v_embeddings_summary` - Embedding generation analytics

### Task 2.8: Add Retrieval Node to LangGraph

**Files Modified:**
- `src/agent/nodes.py` - Added `retrieval_node()`
- `src/agent/graph.py` - Updated workflow with retrieval

**Workflow:**
```
retrieval → diagnose → verify → optimize → persist
    ↓           ↓         ↓         ↓
  tools ←─────────────────────────────
```

**Feature Flag:**
```bash
ENABLE_RETRIEVAL=true|false  # Default: true
```

**Retrieval Node Behavior:**
1. Performs semantic search using user query
2. Adds top 5 relevant logs as evidence
3. Passes enriched state to diagnose node
4. Non-blocking: errors don't stop the workflow

## Test Coverage

**New Test Files:**
- `tests/unit/test_vector_service.py` - 25 tests for VectorService

**Test Results:**
```
128 passed in 4.77s
```

## Verification Commands

```bash
# Compile check
python3 -m compileall -q src functions

# Run tests
source .venv/bin/activate
pytest tests/unit/test_vector_service.py -v
pytest tests/unit tests/integration -v

# BQ provisioning dry run (includes embeddings_metadata)
python -m src.cli provision-bq --dataset chat_analytics --dry-run
```

## Environment Variables

### Backend Configuration
```bash
# Vector search feature flags
ENABLE_VECTOR_SEARCH=true
ENABLE_LOG_EMBEDDINGS=true
ENABLE_RETRIEVAL=true

# Qdrant configuration
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=<optional>

# Embedding configuration
EMBEDDING_MODEL=text-embedding-004
```

### Analytics Worker
```bash
ENABLE_EMBEDDINGS=true
EMBEDDING_JOBS_TOPIC=embedding-jobs
```

### Embedding Worker
```bash
PROJECT_ID=diatonic-ai-gcp
REGION=us-central1
QDRANT_URL=<url>
QDRANT_API_KEY=<key>
EMBEDDING_MODEL=text-embedding-004
ENABLE_EMBEDDINGS=true
```

## Deployment Notes

### Infrastructure Setup (One-time)
```bash
# 1. Create Pub/Sub topic for embedding jobs
gcloud pubsub topics create embedding-jobs

# 2. Create subscription
gcloud pubsub subscriptions create embedding-jobs-to-worker \
    --topic=embedding-jobs \
    --ack-deadline=120

# 3. Update BigQuery schema
python -m src.cli provision-bq --dataset chat_analytics

# 4. Deploy embedding worker
gcloud functions deploy embedding-worker \
    --trigger-topic=embedding-jobs \
    --runtime=python312 \
    --entry-point=process_embedding_job \
    --source=functions/embedding-worker \
    --region=us-central1

# 5. Update analytics worker with embedding trigger
gcloud functions deploy analytics-worker \
    --trigger-topic=chat-events \
    --runtime=python312 \
    --entry-point=process_chat_event \
    --source=functions/analytics-worker \
    --region=us-central1 \
    --set-env-vars=ENABLE_EMBEDDINGS=true,EMBEDDING_JOBS_TOPIC=embedding-jobs

# 6. Update Cloud Run with new environment variables
gcloud run services update glass-pane \
    --region=us-central1 \
    --set-env-vars=ENABLE_VECTOR_SEARCH=true,ENABLE_RETRIEVAL=true
```

## Files Changed Summary

### Backend
- `src/services/vector_service.py` - NEW: Unified vector operations
- `src/agent/tools/definitions.py` - Added semantic_search_logs, find_similar_logs
- `src/agent/nodes.py` - Added retrieval_node
- `src/agent/graph.py` - Updated workflow with retrieval
- `src/cli/provision_bq.py` - Added embeddings_metadata schema

### Functions
- `functions/embedding-worker/main.py` - NEW: Embedding worker
- `functions/embedding-worker/requirements.txt` - NEW: Dependencies
- `functions/analytics-worker/main.py` - Added embedding trigger
- `functions/analytics-worker/requirements.txt` - Added pubsub

### Tests
- `tests/unit/test_vector_service.py` - NEW: 25 vector service tests

### Documentation
- `docs/research/ai-stack/PHASE2_STATUS.md` - NEW: This file

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Glass Pane Frontend                      │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                           │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ /api/chat    │───▶│  LangGraph   │───▶│ DualWrite    │  │
│  └──────────────┘    │              │    │ Service      │  │
│                      │  retrieval ──┤    └──────┬───────┘  │
│                      │  diagnose    │           │          │
│                      │  verify      │           ▼          │
│                      │  optimize    │    ┌──────────────┐  │
│                      │  persist     │    │  Pub/Sub     │  │
│                      └──────┬───────┘    │ chat-events  │  │
│                             │            └──────┬───────┘  │
│                             │                   │          │
│  ┌──────────────────────────┼───────────────────┤          │
│  │                          │                   │          │
│  ▼                          ▼                   ▼          │
│ ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│ │VectorService │    │  Firestore   │    │ Analytics    │  │
│ │              │    │  (hot path)  │    │ Worker       │  │
│ └──────┬───────┘    └──────────────┘    └──────┬───────┘  │
│        │                                       │          │
└────────┼───────────────────────────────────────┼──────────┘
         │                                       │
         ▼                                       ▼
┌──────────────┐                         ┌──────────────┐
│   Qdrant     │◀────────────────────────│  Pub/Sub     │
│   Vector DB  │                         │ embedding-   │
└──────────────┘                         │ jobs         │
         ▲                               └──────┬───────┘
         │                                      │
         │                                      ▼
┌──────────────┐                         ┌──────────────┐
│  Vertex AI   │◀────────────────────────│  Embedding   │
│  Embeddings  │                         │  Worker      │
└──────────────┘                         └──────────────┘
                                                │
                                                ▼
                                         ┌──────────────┐
                                         │  BigQuery    │
                                         │chat_analytics│
                                         └──────────────┘
```

## Known Gaps / Follow-on Tasks

1. **Qdrant deployment** - Need production Qdrant instance (Cloud/self-hosted)
2. **Embedding batching** - Currently single-threaded, consider async batching
3. **Monitoring** - Add metrics for embedding latency and search performance
4. **Rate limiting** - Embedding API rate limiting not implemented
5. **TTL for embeddings** - Consider expiring old embeddings
6. **Frontend integration** - Semantic search UI components (Phase 3)

## Success Metrics

- [x] VectorService provides unified embedding/search interface
- [x] Semantic search tools available to agent
- [x] Embedding worker processes jobs from Pub/Sub
- [x] Analytics worker triggers embeddings for user messages
- [x] Retrieval node adds context before diagnosis
- [x] All tests pass (128/128)
- [x] BigQuery schema includes embeddings_metadata
