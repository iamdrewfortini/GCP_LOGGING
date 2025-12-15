# Phase 3 Quick Reference Card

## 🚀 Quick Start

### Backend: Add Structured Outputs
```python
from src.agent.schemas import Response, Plan

# In your node
llm_with_structure = llm.with_structured_output(Response)
response = llm_with_structure.invoke(messages)

# Access structured data
for finding in response.findings:
    print(f"{finding.severity}: {finding.title}")
```

### Backend: Save Checkpoint
```python
from src.agent.checkpoint import save_checkpoint

# In your node
metadata = save_checkpoint(state)
print(f"Checkpoint saved: {metadata.checkpoint_id}")
```

### Backend: Track Tool Metrics
```python
from src.agent.metered_tool_node import create_metered_tool_node

# Replace ToolNode
tool_node = create_metered_tool_node(tools, publish_metrics=True)
```

### Frontend: Use Enhanced Hook
```typescript
import { useChatStream } from "@/hooks/use-chat-stream"

const { messages, tokenBudget, sendMessage } = useChatStream()
```

### Frontend: Add Components
```typescript
import { TokenBudgetIndicator } from "@/components/chat/TokenBudgetIndicator"
import { ToolCallTimeline } from "@/components/chat/ToolCallTimeline"
import { CitationsPanel } from "@/components/chat/CitationsPanel"

<TokenBudgetIndicator tokenBudget={tokenBudget} />
<ToolCallTimeline toolCalls={message.toolCalls} />
<CitationsPanel citations={message.citations} />
```

## 📊 Schemas Reference

### IngressValidation
```python
validation = IngressValidation(
    is_valid=True,
    intent="debug",
    entities={"services": ["api-gateway"]},
    timeframe="24h",
    suggested_tools=["analyze_logs"]
)
```

### Plan
```python
plan = Plan(
    phase="diagnose",
    hypotheses=[
        Hypothesis(
            id="hyp-1",
            description="Database timeout",
            confidence=0.8
        )
    ],
    tool_invocations=[
        ToolInvocation(
            tool_name="search_logs_tool",
            parameters={"query": "timeout"},
            rationale="Find timeout errors"
        )
    ],
    reasoning="Investigating database issues"
)
```

### Response
```python
response = Response(
    summary="Found database connection issues",
    findings=[
        Finding(
            title="Connection Pool Exhausted",
            severity="critical",
            recommendation="Increase pool size"
        )
    ],
    recommendations=[
        Recommendation(
            title="Scale Database",
            priority="immediate",
            effort="low",
            impact="high"
        )
    ],
    citations=[
        Citation(
            source="log-123",
            content="ERROR: timeout",
            relevance_score=0.95
        )
    ],
    confidence=0.9
)
```

## 🔧 Common Tasks

### Load a Checkpoint
```python
from src.agent.checkpoint import load_checkpoint, restore_state_from_checkpoint

checkpoint_data = load_checkpoint("ckpt-123")
state = restore_state_from_checkpoint(checkpoint_data)
```

### List Checkpoints for Run
```python
from src.agent.checkpoint import list_checkpoints_for_run

checkpoints = list_checkpoints_for_run("run-456", limit=10)
for cp in checkpoints:
    print(f"{cp['phase']}: {cp['checkpoint_id']}")
```

### Query Tool Metrics
```sql
SELECT 
  tool_name,
  AVG(duration_ms) as avg_duration,
  SUM(cost_usd) as total_cost
FROM `diatonic-ai-gcp.chat_analytics.tool_invocations`
WHERE DATE(started_at) = CURRENT_DATE()
GROUP BY tool_name
```

### Emit SSE Events
```python
# Token count event
yield {
    "type": "token_count",
    "data": {
        "total_tokens": 1500,
        "budget_remaining": 8500,
        "should_summarize": False
    }
}

# Checkpoint event
yield {
    "type": "checkpoint",
    "data": {
        "checkpoint_id": "ckpt-123",
        "phase": "diagnose",
        "timestamp": datetime.now().isoformat()
    }
}

# Citation event
yield {
    "type": "citation",
    "data": {
        "source": "log-123",
        "content": "ERROR: timeout",
        "relevance_score": 0.95
    }
}
```

## 🎨 Component Props

### TokenBudgetIndicator
```typescript
interface TokenBudgetIndicatorProps {
  tokenBudget: TokenBudget | null
  className?: string
}

interface TokenBudget {
  promptTokens: number
  completionTokens: number
  totalTokens: number
  budgetMax: number
  budgetRemaining: number
  model: string
  shouldSummarize: boolean
}
```

