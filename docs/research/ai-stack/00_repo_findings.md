# Repo Findings - Current Architecture Inventory

**Date:** 2025-12-15  
**Project:** GCP Centralized Logging & Visualization (Glass Pane)  
**Purpose:** Document current state before AI stack enhancements

---

## Executive Summary

Glass Pane is a production GCP logging platform with an AI-powered log debugger. The system uses:
- **Backend:** FastAPI (Python 3.12) on Cloud Run
- **Agent:** LangGraph + Gemini 2.5 Flash (Vertex AI)
- **Storage:** BigQuery (logs) + Firestore (sessions)
- **Frontend:** React 19 + Vite + TanStack Router
- **Streaming:** SSE (Server-Sent Events) for chat

**Current Capabilities:**
✅ Organization-wide log aggregation (BigQuery)  
✅ AI chat with streaming responses  
✅ Tool calling (BigQuery queries, trace lookup, service health)  
✅ Session persistence (Firestore)  
✅ Real-time log search and filtering  
✅ Firebase emulator support for local dev

**Gaps Identified:**
❌ No tokenization/context budgeting  
❌ No vector search or embeddings  
❌ No queue system for heavy operations  
❌ No BigQuery event log for chat analytics  
❌ No artifact/snapshot system  
❌ No MCP tool generator framework  
❌ Limited observability of agent behavior  

---

## 1. Technology Stack

### Backend Runtime
- **Language:** Python 3.12
- **Framework:** FastAPI
- **Server:** Uvicorn (ASGI)
- **Deployment:** Cloud Run (us-central1)
- **Service Account:** `agent-sa@diatonic-ai-gcp.iam.gserviceaccount.com`

### Dependencies (requirements.txt)
```
fastapi
uvicorn
jinja2
google-cloud-bigquery
google-cloud-logging
google-cloud-billing
google-cloud-aiplatform
google-cloud-trace
google-cloud-run
firebase-admin>=6.4.0
langchain-core
langchain-google-genai
langgraph
pydantic
pytest
httpx
```

**Notable:** No tiktoken, no vector DB client, no queue library (Celery/RQ/Cloud Tasks SDK)

### Frontend Stack
```json
{
  "react": "^19.2.0",
  "vite": "^7.2.4",
  "@tanstack/react-query": "5.90.12",
  "@tanstack/react-router": "1.141.2",
  "firebase": "12.6.0",
  "recharts": "2.15.4",
  "zod": "4.2.0"
}
```

### Infrastructure
- **BigQuery Dataset:** `central_logging_v1` (org-wide logs)
- **Firestore:** Native mode, us-central1
- **Pub/Sub Topic:** `logging-critical-alerts` (ERROR+ logs)
- **GCS Bucket:** `dacvisuals-central-logs-archive-v1` (cold storage)
- **Cloud Function:** `log-processor` (alert handler)

---

## 2. Request Lifecycle - Chat Flow

### Current Flow (SSE Streaming)

```
User → Frontend (React)
  ↓ POST /api/chat
Backend (FastAPI)
  ↓ Create/verify session (Firestore)
  ↓ Persist user message (Firestore)
  ↓ Build LangGraph inputs
LangGraph Agent
  ↓ diagnose_node → tools_condition
  ↓ tool_node (execute tools)
  ↓ verify_node → optimize_node
  ↓ persist_node (BigQuery agent_runs)
  ↓ Stream events via astream_events(v2)
Backend
  ↓ Parse events → SSE format
  ↓ Redact sensitive data
  ↓ Persist assistant message (Firestore)
Frontend
  ↓ EventSource parser
  ↓ Update UI incrementally
```

### Event Types (SSE)
```typescript
type ChatStreamEvent = 
  | { type: "session", data: { session_id: string } }
  | { type: "on_chat_model_stream", data: { content: string } }
  | { type: "on_tool_start", data: { tool: string, input: any } }
  | { type: "on_tool_end", data: { output: any } }
  | { type: "error", data: { message: string, reference_id: string } }
```

