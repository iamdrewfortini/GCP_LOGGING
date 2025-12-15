# Application Wiring Notes: Universal Data Envelope Integration

**Date:** 2025-12-15
**Project:** diatonic-ai-gcp

---

## Overview

This document describes the changes required in each service to integrate with the Universal Data Envelope canonical views. Changes are organized by service and prioritized by impact.

---

## 1. Glass Pane API (`src/api/main.py`)

### Current State

- Queries `master_logs` directly via `CanonicalQueryBuilder`
- Returns flat JSON response with specific columns
- No awareness of Universal Envelope

### Required Changes

#### 1.1 Add Optional Canonical View Support

```python
# src/api/main.py

# Add configuration option
CANONICAL_VIEW = os.getenv("CANONICAL_VIEW", "central_logging_v1.master_logs")
USE_CANONICAL_ENVELOPE = os.getenv("USE_CANONICAL_ENVELOPE", "false").lower() == "true"

# Update query builder initialization
query_builder = CanonicalQueryBuilder(
    project_id=PROJECT_ID,
    view_name=CANONICAL_VIEW
)
```

#### 1.2 Add Envelope-Aware Response Model

```python
# Add to src/api/main.py or new src/api/models.py

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

class UniversalEnvelope(BaseModel):
    schema_version: str
    event_id: str
    event_type: str
    event_source: str
    event_ts: datetime
    ingest_ts: datetime
    project_id: Optional[str]
    environment: str
    region: Optional[str]
    zone: Optional[str]

    class Config:
        extra = "allow"  # Allow nested structs

class LogEntryCanonical(BaseModel):
    log_id: str
    universal_envelope: Optional[UniversalEnvelope]
    event_timestamp: datetime
    severity: str
    service_name: Optional[str]
    message: Optional[str]
    trace_id: Optional[str]
    span_id: Optional[str]
    is_error: bool
    # ... other fields as needed
```

#### 1.3 Add New Endpoint for Canonical Logs

```python
@app.get("/api/v2/logs")
async def get_logs_canonical(
    hours: int = Query(24, ge=1, le=168),
    severity: Optional[str] = None,
    service: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    envelope: bool = Query(False, description="Include Universal Envelope"),
):
    """
    Get logs with optional Universal Data Envelope.

    Uses canonical view when envelope=true.
    """
    if envelope:
        view_name = "org_logs_norm.v_logs_all_entry_canon"
    else:
        view_name = "central_logging_v1.master_logs"

    qb = CanonicalQueryBuilder(project_id=PROJECT_ID, view_name=view_name)
    # ... rest of query execution
```

#### 1.4 Backward Compatibility

- Keep existing `/api/logs` endpoint unchanged
- New `/api/v2/logs` supports envelope format
- Feature flag `USE_CANONICAL_ENVELOPE` for gradual rollout

---

## 2. Query Builder (`src/glass_pane/query_builder.py`)

### Current State

- Hardcoded to `central_logging_v1.master_logs`
- Returns flat column set
- Good use of parameterized queries

### Required Changes

#### 2.1 Support Configurable View Name

```python
# src/glass_pane/query_builder.py

class CanonicalQueryBuilder:
    # Add fields for envelope support
    ENVELOPE_FIELDS = [
        "universal_envelope.event_id",
        "universal_envelope.event_ts",
        "universal_envelope.service.name AS envelope_service_name",
        "universal_envelope.trace.trace_id AS envelope_trace_id",
        "universal_envelope.actor.user_id AS envelope_user_id",
        "universal_envelope.privacy.pii_risk AS envelope_pii_risk",
    ]

    def __init__(
        self,
        project_id: str,
        view_name: str = "central_logging_v1.master_logs",
        include_envelope: bool = False
    ):
        self.project_id = project_id
        self.view_name = view_name
        self.full_view = f"{project_id}.{view_name}"
        self.include_envelope = include_envelope

    def build_list_query(self, params: LogQueryParams) -> Dict[str, Any]:
        # Dynamic field selection
        fields = self.DISPLAY_FIELDS.copy()
        if self.include_envelope and "org_logs_norm" in self.view_name:
            fields.extend(self.ENVELOPE_FIELDS)

        # ... rest of query building
```

