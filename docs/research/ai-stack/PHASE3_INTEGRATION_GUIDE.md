# Phase 3 Integration Guide

## Overview
This guide provides step-by-step instructions for integrating Phase 3 components into the Glass Pane application.

## Backend Integration

### Step 1: Update API to Emit New SSE Events

Update `app/api/chat.py` to emit the new event types:

```python
from src.agent.schemas import Response, Plan, IngressValidation
from src.agent.checkpoint import save_checkpoint

async def stream_chat_response(request: ChatRequest):
    """Stream chat response with enhanced events."""
    
    # ... existing code ...
    
    # Emit token count events
    if state.get("token_budget"):
        token_budget = state["token_budget"]
        yield {
            "type": "token_count",
            "data": {
                "input_tokens": token_budget.get("prompt_tokens", 0),
                "output_tokens": token_budget.get("completion_tokens", 0),
                "total_tokens": token_budget.get("total_tokens", 0),
                "budget_remaining": token_budget.get("budget_remaining", 0),
                "budget_max": token_budget.get("budget_max", 100000),
                "model": token_budget.get("model", "gpt-4"),
                "should_summarize": token_budget.get("should_summarize", False),
            }
        }
    
    # Emit checkpoint events
    if state.get("evidence"):
        for evidence in state["evidence"]:
            if evidence.get("type") == "checkpoint":
                yield {
                    "type": "checkpoint",
                    "data": {
                        "checkpoint_id": evidence.get("checkpoint_id"),
                        "run_id": state.get("run_id"),
                        "phase": evidence.get("phase"),
                        "timestamp": evidence.get("timestamp"),
                        "token_usage": state.get("token_budget", {}),
                        "message_count": len(state.get("messages", [])),
                        "tool_call_count": len(state.get("tool_calls", [])),
                    }
                }
    
    # Emit citation events (from structured Response)
    if hasattr(response, "citations"):
        for citation in response.citations:
            yield {
                "type": "citation",
                "data": {
                    "source": citation.source,
                    "content": citation.content,
                    "relevance_score": citation.relevance_score,
                    "metadata": citation.metadata,
                }
            }
```

### Step 2: Integrate MeteredToolNode

Update `src/agent/nodes.py` to use MeteredToolNode:

```python
from src.agent.metered_tool_node import create_metered_tool_node

# Replace:
# tool_node = ToolNode(tools)

# With:
tool_node = create_metered_tool_node(tools, publish_metrics=True)
```

### Step 3: Add Checkpoint Node to Graph

Update `src/agent/graph.py` to include checkpoint node:

```python
from src.agent.nodes import checkpoint_node

# Add checkpoint node
workflow.add_node("checkpoint", checkpoint_node)

# Add checkpoint after diagnose
workflow.add_edge("diagnose", "checkpoint")
workflow.add_edge("checkpoint", "verify")

# Or add conditional checkpointing
def should_checkpoint(state: AgentState) -> str:
    """Decide whether to checkpoint."""
    # Checkpoint every 5 messages or when token budget > 50%
    if len(state.get("messages", [])) % 5 == 0:
        return "checkpoint"
    if state.get("token_budget", {}).get("total_tokens", 0) > 50000:
        return "checkpoint"
    return "continue"

workflow.add_conditional_edges(
    "diagnose",
    should_checkpoint,
    {
        "checkpoint": "checkpoint",
        "continue": "verify",
    }
)
```

### Step 4: Deploy BigQuery Table

Run the deployment script:

```bash
# Set project ID
export PROJECT_ID=diatonic-ai-gcp

# Create tool_invocations table
./scripts/create_tool_invocations_table.sh

# Verify table creation
bq show diatonic-ai-gcp:chat_analytics.tool_invocations
```

### Step 5: Create Pub/Sub Topic for Tool Metrics

```bash
# Create topic
gcloud pubsub topics create tool-invocation-metrics \
  --project=diatonic-ai-gcp

# Create subscription
gcloud pubsub subscriptions create tool-metrics-to-bq \
  --topic=tool-invocation-metrics \
  --ack-deadline=60 \
  --project=diatonic-ai-gcp

# Verify
gcloud pubsub topics describe tool-invocation-metrics
```

### Step 6: Deploy Tool Metrics Worker (Optional)

Create Cloud Function to consume tool metrics:

```python
# functions/tool_metrics_worker/main.py
import base64
import json
from google.cloud import bigquery

def process_tool_metrics(event, context):
    """Process tool invocation metrics from Pub/Sub."""
    
    # Decode message
    message_data = base64.b64decode(event['data']).decode('utf-8')
    metrics = json.loads(message_data)
    
    # Insert into BigQuery
    client = bigquery.Client()
    table_id = "diatonic-ai-gcp.chat_analytics.tool_invocations"
    
    errors = client.insert_rows_json(table_id, [metrics])
    
    if errors:
        print(f"Errors inserting rows: {errors}")
        raise Exception("Failed to insert metrics")
    
    print(f"Inserted tool metrics: {metrics['invocation_id']}")
```