**Observations:**
- ✅ Clean SSE implementation with proper error handling
- ✅ Redaction layer (`src/security/redaction.py`)
- ❌ No token counting or budget enforcement
- ❌ No structured event schema validation
- ❌ No event persistence to BigQuery for analytics

---

## 3. LangGraph Agent Architecture

### Graph Structure (`src/agent/graph.py`)

```python
workflow = StateGraph(AgentState)

# Nodes
workflow.add_node("diagnose", diagnose_node)
workflow.add_node("verify", verify_node)
workflow.add_node("optimize", optimize_node)
workflow.add_node("tools", tool_node)
workflow.add_node("persist", persist_node)

# Flow
diagnose → tools_condition → [tools | verify]
verify → tools_condition → [tools | optimize]
optimize → tools_condition → [tools | persist]
persist → END
tools → dispatcher → [diagnose | verify | optimize]
```

### State Schema (`src/agent/state.py`)
```python
class AgentState(TypedDict):
    run_id: str
    user_query: str
    messages: Annotated[List[BaseMessage], operator.add]
    scope: Dict[str, Any]
    hypotheses: List[str]
    evidence: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    cost_summary: Dict[str, Any]
    runbook_ids: List[str]
    phase: str  # diagnose | verify | optimize
    mode: str
    status: str
    error: Optional[str]
```

**Observations:**
- ✅ Well-structured 3-phase diagnostic flow
- ✅ Tool routing via `tools_condition`
- ❌ No checkpointing/memory persistence
- ❌ No token budget tracking in state
- ❌ No structured output validation (Pydantic models)

### Tools Available (`src/agent/tools/definitions.py`)

**Smart Tools (Enhanced):**
- `analyze_logs(intent, timeframe, severity_filter, service_filter)` - Comprehensive analysis
- `get_log_summary(hours)` - Quick health check
- `find_related_logs(error_message, time_window_minutes)` - Context search
- `suggest_queries(context)` - Query recommendations

**Standard Tools:**
- `search_logs_tool(query, severity, service, hours, limit)` - Basic search
- `bq_query_tool(sql, params)` - Raw BigQuery execution
- `trace_lookup_tool(trace, project)` - Trace API integration
- `service_health_tool(service, region)` - Cloud Run service inspection
- `runbook_search_tool(query)` - Placeholder
- `repo_search_tool(pattern, paths)` - Placeholder
- `create_view_tool(dataset, view_name, sql)` - View materialization
- `dashboard_spec_tool(title, panels, filters, alerts)` - Dashboard generation

**Tool Safety (`src/agent/tools/bq.py`):**
```python
def run_bq_query(inp: BQQueryInput) -> BQQueryOutput:
    # 1. Dry run first
    dry_run_out = run_bq_dry_run(...)
    
    # 2. Enforce byte limit
    if dry_run_out.bytes_estimate > config.MAX_BQ_BYTES_ESTIMATE:
        raise ValueError(f"Query exceeds byte limit: {dry_run_out.bytes_estimate}")
    
    # 3. Execute with max_rows limit
    rows = query_job.result(max_results=inp.max_rows)
```

**Observations:**
- ✅ Dry-run safety gate for BigQuery
- ✅ Smart tools with intent-based routing
- ❌ No tool output caching
- ❌ No tool execution metrics (latency, cost)
- ❌ No tool registry or dynamic loading

---

## 4. Storage Architecture

### Firestore Collections

