# Risks & Mitigations

**Date:** 2025-12-15  
**Status:** Proposed  
**Version:** 1.0

---

## Risk Matrix

| Risk | Likelihood | Impact | Severity | Mitigation Priority |
|------|-----------|--------|----------|-------------------|
| Cost overrun (BigQuery/Vertex AI) | High | High | **CRITICAL** | P0 |
| Token budget overflow | Medium | High | **HIGH** | P0 |
| Vector search latency | Medium | Medium | **MEDIUM** | P1 |
| Pub/Sub message loss | Low | High | **MEDIUM** | P1 |
| Generated tool security breach | Low | Critical | **HIGH** | P0 |
| Firestore quota exhaustion | Medium | Medium | **MEDIUM** | P1 |
| Data privacy violation | Low | Critical | **CRITICAL** | P0 |
| Performance degradation | Medium | Medium | **MEDIUM** | P2 |

---

## 1. Cost Overrun (BigQuery/Vertex AI)

### Risk Description
Uncontrolled BigQuery queries or embedding generation could result in unexpected costs exceeding budget.

### Likelihood: HIGH
- Users can trigger arbitrary queries
- Embeddings generated for every message
- No hard cost limits in place

### Impact: HIGH
- Could exceed monthly budget ($1000+)
- Requires emergency shutdown
- Business disruption

### Mitigations

#### Prevention
```python
# Enforce maximum bytes billed per query
job_config = bigquery.QueryJobConfig(
    maximum_bytes_billed=50_000_000_000,  # 50GB = ~$0.25
    use_query_cache=True
)

# Rate limit embeddings per user
MAX_EMBEDDINGS_PER_USER_PER_DAY = 1000

# Deduplicate embeddings by text hash
text_hash = hashlib.sha256(text.encode()).hexdigest()
if embedding_exists(text_hash):
    return cached_embedding_id
```

#### Detection
```sql
-- Daily cost monitoring query
SELECT
  DATE(creation_time) as date,
  SUM(total_bytes_billed) / POW(1024, 4) as tb_billed,
  SUM(total_bytes_billed) / POW(1024, 4) * 5 as estimated_cost_usd
FROM `diatonic-ai-gcp.region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE DATE(creation_time) >= CURRENT_DATE() - 7
GROUP BY date
ORDER BY date DESC;
```

#### Response
1. Set up budget alerts in GCP Console ($100, $500, $1000 thresholds)
2. Create Cloud Function to disable expensive features if budget exceeded
3. Implement circuit breaker pattern for BigQuery queries

```python
# Circuit breaker
class CostCircuitBreaker:
    def __init__(self, daily_limit_usd: float = 100.0):
        self.daily_limit = daily_limit_usd
        self.current_spend = 0.0
        self.is_open = False
    
    def check(self):
        if self.is_open:
            raise CircuitBreakerOpen("Daily cost limit exceeded")
        
        # Check current spend from BigQuery
        self.current_spend = get_daily_spend()
        if self.current_spend > self.daily_limit:
            self.is_open = True
            send_alert("Cost limit exceeded!")
            raise CircuitBreakerOpen("Daily cost limit exceeded")
```

---

## 2. Token Budget Overflow

### Risk Description
Long conversations could exceed context window (1M tokens for Gemini 2.5 Flash), causing errors or truncation.

### Likelihood: MEDIUM
- Users may have very long sessions
- Tool outputs can be large
- No automatic summarization

### Impact: HIGH
- Conversation breaks mid-session
- Loss of context
- Poor user experience

### Mitigations

#### Prevention
```python
# Enforce token budget in state
class TokenBudgetManager:
    def __init__(self, max_tokens: int = 100_000):  # Conservative limit
        self.max_tokens = max_tokens
        self.tokens_used = 0
    
    def check_budget(self, additional_tokens: int) -> bool:
        return (self.tokens_used + additional_tokens) <= self.max_tokens
    
    def reserve_tokens(self, count: int):
        if not self.check_budget(count):
            # Trigger summarization
            raise TokenBudgetExceeded("Need to summarize conversation")
        self.tokens_used += count
```

#### Detection
```python
# Monitor token usage in SSE stream
if token_budget["percentUsed"] > 80:
    emit_sse_event("warning", {
        "message": "Approaching token limit, conversation may be summarized soon"
    })
