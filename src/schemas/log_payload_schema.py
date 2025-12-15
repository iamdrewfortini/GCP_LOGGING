"""
Canonical payload schema for logs in Qdrant collection.

Version: v1
Based on spec payload_schema_v1.

Uses Pydantic for strict validation.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


class Severity(str, Enum):
    DEFAULT = "DEFAULT"
    DEBUG = "DEBUG"
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    ALERT = "ALERT"
    EMERGENCY = "EMERGENCY"


class LogType(str, Enum):
    # Config-driven, add as needed
    APPLICATION = "application"
    SYSTEM = "system"
    AUDIT = "audit"
    # Add more from config


class LogPayloadV1(BaseModel):
    """
    Canonical log payload schema v1.

    Required fields: log_id, timestamp, message (or body)
    Derived fields: timestamp_year, etc. (added during normalization)
    """

    # Primary identifiers
    log_id: str = Field(..., description="Unique log entry ID")
    tenant_id: str = Field(..., description="Tenant identifier for multitenancy")
    service_name: str = Field(..., description="Service or component name")
    severity: Severity = Field(..., description="Log severity level")
    log_type: LogType = Field(..., description="Type of log (application, system, etc.)")

    # Timestamps
    timestamp: datetime = Field(..., description="Log timestamp")
    timestamp_year: int = Field(default=0, description="Derived year for filtering")
    timestamp_month: int = Field(default=0, description="Derived month")
    timestamp_day: int = Field(default=0, description="Derived day")
    timestamp_hour: int = Field(default=0, description="Derived hour")

    # HTTP context (optional)
    http_method: Optional[str] = Field(None, description="HTTP method")
    http_status: Optional[int] = Field(None, description="HTTP status code")
    trace_id: Optional[str] = Field(None, description="Trace ID")
    span_id: Optional[str] = Field(None, description="Span ID")

    # Source info
    source_table: str = Field(..., description="BigQuery table source")

    # Content
    message: Optional[str] = Field(None, description="Text message")
    body: Optional[str] = Field(None, description="Additional body text")

    # Metadata
    labels: Optional[Dict[str, Any]] = Field(None, description="Key-value labels")
    attrs: Optional[Dict[str, Any]] = Field(None, description="Additional attributes")

    @model_validator(mode='after')
    def derive_time_fields(self):
        if self.timestamp:
            self.timestamp_year = self.timestamp.year
            self.timestamp_month = self.timestamp.month
            self.timestamp_day = self.timestamp.day
            self.timestamp_hour = self.timestamp.hour
        return self

    @field_validator('message', 'body')
    @classmethod
    def check_content(cls, v):
        if v and len(v) > 10000:  # Arbitrary limit, can be config
            raise ValueError("Content too long, truncate during normalization")
        return v

    class Config:
        # Allow extra fields? No, strict
        extra = 'forbid'


# For normalization: function to prepare raw payload
def normalize_log_payload(raw_payload: Dict[str, Any]) -> LogPayloadV1:
    """
    Normalize raw log payload into canonical schema.
    Handles timestamp parsing, validates.
    """
    # Assume raw_payload has timestamp as datetime or str
    if 'timestamp' in raw_payload and isinstance(raw_payload['timestamp'], str):
        raw_payload['timestamp'] = datetime.fromisoformat(raw_payload['timestamp'])

    return LogPayloadV1(**raw_payload)