#### 2.2 Add Envelope-Specific Query Methods

```python
def build_envelope_query(self, params: LogQueryParams) -> Dict[str, Any]:
    """Build query that returns full Universal Envelope STRUCT."""
    # ... implementation
    pass

def build_trace_correlation_query(
    self,
    trace_id: str,
    hours: int = 24
) -> Dict[str, Any]:
    """Query logs by trace_id using envelope fields."""
    sql = f"""
    SELECT
        log_id,
        universal_envelope,
        event_timestamp,
        severity,
        message
    FROM `{self.full_view}`
    WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @hours DAY)
        AND trace_id = @trace_id
    ORDER BY event_timestamp ASC
    """
    params = [
        bigquery.ScalarQueryParameter("hours", "INT64", hours),
        bigquery.ScalarQueryParameter("trace_id", "STRING", trace_id),
    ]
    return {"sql": sql.strip(), "params": params}
```

---

## 3. ETL Pipeline (`src/etl/`)

### Current State

- `extractor.py` - Reads from raw sink tables
- `normalizer.py` - Converts to `NormalizedLog` dataclass
- `loader.py` - Writes to `master_logs`
- Well-structured but missing envelope fields

### Required Changes

#### 3.1 Update NormalizedLog Dataclass

```python
# src/etl/normalizer.py

@dataclass
class NormalizedLog:
    # ... existing fields ...

    # Add Universal Envelope fields
    schema_version: str = "1.0.0"
    environment: Optional[str] = None
    correlation_request_id: Optional[str] = None
    correlation_session_id: Optional[str] = None
    correlation_conversation_id: Optional[str] = None
    privacy_pii_risk: Optional[str] = None
    privacy_redaction_state: str = "none"
    privacy_retention_class: str = "standard"
```

#### 3.2 Add Envelope Derivation Methods

```python
# src/etl/normalizer.py

class LogNormalizer:
    def _derive_environment(self, raw: RawLogRecord, normalized: NormalizedLog) -> str:
        """Derive environment from labels or service name."""
        labels = raw.labels or {}

        # Check explicit labels
        if labels.get("env"):
            return labels["env"]
        if labels.get("environment"):
            return labels["environment"]

        # Derive from service name
        svc = normalized.service_name or ""
        if "-dev" in svc or "_dev" in svc:
            return "dev"
        if "-staging" in svc or "_staging" in svc:
            return "staging"

        return "prod"

    def _classify_pii_risk(self, normalized: NormalizedLog) -> str:
        """Classify PII risk based on content patterns."""
        text = (normalized.message or "") + (normalized.text_payload or "")

        # High risk patterns
        if re.search(r"(?i)(password|secret|token|api.?key|authorization)", text):
            return "high"

        # Moderate risk patterns
        if re.search(r"(?i)(email|phone|\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b)", text):
            return "moderate"

        # Low risk patterns
        if re.search(r"(?i)(user.?id|account.?id)", text):
            return "low"

        return "none"

    def _extract_correlation_ids(self, raw: RawLogRecord, normalized: NormalizedLog):
        """Extract correlation IDs from various sources."""
        labels = raw.labels or {}
        json_payload = raw.json_payload or {}

        normalized.correlation_request_id = (
            labels.get("request_id") or
            labels.get("requestId") or
            json_payload.get("request_id") or
            normalized.operation_id
        )

        normalized.correlation_session_id = (
            labels.get("session_id") or
            labels.get("sessionId") or
            json_payload.get("session_id")
        )

        normalized.correlation_conversation_id = (
            labels.get("conversation_id") or
            labels.get("conversationId") or
            json_payload.get("conversation_id")
        )
```

#### 3.3 Update normalize() Method

