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
    event_ts: str
    severity: str
    service: str
    source_table: str
    display_message: str
    json_payload: Optional[Dict[str, Any]] = None
    trace: Optional[str] = None
    spanId: Optional[str] = None
    requestUrl: Optional[str] = None
    requestMethod: Optional[str] = None
    status: Optional[int] = None
    latency_s: Optional[float] = None
    userAgent: Optional[str] = None
    remoteIp: Optional[str] = None
    error_fingerprint: str

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
