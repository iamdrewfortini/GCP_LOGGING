"""
GraphQL Types
"""

import strawberry
from strawberry.scalars import JSON
from datetime import datetime
from typing import List, Optional
from enum import Enum

# Enums
@strawberry.enum
class Severity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    ALERT = "ALERT"
    EMERGENCY = "EMERGENCY"

@strawberry.enum
class LogType(str, Enum):
    APPLICATION = "application"
    SYSTEM = "system"
    AUDIT = "audit"

# Types
@strawberry.type
class LogEntry:
    id: str
    event_ts: datetime
    ingest_ts: datetime
    project_id: str
    env: str
    region: str
    service_name: str
    severity: Severity
    event_type: str
    correlation_ids: List[str]
    labels: JSON
    message: Optional[str]
    body: Optional[str]
    http_method: Optional[str]
    http_status: Optional[int]
    trace_id: Optional[str]
    span_id: Optional[str]

@strawberry.type
class LogQuery:
    logs: List[LogEntry]
    total_count: int
    has_more: bool

@strawberry.type
class Health:
    ok: bool
    version: str
    services: JSON

@strawberry.type
class ServiceInfo:
    name: str
    region: str
    env: str

# Inputs
@strawberry.input
class LogFilter:
    hours: Optional[int] = None
    limit: Optional[int] = 100
    severity: Optional[Severity] = None
    service_name: Optional[str] = None
    region: Optional[str] = None
    env: Optional[str] = None

@strawberry.input
class RunQueryInput:
    query: str
    variables: Optional[JSON] = None

@strawberry.input
class EnqueueEmbeddingJobInput:
    log_ids: List[str]
    priority: Optional[int] = 1

@strawberry.input
class SetTagInput:
    id: str
    tag: str

# Placeholder for other types
@strawberry.type
class LogChunk:
    id: str
    content: str

@strawberry.type
class EmbeddingJob:
    id: str
    status: str
    log_ids: List[str]

@strawberry.type
class ChatEvent:
    id: str
    session_id: str
    message: str
    timestamp: datetime

@strawberry.type
class ToolInvocation:
    id: str
    tool_name: str
    input: JSON
    output: JSON