```

#### Response
1. Implement automatic summarization when 80% budget used
2. Store summaries in Firestore checkpoints
3. Provide UI warning to user
4. Allow user to start new session with summary

---

## 3. Vector Search Latency

### Risk Description
Semantic search queries could be slow (>1s), degrading user experience.

### Likelihood: MEDIUM
- Vertex AI Vector Search can have variable latency
- Large indexes (>1M vectors) slower
- Cold start issues

### Impact: MEDIUM
- Slower chat responses
- User frustration
- Increased Cloud Run costs (longer request duration)

### Mitigations

#### Prevention
```python
# Set aggressive timeout
async def semantic_search_with_timeout(query: str, timeout_sec: float = 0.5):
    try:
        return await asyncio.wait_for(
            vector_service.semantic_search(query),
            timeout=timeout_sec
        )
    except asyncio.TimeoutError:
        # Fall back to keyword search
        return keyword_search(query)
```

#### Detection
```python
# Track p95 latency
@tool
def semantic_search_logs(query: str):
    start_time = time.time()
    results = vector_service.semantic_search(query)
    duration_ms = (time.time() - start_time) * 1000
    
    # Log metric
    publish_metric("vector_search_latency_ms", duration_ms)
    
    if duration_ms > 1000:
        logger.warning(f"Slow vector search: {duration_ms}ms")
    
    return results
```

#### Response
1. Cache frequently searched queries in Redis
2. Use approximate nearest neighbor (ANN) with lower accuracy for speed
3. Implement hybrid search (fast keyword + slow semantic in parallel)
4. Pre-warm index with common queries

---

## 4. Pub/Sub Message Loss

### Risk Description
Messages published to Pub/Sub could be lost due to network issues, quota limits, or subscriber failures.

### Likelihood: LOW
- Pub/Sub is highly reliable (99.95% SLA)
- But subscriber failures can cause message loss

### Impact: HIGH
- Chat events not logged to BigQuery
- Embeddings not generated
- Analytics incomplete

### Mitigations

#### Prevention
```python
# Use dead letter queue
gcloud pubsub subscriptions create embedding-worker \
  --topic=embedding-jobs \
  --dead-letter-topic=embedding-jobs-dlq \
  --max-delivery-attempts=5

# Implement idempotency
def process_chat_event(event):
    event_id = event["event_id"]
    
    # Check if already processed
    if event_already_processed(event_id):
        logger.info(f"Skipping duplicate event: {event_id}")
        return
    
    # Process event
    insert_to_bigquery(event)
    
    # Mark as processed
    mark_event_processed(event_id)
```

#### Detection
```python
# Monitor subscription backlog
from google.cloud import monitoring_v3

def check_subscription_backlog():
    client = monitoring_v3.MetricServiceClient()
    
    # Query backlog metric
    results = client.list_time_series(
        name=f"projects/{project_id}",
        filter='metric.type="pubsub.googleapis.com/subscription/num_undelivered_messages"'
    )
    
    for result in results:
        if result.points[0].value.int64_value > 1000:
            send_alert(f"High backlog: {result.points[0].value.int64_value}")
```

#### Response
1. Set up alerting for subscription backlog > 1000 messages
2. Implement retry logic with exponential backoff
3. Manual replay from dead letter queue if needed
4. Backfill missing data from Firestore to BigQuery

---

## 5. Generated Tool Security Breach

### Risk Description
A malicious or buggy tool spec could generate code that:
- Deletes data
- Exfiltrates sensitive information
- Causes denial of service

### Likelihood: LOW
- Tool generation is controlled
- Safety checks in place

### Impact: CRITICAL
- Data loss
- Security breach
- Compliance violation

### Mitigations

#### Prevention
```python
# Strict validation of tool specs
class ToolSpec(BaseModel):
    @validator("safety")
    def validate_safety(cls, v):
        # Require deny_keywords
        if not v.get("deny_keywords"):
            raise ValueError("deny_keywords required")
        
        # Require allowed_datasets
        if not v.get("allowed_datasets"):
            raise ValueError("allowed_datasets required")
        
        # Deny dangerous keywords
        dangerous = ["DROP", "DELETE", "TRUNCATE", "ALTER"]
        for keyword in dangerous:
            if keyword not in v["deny_keywords"]:
                raise ValueError(f"Must deny keyword: {keyword}")
        
        return v

