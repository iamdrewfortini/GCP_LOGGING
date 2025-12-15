# AI Stack Research - Glass Pane Intelligence Enhancement

**Date:** 2025-12-15  
**Status:** Research Complete - Ready for Implementation  
**Version:** 1.0

---

## Overview

This research package defines a comprehensive AI intelligence stack for Glass Pane, enabling:
- **Realtime chat** with token budgeting and streaming
- **Dual-write storage** (Firebase hot + BigQuery cold)
- **Vector search** with semantic log retrieval
- **Queue-based workers** for heavy operations
- **Artifact system** for traces and reports
- **MCP tool generator** for safe, auditable tool creation

---

## Document Index

### 1. [00_repo_findings.md](./00_repo_findings.md)
**Current State Analysis**
- Technology stack inventory
- Request lifecycle mapping
- LangGraph agent architecture
- Storage schemas (Firestore + BigQuery)
- Frontend implementation
- Gaps identified

**Key Findings:**
- ✅ Solid foundation: FastAPI + LangGraph + SSE streaming
- ✅ Firebase integration working
- ❌ No tokenization or context budgeting
- ❌ No vector search or embeddings
- ❌ No queue system for async operations

---

### 2. [01_reference_architecture.md](./01_reference_architecture.md)
**Target Architecture**
- Component diagram with data flows
- Realtime chat protocol (SSE with extended events)
- Dual-write storage strategy
- Tokenization & context budgeting
- Vector search architecture (Vertex AI)
- Cost controls & guardrails

**Key Decisions:**
- SSE over WebSocket (simpler, Cloud Run compatible)
- Vertex AI Vector Search (managed, scalable)
- Pub/Sub for async operations (decoupled, reliable)
- tiktoken for token counting (accurate, fast)

---

### 3. [02_langgraph_design.md](./02_langgraph_design.md)
**Enhanced Agent Architecture**
- Extended graph structure with new nodes
- Structured outputs (Pydantic models)
- Checkpointing for long conversations
- Token budget integration
- Streaming event mapping
- Memory strategies (short-term + long-term)

**New Nodes:**
- `ingress_validation` - Classify intent, estimate complexity
- `retrieval` - Hybrid search (semantic + keyword)
- `planner` - Create execution plan with token estimates
- `tool_router` - Decide tool execution vs synthesis
- `synthesize` - Generate structured response with citations
- `checkpoint` - Save state for resumption

---

### 4. [03_data_model_firebase.md](./03_data_model_firebase.md)
**Firestore Schema (Hot Path)**
- Extended `sessions/` collection with token tracking
- Enhanced `messages/` with metadata
- New `checkpoints/` for LangGraph state
- New `embeddings/` for vector metadata
- New `artifacts/` for generated outputs
- New `insights/` for AI-generated insights
- New `costAnalytics/` for dashboard
- Security rules and indexes

**Retention:** 30 days active → 90 days archived → delete/export

---

### 5. [04_data_model_bigquery.md](./04_data_model_bigquery.md)
**BigQuery Schema (Cold Path)**
- `chat_events` - Append-only event log (7 year retention)
- `tool_invocations` - Tool execution metrics
- `artifacts` - Generated output metadata
- `repo_snapshots` - Code index metadata
- `embeddings_metadata` - Embedding generation logs
- Materialized views for analytics
- Partitioning/clustering strategies
- Cost controls

**Key Features:**
- Partition by date, cluster by high-cardinality fields
- Require partition filters
- Maximum bytes billed enforcement
- Query cache enabled

---

### 6. [05_vector_and_queue_plan.md](./05_vector_and_queue_plan.md)
**Vector Search & Queue Architecture**
- Vertex AI Vector Search setup
- Embedding pipeline (Pub/Sub → Cloud Function)
- VectorService implementation
- Semantic search tools
- Realtime vectorization flow
- Cost optimization (deduplication, batching, caching)

**Pub/Sub Topics:**
- `chat-events` - All chat events → BigQuery
- `embedding-jobs` - Async embedding generation
- `index-jobs` - Repo snapshot indexing
- `analytics-jobs` - Aggregation and insights

---

### 7. [06_frontend_hooks_and_components.md](./06_frontend_hooks_and_components.md)
**Frontend Implementation**
- Enhanced `useChatStream` hook with token tracking
- `useArtifacts` hook for artifact management
- `TokenBudgetIndicator` component
- `ToolCallTimeline` component
- `CitationsPanel` component
- `ArtifactList` component
- Testing strategy (unit + E2E)

**Key Features:**
- Realtime token budget display
- Tool execution timeline with collapsible details
- Citation sources with relevance scores
- Artifact download and management

---