```python
def normalize(self, raw: RawLogRecord) -> NormalizedLog:
    # ... existing normalization ...

    # Add envelope fields
    normalized.schema_version = "1.0.0"
    normalized.environment = self._derive_environment(raw, normalized)
    normalized.privacy_pii_risk = self._classify_pii_risk(normalized)
    normalized.privacy_retention_class = "audit" if normalized.is_audit else "standard"

    # Extract correlation IDs
    self._extract_correlation_ids(raw, normalized)

    return normalized
```

#### 3.4 Update Loader to_bq_row()

```python
# src/etl/loader.py

def _to_bq_row(self, log: NormalizedLog, batch_id: str) -> Optional[Dict]:
    # ... existing code ...

    return {
        # ... existing fields ...

        # Add envelope fields
        "schema_version": log.schema_version,
        "environment": log.environment,
        "correlation_request_id": log.correlation_request_id,
        "correlation_session_id": log.correlation_session_id,
        "correlation_conversation_id": log.correlation_conversation_id,
        "privacy_pii_risk": log.privacy_pii_risk,
        "privacy_redaction_state": log.privacy_redaction_state,
        "privacy_retention_class": log.privacy_retention_class,

        # ... rest of fields ...
    }
```

---

## 4. Log Processor Cloud Function (`functions/log-processor/`)

### Current State

- Simple Pub/Sub trigger
- Only logs alerts, doesn't write to BigQuery
- No envelope awareness needed

### Required Changes

**None required.** This function only processes alerts and doesn't interact with the data layer.

---

## 5. Generate Log Embedding Function

### Current State

- Reads logs, generates embeddings, writes to Qdrant
- Unknown exact implementation

### Required Changes

#### 5.1 Update Log Query to Use Canonical View

If querying BigQuery directly, update to use `v_logs_all_entry_canon` for consistent schema.

#### 5.2 Include Envelope Fields in Embedding Metadata

```python
# When storing embeddings, include envelope metadata
metadata = {
    "log_id": log["log_id"],
    "event_ts": log["universal_envelope"]["event_ts"],
    "service_name": log["universal_envelope"]["service"]["name"],
    "trace_id": log["universal_envelope"]["trace"]["trace_id"],
    "environment": log["universal_envelope"]["environment"],
    # ... other useful fields for retrieval
}
```

---

## 6. Glass Pane Agent (`src/agent/`)

### Current State

- Uses LangGraph with Gemini
- Has tools for log queries
- Queries via API or direct BigQuery

### Required Changes

#### 6.1 Update Agent Tools

```python
# src/agent/tools.py (if exists)

@tool
def query_logs_by_trace(trace_id: str) -> str:
    """Query all logs for a given trace ID."""
    # Use canonical view for trace correlation
    query = f"""
    SELECT
        universal_envelope.event_ts,
        universal_envelope.service.name,
        severity,
        message
    FROM `diatonic-ai-gcp.org_logs_norm.v_logs_all_entry_canon`
    WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
        AND trace_id = '{trace_id}'
    ORDER BY universal_envelope.event_ts
    """
    # ... execute query
```

#### 6.2 Log Tool Invocations to Agent Table

```python
# src/agent/tools.py or src/agent/graph.py

from google.cloud import bigquery
import uuid

def log_tool_invocation(
    session_id: str,
    tool_name: str,
    tool_input: dict,
    tool_output: dict,
    duration_ms: float,
    status: str,
    error_message: Optional[str] = None,
    user_id: Optional[str] = None
):
    """Log tool invocation to org_agent.tool_invocations."""
    client = bigquery.Client()

    row = {
        "invocation_id": str(uuid.uuid4()),
        "session_id": session_id,
        "invoked_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
        "tool_name": tool_name,
        "tool_version": "1.0.0",
        "tool_input": json.dumps(tool_input),
        "tool_output": json.dumps(tool_output),
        "duration_ms": duration_ms,
        "status": status,
        "error_message": error_message,
        "user_id": user_id,
        "model_name": "gemini-2.5-flash",
        "schema_version": "1.0.0",
        "environment": "prod",
        "invocation_date": datetime.utcnow().strftime("%Y-%m-%d"),
    }

    client.insert_rows_json(
        "diatonic-ai-gcp.org_agent.tool_invocations",
        [row]
    )
```