### ToolCallTimeline
```typescript
interface ToolCallTimelineProps {
  toolCalls: ToolCall[]
  className?: string
}

interface ToolCall {
  id: string
  tool: string
  input?: Record<string, unknown>
  output?: unknown
  status: "running" | "completed" | "error"
  durationMs?: number
  tokenCount?: number
  costUsd?: number
}
```

### CitationsPanel
```typescript
interface CitationsPanelProps {
  citations: Citation[]
  className?: string
}

interface Citation {
  source: string
  content: string
  relevanceScore: number
  metadata?: Record<string, unknown>
}
```

## 🧪 Testing

### Run Backend Tests
```bash
# All Phase 3 tests
.venv/bin/python -m pytest tests/unit/test_structured_outputs.py -v
.venv/bin/python -m pytest tests/unit/test_checkpoint_node.py -v
.venv/bin/python -m pytest tests/unit/test_metered_tool_node.py -v

# Specific test
.venv/bin/python -m pytest tests/unit/test_structured_outputs.py::TestResponse -v
```

### Run Frontend Tests
```bash
cd frontend

# All Phase 3 tests
npm test -- TokenBudgetIndicator.test.tsx
npm test -- ToolCallTimeline.test.tsx
npm test -- CitationsPanel.test.tsx

# Watch mode
npm test -- --watch
```

## 📦 Deployment

### Deploy BigQuery Table
```bash
export PROJECT_ID=diatonic-ai-gcp
./scripts/create_tool_invocations_table.sh
```

### Create Pub/Sub Topic
```bash
gcloud pubsub topics create tool-invocation-metrics
gcloud pubsub subscriptions create tool-metrics-to-bq \
  --topic=tool-invocation-metrics
```

### Deploy Firestore Rules
```bash
firebase deploy --only firestore:rules
firebase deploy --only firestore:indexes
```

## 🐛 Debugging

### Check Token Tracking
```python
from src.agent.tokenization import TokenBudgetManager

manager = TokenBudgetManager(model="gpt-4", max_tokens=100000)
count = manager.count_text("Hello world")
print(f"Tokens: {count}")
print(f"Status: {manager.get_budget_status()}")
```

### Verify Checkpoint Saved
```python
from firebase_admin import firestore

db = firestore.client()
doc = db.collection("checkpoints").document("ckpt-123").get()
if doc.exists:
    print(f"Checkpoint found: {doc.to_dict()}")
```

### Check Tool Metrics
```bash
# Query BigQuery
bq query --use_legacy_sql=false '
SELECT * FROM `diatonic-ai-gcp.chat_analytics.tool_invocations`
ORDER BY started_at DESC
LIMIT 10
'
```

### Debug Frontend Events
```typescript
// In use-chat-stream.ts
console.log("Event received:", event.type, event.data)
```

## 📚 File Locations

### Backend
- Schemas: `src/agent/schemas.py`
- Checkpoint: `src/agent/checkpoint.py`
- Tool Metrics: `src/agent/metered_tool_node.py`
- Tests: `tests/unit/test_*.py`

### Frontend
- Hook: `frontend/src/hooks/use-chat-stream.ts`
- Components: `frontend/src/components/chat/`
- Tests: `frontend/src/components/chat/__tests__/`

### Config
- BigQuery Schema: `schemas/bigquery/tool_invocations.json`
- Deployment: `scripts/create_tool_invocations_table.sh`

## 🔗 Related Docs

- [Phase 3 Progress](./PHASE3_PROGRESS.md)
- [Integration Guide](./PHASE3_INTEGRATION_GUIDE.md)
- [Complete Summary](./PHASE3_COMPLETE.md)
- [Implementation Plan](./08_implementation_tasks.toon.json)

## 💡 Tips

1. **Use structured outputs** for type safety and validation
2. **Checkpoint frequently** during long-running operations
3. **Monitor tool metrics** to optimize performance
4. **Test token limits** with realistic data
5. **Handle errors gracefully** in all components

## ⚠️ Common Pitfalls

1. **Don't forget** to emit SSE events from backend
2. **Remember** to handle null tokenBudget in frontend
3. **Always** validate structured outputs
4. **Check** Firestore permissions for checkpoints
5. **Monitor** BigQuery costs for tool metrics

---

**Quick Reference Version**: 1.0.0  
**Last Updated**: December 15, 2024