### 8. [07_mcp_tool_generator_template.md](./07_mcp_tool_generator_template.md)
**MCP Tool Generator Framework**
- Tool spec schema (YAML)
- Spec validator (Pydantic)
- Code generator (Jinja2 templates)
- ToolRuntime with safety checks
- ToolRegistry for management
- Example tool specs
- CLI for tool management

**Safety Features:**
- Keyword deny/allow lists
- Dataset restrictions
- Row limits
- Timeout enforcement
- Audit logging
- Redaction

---

### 9. [08_implementation_tasks.toon.json](./08_implementation_tasks.toon.json)
**Phased Implementation Plan**
- **Phase 1:** Foundation (7 days) - Tokenization + Dual-Write
- **Phase 2:** Vector Search (10 days) - Embeddings + Semantic Search
- **Phase 3:** Enhanced LangGraph (7 days) - Structured Outputs + Frontend
- **Phase 4:** MCP Tool Generator (10 days) - Tool Generation Framework

**Total Duration:** 34 days (~7 weeks)

**Each Task Includes:**
- Description and dependencies
- Acceptance criteria
- Verification command
- Estimated hours

---

### 10. [09_risks_and_mitigations.md](./09_risks_and_mitigations.md)
**Risk Management**
- Cost overrun (BigQuery/Vertex AI) - **CRITICAL**
- Token budget overflow - **HIGH**
- Vector search latency - **MEDIUM**
- Pub/Sub message loss - **MEDIUM**
- Generated tool security breach - **HIGH**
- Firestore quota exhaustion - **MEDIUM**
- Data privacy violation - **CRITICAL**
- Performance degradation - **MEDIUM**

**Each Risk Includes:**
- Likelihood and impact assessment
- Prevention strategies
- Detection mechanisms
- Response procedures

---

## Quick Start

### 1. Review Research
```bash
# Read documents in order
cat docs/research/ai-stack/00_repo_findings.md
cat docs/research/ai-stack/01_reference_architecture.md
# ... etc
```

### 2. Validate Current State
```bash
# Run existing tests
pytest tests/unit/ -v
cd frontend && npm test

# Check current architecture
python -c "from src.agent.graph import graph; print(graph.get_graph().draw_mermaid())"
```

### 3. Start Implementation
```bash
# Phase 1, Task 1: Add tokenization
pip install tiktoken
mkdir -p src/agent/tokenization
touch src/agent/tokenization.py

# Follow tasks in 08_implementation_tasks.toon.json
```

---

## Key Metrics

### Success Criteria
- **Phase 1:** Token tracking visible in UI, events in BigQuery
- **Phase 2:** Semantic search < 200ms p95, embeddings < 500ms p95
- **Phase 3:** Tool metrics in BigQuery, no performance degradation
- **Phase 4:** Tool generation < 5s, safety checks pass

### Cost Targets
- **BigQuery:** < $50/month (with 50GB query limit)
- **Vertex AI Embeddings:** < $30/month (1000 embeddings/day)
- **Vertex AI Vector Search:** < $50/month (small index)
- **Firestore:** < $20/month (with caching)
- **Pub/Sub:** < $10/month
- **Total:** < $160/month

---

## References

### External Documentation
- [LangGraph Docs](https://langchain-ai.github.io/langgraph/)
- [Vertex AI Vector Search](https://cloud.google.com/vertex-ai/docs/vector-search/overview)
- [Vertex AI Embeddings](https://cloud.google.com/vertex-ai/docs/generative-ai/embeddings/get-text-embeddings)
- [BigQuery Best Practices](https://cloud.google.com/bigquery/docs/best-practices)
- [Firestore Data Model](https://firebase.google.com/docs/firestore/data-model)
- [tiktoken](https://github.com/openai/tiktoken)

### Internal Documentation
- [ARCHITECTURE.md](../../ARCHITECTURE.md) - Current system architecture
- [FRONTEND_ARCHITECTURE.md](../../FRONTEND_ARCHITECTURE.md) - Frontend details
- [IMPLEMENTATION_GUIDE.md](../../IMPLEMENTATION_GUIDE.md) - Firebase setup

---

## Next Steps

1. **Review & Approve** - Stakeholder review of research
2. **Prioritize** - Confirm phase order and timeline
3. **Resource Allocation** - Assign engineers to phases
4. **Kickoff Phase 1** - Start with tokenization + dual-write
5. **Weekly Check-ins** - Track progress against tasks
6. **Iterate** - Adjust based on learnings

---

## Questions & Feedback

For questions or feedback on this research:
1. Review the specific document for details
2. Check risks and mitigations for concerns
3. Consult implementation tasks for timeline
4. Reach out to the AI platform team

---

**Research Complete - Ready for Implementation** ✅

**Total Pages:** 10 documents  
**Total Tasks:** 32 tasks across 4 phases  
**Estimated Duration:** 34 days  
**Risk Level:** Medium (with mitigations in place)