---

## 7. Frontend (`frontend/`)

### Current State

- React + TypeScript + TanStack
- Queries API endpoints
- Displays log data in tables/lists

### Required Changes

#### 7.1 Add TypeScript Types for Envelope

```typescript
// frontend/src/types/logs.ts

export interface UniversalEnvelope {
  schema_version: string;
  event_id: string;
  event_type: string;
  event_source: string;
  event_ts: string;
  ingest_ts: string;
  project_id: string | null;
  environment: string;
  region: string | null;
  zone: string | null;
  service: {
    name: string | null;
    revision: string | null;
    instance_id: string | null;
    runtime: string | null;
  };
  trace: {
    trace_id: string | null;
    span_id: string | null;
    sampled: boolean | null;
  };
  actor: {
    user_id: string | null;
    tenant_id: string | null;
    org_id: string | null;
    ip: string | null;
    user_agent: string | null;
  };
  correlation: {
    request_id: string | null;
    session_id: string | null;
    conversation_id: string | null;
    job_id: string | null;
    parent_event_id: string | null;
  };
  privacy: {
    pii_risk: 'none' | 'low' | 'moderate' | 'high';
    redaction_state: 'none' | 'partial' | 'full';
    retention_class: 'ephemeral' | 'standard' | 'audit' | 'legal_hold';
  };
}

export interface LogEntryCanonical {
  log_id: string;
  universal_envelope?: UniversalEnvelope;
  event_timestamp: string;
  severity: string;
  service_name: string | null;
  message: string | null;
  trace_id: string | null;
  span_id: string | null;
  is_error: boolean;
  // ... other flat fields
}
```

#### 7.2 Update API Client (Optional)

```typescript
// frontend/src/api/logs.ts

export async function fetchLogsCanonical(
  params: LogQueryParams & { envelope?: boolean }
): Promise<LogEntryCanonical[]> {
  const searchParams = new URLSearchParams({
    hours: params.hours.toString(),
    limit: params.limit.toString(),
    envelope: (params.envelope ?? false).toString(),
  });

  if (params.severity) searchParams.set('severity', params.severity);
  if (params.service) searchParams.set('service', params.service);

  const endpoint = params.envelope ? '/api/v2/logs' : '/api/logs';
  const response = await fetch(`${API_URL}${endpoint}?${searchParams}`);
  return response.json();
}
```

---

## 8. Environment Variables Summary

Add these environment variables to deployment configurations:

| Variable | Default | Description |
|----------|---------|-------------|
| `CANONICAL_VIEW` | `central_logging_v1.master_logs` | BigQuery view to query |
| `USE_CANONICAL_ENVELOPE` | `false` | Enable envelope in responses |
| `AGENT_LOG_INVOCATIONS` | `false` | Log tool invocations to BigQuery |

### Cloud Run Update

```bash
gcloud run services update glass-pane \
  --set-env-vars="CANONICAL_VIEW=central_logging_v1.master_logs" \
  --set-env-vars="USE_CANONICAL_ENVELOPE=false" \
  --region=us-central1
```

---

## 9. Testing Checklist

### Unit Tests

- [ ] `NormalizedLog` dataclass includes new fields
- [ ] `_derive_environment()` returns correct values
- [ ] `_classify_pii_risk()` detects patterns
- [ ] `_to_bq_row()` includes all envelope fields
- [ ] `CanonicalQueryBuilder` generates valid SQL for envelope views

### Integration Tests

- [ ] ETL pipeline writes envelope fields to BigQuery
- [ ] API returns data from canonical view
- [ ] Agent tools work with canonical view
- [ ] Frontend displays envelope data (if enabled)

### End-to-End Tests

- [ ] Full flow: Log ingestion → ETL → Canonical view → API → Frontend
- [ ] Trace correlation query across services
- [ ] Performance benchmarks meet targets
