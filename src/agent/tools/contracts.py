from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class BQDryRunInput(BaseModel):
    sql: str
    params: Optional[Dict[str, Any]] = None

class BQDryRunOutput(BaseModel):
    bytes_estimate: int
    referenced_tables: List[str]
    warnings: List[str] = []

class BQQueryInput(BaseModel):
    sql: str
    params: Optional[Dict[str, Any]] = None
    max_rows: int = 1000

class BQQueryOutput(BaseModel):
    job_id: str
    rows: List[Dict[str, Any]]
    total_bytes_processed: int
    cache_hit: bool

class LogEvent(BaseModel):
    """Log event model matching master_logs schema."""
    event_timestamp: str  # Previously event_ts
    severity: str
    service_name: str  # Previously service
    source_table: str
    message: str  # Previously display_message
    json_payload: Optional[Dict[str, Any]] = None
    trace_id: Optional[str] = None  # Previously trace
    span_id: Optional[str] = None  # Previously spanId
    http_url: Optional[str] = None  # Previously requestUrl
    http_method: Optional[str] = None  # Previously requestMethod
    http_status: Optional[int] = None  # Previously status
    http_latency_ms: Optional[float] = None  # Previously latency_s
    http_user_agent: Optional[str] = None  # Previously userAgent
    http_remote_ip: Optional[str] = None  # Previously remoteIp
    error_fingerprint: str
    # Additional master_logs fields
    stream_id: Optional[str] = None
    log_type: Optional[str] = None
    resource_type: Optional[str] = None

class TraceSpan(BaseModel):
    spanId: str
    parentSpanId: Optional[str] = None
    name: str
    startTime: str
    endTime: str
    attributes: Dict[str, Any]
    status: Optional[Dict[str, Any]] = None

class MetricPoint(BaseModel):
    timestamp: str
    value: float
    labels: Dict[str, str]

class AgentRunArtifact(BaseModel):
    run_id: str
    kind: str
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