Deploy:

```bash
gcloud functions deploy tool-metrics-worker \
  --runtime python311 \
  --trigger-topic tool-invocation-metrics \
  --entry-point process_tool_metrics \
  --region us-central1 \
  --project diatonic-ai-gcp
```

### Step 7: Update Firestore Security Rules

Add rules for checkpoints collection:

```javascript
// firestore.rules
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    
    // Checkpoints collection
    match /checkpoints/{checkpointId} {
      // Allow authenticated users to read their own checkpoints
      allow read: if request.auth != null 
        && request.auth.uid == resource.data.scope.user_id;
      
      // Only backend can write
      allow write: if false;
    }
    
    // ... existing rules ...
  }
}
```

Deploy rules:

```bash
firebase deploy --only firestore:rules
```

### Step 8: Create Firestore Index

Create index for checkpoint queries:

```json
// firestore.indexes.json
{
  "indexes": [
    {
      "collectionGroup": "checkpoints",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "run_id", "order": "ASCENDING" },
        { "fieldPath": "created_at", "order": "DESCENDING" }
      ]
    }
  ]
}
```

Deploy:

```bash
firebase deploy --only firestore:indexes
```

## Frontend Integration

### Step 1: Update Chat Route to Use New Hook

Update `frontend/src/routes/chat.tsx`:

```typescript
import { useChatStream } from "@/hooks/use-chat-stream"
import { TokenBudgetIndicator } from "@/components/chat/TokenBudgetIndicator"
import { ToolCallTimeline } from "@/components/chat/ToolCallTimeline"
import { CitationsPanel } from "@/components/chat/CitationsPanel"

export function ChatPage() {
  const {
    messages,
    isStreaming,
    tokenBudget,
    checkpoints,
    sendMessage,
    stopGeneration,
    clearMessages,
  } = useChatStream()

  return (
    <div className="flex h-screen">
      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4">
          {messages.map((message) => (
            <div key={message.id}>
              <MessageBubble message={message} />
              
              {/* Show tool calls if present */}
              {message.toolCalls && message.toolCalls.length > 0 && (
                <ToolCallTimeline 
                  toolCalls={message.toolCalls} 
                  className="mt-2"
                />
              )}
              
              {/* Show citations if present */}
              {message.citations && message.citations.length > 0 && (
                <CitationsPanel 
                  citations={message.citations} 
                  className="mt-2"
                />
              )}
            </div>
          ))}
        </div>

        {/* Input area */}
        <ChatInput onSend={sendMessage} disabled={isStreaming} />
      </div>

      {/* Sidebar with token budget */}
      <div className="w-80 border-l p-4 space-y-4">
        <TokenBudgetIndicator tokenBudget={tokenBudget} />
        
        {/* Checkpoint history */}
        {checkpoints.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Checkpoints ({checkpoints.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {checkpoints.map((cp) => (
                <div key={cp.checkpointId} className="text-xs">
                  {cp.phase} - {new Date(cp.timestamp).toLocaleTimeString()}
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
```

### Step 2: Update API Types

Add new event types to `frontend/src/types/api.ts`:

```typescript
export const ChatEventTypeSchema = z.enum([
  "session",
  "on_chat_model_stream",
  "on_tool_start",
  "on_tool_end",
  "token_count",      // NEW
  "checkpoint",       // NEW
  "citation",         // NEW
  "error",
])
```

### Step 3: Install Missing Dependencies

Check if @radix-ui/react-progress is installed:

```bash
cd frontend
npm install @radix-ui/react-progress
```

### Step 4: Run Frontend Tests

```bash
cd frontend

# Run component tests
npm test -- TokenBudgetIndicator.test.tsx
npm test -- ToolCallTimeline.test.tsx
npm test -- CitationsPanel.test.tsx

# Run all tests
npm test
```

## Verification

### Backend Verification

1. **Test Token Tracking**:
```bash
# Start backend
python -m uvicorn app.main:app --reload

# Send test message
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Check logs for errors"}'

# Verify token_count events in response
```

2. **Test Checkpoint Creation**:
```bash
# Check Firestore for checkpoints
firebase firestore:get checkpoints --limit 5

# Or use Python
python -c "
from src.agent.checkpoint import list_checkpoints_for_run
checkpoints = list_checkpoints_for_run('test-run-123')
print(f'Found {len(checkpoints)} checkpoints')
"
```