# Runtime enforcement
class ToolRuntime:
    def _validate_input(self, input_data: Dict[str, Any]):
        if "sql" in input_data:
            sql = input_data["sql"].upper()
            
            # Check deny list
            for keyword in self.safety["deny_keywords"]:
                if keyword in sql:
                    raise SecurityError(f"Denied keyword: {keyword}")
            
            # Check dataset restrictions
            datasets = extract_datasets(sql)
            for dataset in datasets:
                if dataset not in self.safety["allowed_datasets"]:
                    raise SecurityError(f"Dataset not allowed: {dataset}")
```

#### Detection
```python
# Audit all tool invocations
def _log_invocation(self, invocation_id, input_data, output_data, status):
    # Log to BigQuery
    row = {
        "invocation_id": invocation_id,
        "tool_name": self.tool_id,
        "input_summary": str(input_data)[:500],
        "output_summary": str(output_data)[:500],
        "status": status,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    self.bq.insert_rows_json("chat_analytics.tool_invocations", [row])
    
    # Alert on suspicious activity
    if status == "error" and "SecurityError" in str(output_data):
        send_security_alert(f"Security violation in tool {self.tool_id}")
```

#### Response
1. Code review all generated tools before deployment
2. Implement approval workflow for new tools
3. Run generated tools in sandbox environment first
4. Maintain audit log of all tool generation and execution
5. Ability to instantly disable tools via registry

---

## 6. Firestore Quota Exhaustion

### Risk Description
High traffic could exceed Firestore quotas (reads, writes, storage).

### Likelihood: MEDIUM
- Default quotas: 50K reads/sec, 10K writes/sec
- Storage: 1GB free, then $0.18/GB/month

### Impact: MEDIUM
- Chat functionality degraded
- Users unable to access sessions
- Increased costs

### Mitigations

#### Prevention
```python
# Implement caching
import redis

cache = redis.Redis(host='localhost', port=6379)

def get_session_cached(session_id: str):
    # Check cache first
    cached = cache.get(f"session:{session_id}")
    if cached:
        return json.loads(cached)
    
    # Fetch from Firestore
    session = firebase_service.get_session(session_id)
    
    # Cache for 5 minutes
    cache.setex(f"session:{session_id}", 300, json.dumps(session))
    
    return session

# Batch writes
def batch_write_messages(session_id: str, messages: List[Dict]):
    batch = db.batch()
    for msg in messages:
        ref = db.collection("sessions").document(session_id).collection("messages").document()
        batch.set(ref, msg)
    batch.commit()  # Single write operation
```

#### Detection
```python
# Monitor Firestore usage
from google.cloud import monitoring_v3

def check_firestore_usage():
    client = monitoring_v3.MetricServiceClient()
    
    # Query read/write metrics
    results = client.list_time_series(
        name=f"projects/{project_id}",
        filter='metric.type="firestore.googleapis.com/document/read_count"'
    )
    
    for result in results:
        reads_per_sec = result.points[0].value.int64_value
        if reads_per_sec > 40000:  # 80% of quota
            send_alert(f"High Firestore read rate: {reads_per_sec}/sec")
```

#### Response
1. Request quota increase from GCP support
2. Implement read-through cache (Redis/Memorystore)
3. Archive old sessions to GCS
4. Optimize queries (use indexes, limit results)

---

## 7. Data Privacy Violation

### Risk Description
Sensitive data (PII, credentials) could be:
- Logged to BigQuery
- Sent to LLM
- Stored in embeddings
- Exposed in UI

### Likelihood: LOW
- Redaction layer in place
- But new data sources could bypass

### Impact: CRITICAL
- GDPR/CCPA violation
- Legal liability
- Reputation damage

### Mitigations

#### Prevention
```python
# Comprehensive redaction
class Redactor:
    def __init__(self):
        self.patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
            "credit_card": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
            "api_key": r'\b[A-Za-z0-9]{32,}\b'
        }
    
    def scrub_data(self, data: Any) -> Any:
        if isinstance(data, str):
            for pattern_name, pattern in self.patterns.items():
                data = re.sub(pattern, f"[REDACTED_{pattern_name.upper()}]", data)
        elif isinstance(data, dict):
            return {k: self.scrub_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.scrub_data(item) for item in data]
        return data

# Apply redaction at every boundary
redactor = Redactor()

# Before LLM
messages = [redactor.scrub_data(msg) for msg in messages]

# Before BigQuery
event_data = redactor.scrub_data(event_data)