**sessions/**
```typescript
{
  userId: string
  title: string
  status: "active" | "archived" | "deleted"
  createdAt: Timestamp
  updatedAt: Timestamp
  metadata: {
    totalMessages: number
    totalCost: number
    tags: string[]
  }
}
```

**sessions/{sessionId}/messages/**
```typescript
{
  role: "user" | "assistant" | "system" | "tool"
  content: string
  timestamp: Timestamp
  metadata: {
    tools_used?: string[]
    word_count?: number
  }
}
```

**sessions/{sessionId}/graphStates/** (unused currently)
```typescript
{
  state: object
  checkpointId?: string
  createdAt: Timestamp
}
```

**savedQueries/**
```typescript
{
  userId: string
  name: string
  queryParams: object
  createdAt: Timestamp
  lastRunAt: Timestamp
  runCount: number
}
```

**Security Rules:** User-scoped access, immutable messages, admin-only collections

**Observations:**
- ✅ Clean schema with proper indexing
- ✅ Security rules enforce ownership
- ❌ No embeddings collection (defined in rules but unused)
- ❌ No insights collection (defined in rules but unused)
- ❌ No cost analytics collection (defined in rules but unused)

### BigQuery Schema

**central_logging_v1.view_canonical_logs** (View)
```sql
SELECT 
    event_ts,
    receive_ts,
    source_table,  -- run_stdout, run_stderr, cloudaudit_activity, syslog
    resource_type,
    project_id,
    service,
    severity,
    trace,
    spanId,
    operation,
    display_message,
    json_payload_str,
    labels_json
FROM (
    SELECT ... FROM cloudaudit_googleapis_com_activity
    UNION ALL
    SELECT ... FROM run_googleapis_com_stdout
    UNION ALL
    SELECT ... FROM run_googleapis_com_stderr
    UNION ALL
    SELECT ... FROM syslog
)
```

**org_agent.agent_runs** (Table - used by persist_node)
```python
{
    "run_id": str,
    "ts": timestamp,
    "user_query": str,
    "scope": json,
    "graph_state": json,
    "tool_calls": json,
    "evidence": json[],
    "cost_summary": json,
    "runbook_ids": str[],
    "confidence": float,
    "status": str,
    "error": str
}
```

**Observations:**
- ✅ Canonical view simplifies multi-table queries
- ✅ Partitioned tables for performance
- ❌ No chat_events table for streaming analytics
- ❌ No tool_invocations table for tool metrics
- ❌ No artifacts table for generated outputs
- ❌ No repo_snapshots table for index metadata

---

## 5. Frontend Architecture

### Streaming Implementation (`frontend/src/lib/api.ts`)

```typescript
export async function* streamChat(request: ChatRequest): AsyncGenerator<ChatStreamEvent> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  })

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() || ""

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6).trim()
        if (data === "[DONE]") return
        try {
          yield JSON.parse(data) as ChatStreamEvent
        } catch {
          // Skip invalid JSON
        }
      }
    }
  }
}
```

### Chat Hook (`frontend/src/hooks/use-chat.ts`)

```typescript
export function useChat(userId = "anonymous") {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  
  const sendMessage = async (content: string, context = {}) => {
    // Add user message optimistically
    setMessages(prev => [...prev, userMessage])
    
    // Create placeholder for assistant
    setMessages(prev => [...prev, assistantMessage])
    
    // Stream response
    for await (const event of streamChat(request)) {
      handleStreamEvent(event, assistantMessage.id)
    }
  }
  
  const handleStreamEvent = (event, messageId) => {
    switch (event.type) {
      case "on_chat_model_stream":
        // Append content incrementally
        setMessages(prev => prev.map(m => 
          m.id === messageId ? { ...m, content: m.content + event.data.content } : m
        ))
        break
      case "on_tool_start":
        // Add tool call to message
        break
      case "on_tool_end":
        // Update tool call status
        break
    }
  }
}
```

**Observations:**
- ✅ Clean SSE parser with buffering
- ✅ Optimistic UI updates
- ✅ Tool call tracking
- ❌ No reconnection logic
- ❌ No abort controller for cancellation
- ❌ No token counting display
- ❌ No artifact viewer component

---

## 6. Deployment & Configuration

### Cloud Build Pipeline (`cloudbuild.yaml`)

```yaml
steps:
  - id: test
    name: python:3.12-slim
    entrypoint: bash
    args: ["-c", "pip install -r requirements.txt && pytest -q"]
  
  - id: build
    name: gcr.io/cloud-builders/docker
    args: ["build", "-t", "gcr.io/$PROJECT_ID/glass-pane:$COMMIT_SHA", "."]
  
  - id: deploy
    name: gcr.io/google.com/cloudsdktool/cloud-sdk
    args: [
      "run", "deploy", "glass-pane",
      "--image", "gcr.io/$PROJECT_ID/glass-pane:$COMMIT_SHA",
      "--set-env-vars", "PROJECT_ID=$PROJECT_ID,FIREBASE_ENABLED=true,..."
    ]
```

### Environment Variables (Cloud Run)
```bash
PROJECT_ID=diatonic-ai-gcp
PROJECT_ID_LOGS=diatonic-ai-gcp
PROJECT_ID_AGENT=diatonic-ai-gcp
PROJECT_ID_FINOPS=diatonic-ai-gcp
CANONICAL_VIEW=org_observability.logs_canonical_v2
BQ_LOCATION=US
VERTEX_ENABLED=true
VERTEX_REGION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true
FIREBASE_ENABLED=true
MAX_BQ_BYTES_ESTIMATE=50000000000  # 50GB
MAX_ROWS_RETURNED=1000
```

### Firebase Hosting (`firebase.json`)
```json
{
  "hosting": {
    "public": "frontend/dist",
    "rewrites": [
      { "source": "/api/**", "run": { "serviceId": "glass-pane" } },
      { "source": "**", "destination": "/index.html" }
    ]
  },
  "emulators": {
    "firestore": { "port": 8181 },
    "auth": { "port": 9099 },
    "pubsub": { "port": 8085 }
  }
}
```

---

## 7. Gaps & Missing Components

### Tokenization & Context Management
- ❌ No tiktoken or token counting
- ❌ No context window budgeting (Gemini 2.5 Flash = 1M tokens)
- ❌ No chunking strategy for large logs
- ❌ No summarization checkpoints

### Vector Search & Embeddings
- ❌ No embedding generation pipeline
- ❌ No vector store (Vertex AI Vector Search, pgvector, Qdrant)
- ❌ No semantic search over logs
- ❌ No repo indexing with embeddings

### Queue & Background Jobs
- ❌ No Cloud Tasks or Pub/Sub worker pattern
- ❌ No Celery/RQ for async jobs
- ❌ Heavy operations (embeddings, backfills) block request thread

### BigQuery Analytics
- ❌ No chat_events table for streaming analytics
- ❌ No tool_invocations table for tool metrics
- ❌ No artifacts table for generated outputs
- ❌ No partitioning/clustering strategy for chat data

### Artifact System
- ❌ No artifact creation pipeline
- ❌ No repo snapshot indexing
- ❌ No trace viewer or debug replay

### MCP Tool Generator
- ❌ No tool spec schema
- ❌ No code generation framework
- ❌ No policy/guardrail system
- ❌ No audit logging for tool execution

### Observability
- ❌ No structured logging for agent decisions
- ❌ No cost tracking per conversation
- ❌ No latency metrics for tool calls
- ❌ No error rate monitoring

---

## 8. Strengths to Preserve

### What's Working Well
1. **Clean SSE streaming** - Reliable, low-latency, works with Cloud Run
2. **LangGraph structure** - 3-phase diagnostic flow is intuitive
3. **Tool safety** - Dry-run gate prevents expensive queries
4. **Firebase integration** - Session persistence works smoothly
5. **Frontend architecture** - Modern React stack with good DX
6. **Emulator support** - Local dev workflow is solid
7. **Security** - Redaction layer, Firestore rules, IAM scoping

### Patterns to Extend
- SSE event schema → Add more event types (token_count, artifact_created, checkpoint_saved)
- Tool pattern → Extend to MCP-compatible tool registry
- Firestore collections → Add embeddings, insights, cost_analytics
- BigQuery views → Add chat analytics views
- Frontend hooks → Add useArtifacts, useRepoSnapshots, useTokenBudget

---

## 9. Integration Points for New Features

### Where to Add Tokenization
- **Backend:** `src/agent/tokenization.py` (new module)
- **State:** Add `token_budget`, `tokens_used` to `AgentState`
- **Streaming:** Emit `token_count` events in SSE
- **Frontend:** Display token usage in chat UI

### Where to Add Vector Search
- **Backend:** `src/services/vector_service.py` (new module)
- **Tools:** `semantic_search_tool`, `find_similar_errors_tool`
- **Queue:** Pub/Sub → Cloud Function → embed → upsert
- **Firestore:** `embeddings/` collection for metadata

### Where to Add Queues
- **Backend:** `src/workers/` (new directory)
- **Pub/Sub Topics:** `chat-events`, `embedding-jobs`, `index-jobs`
- **Cloud Functions:** `functions/workers/` (new directory)

### Where to Add BigQuery Analytics
- **Schema:** `infra/bigquery/chat_analytics/` (new directory)
- **Tables:** `chat_events`, `tool_invocations`, `artifacts`, `repo_snapshots`
- **Views:** `chat_sessions_summary`, `tool_usage_stats`

### Where to Add MCP Tools
- **Backend:** `src/mcp/` (new directory)
- **Generator:** `src/mcp/generator.py`
- **Registry:** `src/mcp/registry.py`
- **Specs:** `src/mcp/specs/` (YAML/JSON tool definitions)

---

## 10. Recommended Next Steps

### Phase 1: Foundation (Week 1)
1. Add tokenization module (tiktoken)
2. Create BigQuery chat_events table
3. Implement dual-write (Firestore + BigQuery)
4. Add structured event schema validation

### Phase 2: Vector Search (Week 2)
5. Set up Vertex AI Vector Search index
6. Create embedding generation pipeline (Pub/Sub + Cloud Function)
7. Add semantic search tools
8. Implement repo snapshot indexing

### Phase 3: Queues & Workers (Week 3)
9. Set up Cloud Tasks for heavy operations
10. Create worker functions for embeddings, backfills
11. Add job status tracking in Firestore

### Phase 4: MCP Tool Generator (Week 4)
12. Design tool spec schema
13. Implement code generator
14. Add policy/guardrail framework
15. Create audit logging system

---

## Appendix: File Inventory

### Backend Core
- `src/api/main.py` - FastAPI app, SSE streaming endpoint
- `src/agent/graph.py` - LangGraph workflow definition
- `src/agent/nodes.py` - Node implementations (diagnose, verify, optimize)
- `src/agent/state.py` - AgentState TypedDict
- `src/agent/llm.py` - Gemini 2.5 Flash initialization
- `src/agent/tools/definitions.py` - Tool implementations
- `src/agent/tools/bq.py` - BigQuery execution with safety
- `src/agent/persistence.py` - BigQuery agent_runs writer
- `src/services/firebase_service.py` - Firestore client wrapper
- `src/security/redaction.py` - PII redaction
- `src/config.py` - Environment configuration

### Frontend Core
- `frontend/src/lib/api.ts` - API client with SSE streaming
- `frontend/src/hooks/use-chat.ts` - Chat state management
- `frontend/src/hooks/use-logs.ts` - Log fetching
- `frontend/src/lib/firebase.ts` - Firebase SDK initialization
- `frontend/src/routes/chat.tsx` - Chat UI page

### Infrastructure
- `cloudbuild.yaml` - CI/CD pipeline
- `Dockerfile` - Cloud Run container
- `firebase.json` - Firebase Hosting + Emulators
- `firestore.rules` - Security rules
- `firestore.indexes.json` - Composite indexes
- `schemas/canonical_view.sql` - Log view definition
- `infra/bigquery/` - Schema definitions

### Documentation
- `docs/ARCHITECTURE.md` - System overview
- `docs/FRONTEND_ARCHITECTURE.md` - Frontend details
- `docs/IMPLEMENTATION_GUIDE.md` - Firebase setup guide

---

**End of Repo Findings**