3. **Test Tool Metrics**:
```bash
# Query BigQuery for tool invocations
bq query --use_legacy_sql=false '
SELECT 
  tool_name,
  status,
  AVG(duration_ms) as avg_duration,
  COUNT(*) as count
FROM `diatonic-ai-gcp.chat_analytics.tool_invocations`
WHERE DATE(started_at) = CURRENT_DATE()
GROUP BY tool_name, status
ORDER BY count DESC
'
```

### Frontend Verification

1. **Test Token Budget Display**:
- Send a message
- Verify TokenBudgetIndicator appears
- Check progress bar updates
- Verify color changes at thresholds

2. **Test Tool Timeline**:
- Send message that triggers tools
- Verify ToolCallTimeline appears
- Click to expand tool details
- Check duration and cost display

3. **Test Citations Panel**:
- Send message that returns citations
- Verify CitationsPanel appears
- Check relevance score badges
- Expand to see excerpts

## Monitoring

### BigQuery Queries

**Tool Performance**:
```sql
SELECT 
  tool_name,
  tool_category,
  COUNT(*) as invocations,
  AVG(duration_ms) as avg_duration_ms,
  SUM(token_count) as total_tokens,
  SUM(cost_usd) as total_cost_usd,
  COUNTIF(status = 'error') as error_count
FROM `diatonic-ai-gcp.chat_analytics.tool_invocations`
WHERE DATE(started_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY tool_name, tool_category
ORDER BY invocations DESC
```

**Token Usage Trends**:
```sql
SELECT 
  DATE(event_timestamp) as date,
  SUM(JSON_EXTRACT_SCALAR(metadata, '$.token_usage.total_tokens')) as total_tokens,
  AVG(JSON_EXTRACT_SCALAR(metadata, '$.token_usage.total_tokens')) as avg_tokens_per_session
FROM `diatonic-ai-gcp.chat_analytics.chat_events`
WHERE event_type = 'session_complete'
  AND DATE(event_timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY date
ORDER BY date DESC
```

**Checkpoint Analysis**:
```sql
-- Query Firestore via BigQuery export (if configured)
SELECT 
  phase,
  COUNT(*) as checkpoint_count,
  AVG(CAST(JSON_EXTRACT_SCALAR(token_usage, '$.total_tokens') AS INT64)) as avg_tokens
FROM `diatonic-ai-gcp.firestore_export.checkpoints`
WHERE DATE(_PARTITIONTIME) = CURRENT_DATE()
GROUP BY phase
```

## Troubleshooting

### Issue: Token events not appearing

**Solution**:
1. Check backend logs for token budget updates
2. Verify `update_token_budget()` is called in nodes
3. Check SSE stream includes token_count events
4. Verify frontend hook handles token_count event type

### Issue: Checkpoints not saving

**Solution**:
1. Check Firestore permissions
2. Verify Firebase is initialized
3. Check checkpoint_node is in graph
4. Review backend logs for errors

### Issue: Tool metrics not in BigQuery

**Solution**:
1. Verify Pub/Sub topic exists
2. Check Cloud Function is deployed
3. Review function logs for errors
4. Verify BigQuery table schema matches

### Issue: Frontend components not rendering

**Solution**:
1. Check console for errors
2. Verify all dependencies installed
3. Check component imports
4. Verify event data structure matches types

## Performance Considerations

### Backend
- Checkpoint saves are async (non-blocking)
- Tool metrics publishing is fire-and-forget
- Token tracking adds ~1ms overhead per node
- Structured outputs add ~50ms for validation

### Frontend
- Token budget updates are throttled (max 1/sec)
- Tool timeline uses virtualization for >10 tools
- Citations panel lazy-loads excerpts
- Progress bar uses CSS transforms (GPU accelerated)

## Security Considerations

1. **Firestore Rules**: Only authenticated users can read their checkpoints
2. **BigQuery**: Tool metrics don't include sensitive data
3. **Pub/Sub**: Messages are encrypted in transit
4. **Frontend**: Token budget doesn't expose API keys

## Next Steps

After Phase 3 integration:

1. **Monitor Performance**: Track latency impact
2. **Gather Feedback**: User testing of new UI components
3. **Optimize Queries**: Add indexes based on usage patterns
4. **Phase 4**: Begin MCP Tool Generator implementation

---

**Integration Checklist**:
- [ ] Backend SSE events updated
- [ ] MeteredToolNode integrated
- [ ] Checkpoint node added to graph
- [ ] BigQuery table deployed
- [ ] Pub/Sub topic created
- [ ] Firestore rules updated
- [ ] Frontend hook integrated
- [ ] UI components added to chat
- [ ] Tests passing
- [ ] Monitoring queries created
- [ ] Documentation updated

**Estimated Integration Time**: 4-6 hours