# Before embedding
text = redactor.scrub_data(text)
```

#### Detection
```python
# Scan for PII in stored data
def scan_for_pii(table_id: str):
    from google.cloud import dlp_v2
    
    dlp = dlp_v2.DlpServiceClient()
    
    # Configure DLP scan
    inspect_config = {
        "info_types": [
            {"name": "EMAIL_ADDRESS"},
            {"name": "PHONE_NUMBER"},
            {"name": "CREDIT_CARD_NUMBER"},
            {"name": "US_SOCIAL_SECURITY_NUMBER"}
        ]
    }
    
    # Scan BigQuery table
    response = dlp.inspect_content(
        parent=f"projects/{project_id}",
        inspect_config=inspect_config,
        item={"table": {"project_id": project_id, "dataset_id": "chat_analytics", "table_id": table_id}}
    )
    
    if response.result.findings:
        send_alert(f"PII found in {table_id}: {len(response.result.findings)} findings")
```

#### Response
1. Run DLP scans weekly on all tables
2. Implement data retention policies (auto-delete after 90 days)
3. Provide user data export/deletion API (GDPR compliance)
4. Encrypt sensitive fields at rest
5. Audit access logs regularly

---

## 8. Performance Degradation

### Risk Description
New features (embeddings, vector search, dual-write) could slow down chat responses.

### Likelihood: MEDIUM
- Adding complexity to request path
- External API calls (Vertex AI)
- Database writes

### Impact: MEDIUM
- Slower user experience
- Higher Cloud Run costs
- User churn

### Mitigations

#### Prevention
```python
# Async operations
async def chat_handler(request: ChatRequest):
    # Synchronous: Write to Firestore (fast)
    firebase_service.add_message(session_id, "user", request.message)
    
    # Asynchronous: Publish to Pub/Sub (fire-and-forget)
    asyncio.create_task(
        pubsub_client.publish(topic, event_data)
    )
    
    # Asynchronous: Generate embedding (don't wait)
    asyncio.create_task(
        vector_service.embed_and_store(request.message)
    )
    
    # Synchronous: Stream response (user-facing)
    return StreamingResponse(event_stream())

# Parallel tool execution
async def execute_tools_parallel(tools: List[Tool]):
    results = await asyncio.gather(*[
        tool.execute() for tool in tools
    ])
    return results
```

#### Detection
```python
# Track p95 latency
import time

@app.middleware("http")
async def track_latency(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    
    # Log metric
    publish_metric("request_latency_ms", duration_ms, {
        "endpoint": request.url.path,
        "method": request.method
    })
    
    # Alert on slow requests
    if duration_ms > 5000:  # 5 seconds
        logger.warning(f"Slow request: {request.url.path} took {duration_ms}ms")
    
    return response
```

#### Response
1. Set up latency alerts (p95 > 2s)
2. Implement caching for expensive operations
3. Use Cloud Run min instances to avoid cold starts
4. Profile slow requests with Cloud Trace
5. Optimize database queries (add indexes)

---

## Compliance & Governance

### Data Retention
- **Firestore:** 30 days active, 90 days archived, then delete
- **BigQuery:** 7 years (compliance requirement)
- **GCS:** 1 year (log archives)

### Access Control
- **Firestore:** User-scoped via security rules
- **BigQuery:** Service account with least privilege
- **Vertex AI:** Project-level IAM

### Audit Trail
- All tool invocations logged to BigQuery
- All tool generation logged to Firestore
- All API requests logged to Cloud Logging

### Incident Response Plan
1. **Detection:** Automated alerts via Cloud Monitoring
2. **Triage:** On-call engineer investigates
3. **Mitigation:** Disable affected feature via feature flag
4. **Resolution:** Deploy fix, verify, re-enable
5. **Post-mortem:** Document incident, update runbook

---

## Monitoring Dashboard

### Key Metrics to Track
1. **Cost:** Daily spend by service (BigQuery, Vertex AI, Firestore)
2. **Performance:** p50/p95/p99 latency for /api/chat
3. **Reliability:** Error rate, success rate by endpoint
4. **Usage:** DAU, messages per user, tokens per session
5. **Quality:** Tool success rate, embedding generation rate

### Alerts to Configure
- Daily cost > $100
- Error rate > 5%
- p95 latency > 2s
- Pub/Sub backlog > 1000
- Firestore quota > 80%
- Token budget exceeded > 10 times/day

---

**End of Risks & Mitigations**
