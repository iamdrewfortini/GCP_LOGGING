"""
Log Normalizer

Normalizes different log payload types into a unified schema.
Handles text, JSON, and proto payloads from various GCP services.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from src.etl.extractor import RawLogRecord

logger = logging.getLogger(__name__)


# Severity level mapping
SEVERITY_LEVELS = {
    "DEFAULT": 0,
    "DEBUG": 100,
    "INFO": 200,
    "NOTICE": 300,
    "WARNING": 400,
    "ERROR": 500,
    "CRITICAL": 600,
    "ALERT": 700,
    "EMERGENCY": 800,
}


@dataclass
class NormalizedLog:
    """Normalized log record with unified schema."""
    # Primary identifiers
    log_id: str
    insert_id: Optional[str]

    # Timestamps
    event_timestamp: datetime
    receive_timestamp: Optional[datetime]
    etl_timestamp: datetime = field(default_factory=datetime.utcnow)

    # Severity
    severity: str = "DEFAULT"
    severity_level: int = 0
    log_type: str = "application"

    # Source tracking
    source_dataset: str = ""
    source_table: str = ""
    source_log_name: Optional[str] = None
    stream_id: str = ""
    stream_direction: str = "INTERNAL"
    stream_flow: str = "BATCH"
    stream_coordinates: Dict = field(default_factory=dict)

    # Resource
    resource_type: Optional[str] = None
    resource_project: Optional[str] = None
    resource_name: Optional[str] = None
    resource_location: Optional[str] = None
    resource_labels: Dict = field(default_factory=dict)

    # Service
    service_name: Optional[str] = None
    service_version: Optional[str] = None
    service_method: Optional[str] = None

    # Content
    message: str = ""
    text_payload: Optional[str] = None
    json_payload: Optional[Dict] = None
    proto_payload: Optional[Dict] = None
    audit_payload: Optional[Dict] = None

    # HTTP context
    http_method: Optional[str] = None
    http_url: Optional[str] = None
    http_status: Optional[int] = None
    http_latency_ms: Optional[float] = None
    http_user_agent: Optional[str] = None
    http_remote_ip: Optional[str] = None
    http_request_size: Optional[int] = None
    http_response_size: Optional[int] = None
    http_full: Optional[Dict] = None

    # Trace
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    trace_sampled: Optional[bool] = None
    parent_span_id: Optional[str] = None

    # Operation
    operation_id: Optional[str] = None
    operation_producer: Optional[str] = None
    operation_first: Optional[bool] = None
    operation_last: Optional[bool] = None

    # Source location
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    source_function: Optional[str] = None

    # Labels
    labels: Dict = field(default_factory=dict)
    user_labels: Dict = field(default_factory=dict)
    system_labels: Dict = field(default_factory=dict)

    # Principal (for audit)
    principal_email: Optional[str] = None
    principal_type: Optional[str] = None
    caller_ip: Optional[str] = None
    caller_network: Optional[str] = None

    # Error context
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    error_stack_trace: Optional[str] = None
    error_group_id: Optional[str] = None

    # Flags
    is_error: bool = False
    is_audit: bool = False
    is_request: bool = False
    has_trace: bool = False

    # Universal Envelope fields (new)
    schema_version: str = "1.0.0"
    environment: Optional[str] = None
    correlation_request_id: Optional[str] = None
    correlation_session_id: Optional[str] = None
    correlation_conversation_id: Optional[str] = None
    privacy_pii_risk: Optional[str] = None
    privacy_redaction_state: str = "none"
    privacy_retention_class: str = "standard"

    # Additional message fields
    message_summary: Optional[str] = None
    message_category: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for BigQuery insertion."""
        return {
            "log_id": self.log_id,
            "insert_id": self.insert_id,
            "event_timestamp": self.event_timestamp.isoformat() if self.event_timestamp else None,
            "receive_timestamp": self.receive_timestamp.isoformat() if self.receive_timestamp else None,
            "etl_timestamp": self.etl_timestamp.isoformat(),
            "severity": self.severity,
            "severity_level": self.severity_level,
            "log_type": self.log_type,
            "source_dataset": self.source_dataset,
            "source_table": self.source_table,
            "source_log_name": self.source_log_name,
            "stream_id": self.stream_id,
            "stream_direction": self.stream_direction,
            "stream_flow": self.stream_flow,
            "stream_coordinates": self.stream_coordinates,
            "resource_type": self.resource_type,
            "resource_project": self.resource_project,
            "resource_name": self.resource_name,
            "resource_location": self.resource_location,
            "resource_labels": json.dumps(self.resource_labels) if self.resource_labels else None,
            "service_name": self.service_name,
            "service_version": self.service_version,
            "service_method": self.service_method,
            "message": self.message,
            "text_payload": self.text_payload,
            "json_payload": json.dumps(self.json_payload) if self.json_payload else None,
            "proto_payload": json.dumps(self.proto_payload) if self.proto_payload else None,
            "audit_payload": json.dumps(self.audit_payload) if self.audit_payload else None,
            "http_method": self.http_method,
            "http_url": self.http_url,
            "http_status": self.http_status,
            "http_latency_ms": self.http_latency_ms,
            "http_user_agent": self.http_user_agent,
            "http_remote_ip": self.http_remote_ip,
            "http_request_size": self.http_request_size,
            "http_response_size": self.http_response_size,
            "http_full": json.dumps(self.http_full) if self.http_full else None,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "trace_sampled": self.trace_sampled,
            "parent_span_id": self.parent_span_id,
            "operation_id": self.operation_id,
            "operation_producer": self.operation_producer,
            "operation_first": self.operation_first,
            "operation_last": self.operation_last,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "source_function": self.source_function,
            "labels": json.dumps(self.labels) if self.labels else None,
            "user_labels": json.dumps(self.user_labels) if self.user_labels else None,
            "system_labels": json.dumps(self.system_labels) if self.system_labels else None,
            "principal_email": self.principal_email,
            "principal_type": self.principal_type,
            "caller_ip": self.caller_ip,
            "caller_network": self.caller_network,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "error_stack_trace": self.error_stack_trace,
            "error_group_id": self.error_group_id,
            "is_error": self.is_error,
            "is_audit": self.is_audit,
            "is_request": self.is_request,
            "has_trace": self.has_trace,
            # Universal Envelope fields
            "schema_version": self.schema_version,
            "environment": self.environment,
            "correlation_request_id": self.correlation_request_id,
            "correlation_session_id": self.correlation_session_id,
            "correlation_conversation_id": self.correlation_conversation_id,
            "privacy_pii_risk": self.privacy_pii_risk,
            "privacy_redaction_state": self.privacy_redaction_state,
            "privacy_retention_class": self.privacy_retention_class,
            # Message metadata
            "message_summary": self.message_summary,
            "message_category": self.message_category,
            # Partition/cluster keys
            "_partition_date": self.event_timestamp.date().isoformat() if self.event_timestamp else None,
            "_cluster_key": f"{self.severity}:{self.service_name or 'unknown'}",
        }


class LogNormalizer:
    """
    Normalizes raw log records into a unified schema.

    Handles:
    - Text payload extraction
    - JSON payload parsing
    - Proto/audit payload parsing
    - HTTP request normalization
    - Service name extraction
    - Error detection
    """

    def __init__(self):
        self.stats = {
            "processed": 0,
            "text_payloads": 0,
            "json_payloads": 0,
            "proto_payloads": 0,
            "audit_logs": 0,
            "errors": 0,
        }

    def normalize(self, raw: RawLogRecord) -> NormalizedLog:
        """
        Normalize a raw log record.

        Args:
            raw: RawLogRecord from extractor

        Returns:
            NormalizedLog with unified schema
        """
        self.stats["processed"] += 1

        # Create base normalized log
        normalized = NormalizedLog(
            log_id=raw.log_id,
            insert_id=raw.insert_id,
            event_timestamp=raw.timestamp,
            receive_timestamp=raw.receive_timestamp,
            severity=raw.severity,
            severity_level=SEVERITY_LEVELS.get(raw.severity, 0),
            source_dataset=raw.source_dataset,
            source_table=raw.source_table,
            source_log_name=raw.log_name,
            stream_id=raw.stream_id,
            stream_direction=raw.stream_direction,
            stream_flow=raw.stream_flow,
            stream_coordinates=raw.stream_coordinates.to_dict(),
            resource_type=raw.resource_type,
            resource_labels=raw.resource_labels,
            labels=raw.labels,
        )

        # Determine log type
        normalized.log_type = self._determine_log_type(raw)

        # Extract resource details
        self._normalize_resource(raw, normalized)

        # Normalize payloads
        self._normalize_payloads(raw, normalized)

        # Normalize HTTP request
        self._normalize_http(raw, normalized)

        # Normalize trace context
        self._normalize_trace(raw, normalized)

        # Normalize operation
        self._normalize_operation(raw, normalized)

        # Normalize source location
        self._normalize_source_location(raw, normalized)

        # Extract principal (for audit logs)
        self._extract_principal(raw, normalized)

        # Detect errors
        self._detect_errors(raw, normalized)

        # Build unified message
        normalized.message = self._build_message(raw, normalized)

        # Set flags
        normalized.is_error = normalized.severity_level >= 500
        normalized.is_audit = "audit" in raw.source_table.lower()
        normalized.is_request = "request" in raw.source_table.lower()
        normalized.has_trace = bool(normalized.trace_id)

        # Populate Universal Envelope fields
        normalized.schema_version = "1.0.0"
        normalized.environment = self._derive_environment(raw, normalized)
        normalized.privacy_pii_risk = self._classify_pii_risk(normalized)
        normalized.privacy_retention_class = "audit" if normalized.is_audit else "standard"
        normalized.privacy_redaction_state = "none"

        # Extract correlation IDs
        self._extract_correlation_ids(raw, normalized)

        # Generate message metadata
        normalized.message_summary = self._generate_message_summary(normalized)
        normalized.message_category = self._categorize_message(normalized)

        return normalized

    def normalize_batch(self, records: List[RawLogRecord]) -> List[NormalizedLog]:
        """Normalize a batch of records."""
        return [self.normalize(r) for r in records]

    def _determine_log_type(self, raw: RawLogRecord) -> str:
        """Determine the log type from source table."""
        table = raw.source_table.lower()

        if "audit" in table:
            return "audit"
        elif "request" in table:
            return "request"
        elif "build" in table:
            return "build"
        elif "error" in table:
            return "error"
        elif "stderr" in table or "stdout" in table:
            return "application"
        elif "system" in table or "syslog" in table:
            return "system"
        else:
            return "application"

    def _normalize_resource(self, raw: RawLogRecord, normalized: NormalizedLog):
        """Extract resource details."""
        labels = raw.resource_labels or {}

        normalized.resource_project = labels.get("project_id")
        normalized.resource_location = labels.get("location") or labels.get("region") or labels.get("zone")

        # Extract service/resource name
        normalized.resource_name = (
            labels.get("service_name") or
            labels.get("function_name") or
            labels.get("instance_id") or
            labels.get("job_name") or
            labels.get("cluster_name")
        )

        # Set service name
        normalized.service_name = (
            normalized.resource_name or
            raw.resource_type or
            "unknown"
        )

        # Extract version if available
        normalized.service_version = labels.get("revision_name") or labels.get("version_id")

    def _normalize_payloads(self, raw: RawLogRecord, normalized: NormalizedLog):
        """Normalize all payload types."""
        # Text payload
        if raw.text_payload:
            self.stats["text_payloads"] += 1
            normalized.text_payload = raw.text_payload

        # JSON payload
        if raw.json_payload:
            self.stats["json_payloads"] += 1
            normalized.json_payload = raw.json_payload
            self._extract_from_json(raw.json_payload, normalized)

        # Proto payload
        if raw.proto_payload:
            self.stats["proto_payloads"] += 1
            normalized.proto_payload = raw.proto_payload
            self._extract_from_proto(raw.proto_payload, normalized)

        # Audit payload
        if raw.audit_payload:
            self.stats["audit_logs"] += 1
            normalized.audit_payload = raw.audit_payload
            self._extract_from_audit(raw.audit_payload, normalized)

    def _extract_from_json(self, payload: Dict, normalized: NormalizedLog):
        """Extract fields from JSON payload."""
        # Common fields in JSON payloads
        if "message" in payload:
            normalized.text_payload = normalized.text_payload or str(payload["message"])
        if "error" in payload:
            normalized.error_message = str(payload["error"])
        if "level" in payload:
            # Some logs use 'level' instead of severity
            level = str(payload["level"]).upper()
            if level in SEVERITY_LEVELS:
                normalized.severity = level
                normalized.severity_level = SEVERITY_LEVELS[level]

    def _extract_from_proto(self, payload: Dict, normalized: NormalizedLog):
        """Extract fields from proto payload."""
        # Extract method name for audit logs
        if "methodName" in payload:
            normalized.service_method = payload["methodName"]
        if "serviceName" in payload:
            normalized.service_name = payload["serviceName"]

        # Extract status
        if "status" in payload:
            status = payload["status"]
            if isinstance(status, dict):
                normalized.error_code = str(status.get("code", ""))
                normalized.error_message = status.get("message")

    def _extract_from_audit(self, payload: Dict, normalized: NormalizedLog):
        """Extract fields from audit log payload."""
        # Method and service
        normalized.service_method = payload.get("methodName")
        normalized.service_name = payload.get("serviceName", normalized.service_name)

        # Request metadata
        request_metadata = payload.get("requestMetadata", {})
        normalized.caller_ip = request_metadata.get("callerIp")
        normalized.caller_network = request_metadata.get("callerNetwork")

        # Authentication info
        auth_info = payload.get("authenticationInfo", {})
        normalized.principal_email = auth_info.get("principalEmail")
        normalized.principal_type = auth_info.get("principalSubject")

        # Status
        status = payload.get("status", {})
        if status:
            normalized.error_code = str(status.get("code", ""))
            normalized.error_message = status.get("message")

    def _normalize_http(self, raw: RawLogRecord, normalized: NormalizedLog):
        """Normalize HTTP request context."""
        if not raw.http_request:
            return

        http = raw.http_request
        normalized.http_full = http

        normalized.http_method = http.get("requestMethod")
        normalized.http_url = http.get("requestUrl")
        normalized.http_status = http.get("status")
        normalized.http_user_agent = http.get("userAgent")
        normalized.http_remote_ip = http.get("remoteIp")

        # Parse latency
        latency = http.get("latency")
        if latency:
            if isinstance(latency, str):
                # Format: "0.123456s"
                try:
                    normalized.http_latency_ms = float(latency.rstrip("s")) * 1000
                except:
                    pass
            elif isinstance(latency, (int, float)):
                normalized.http_latency_ms = float(latency)

        # Sizes
        normalized.http_request_size = http.get("requestSize")
        normalized.http_response_size = http.get("responseSize")

    def _normalize_trace(self, raw: RawLogRecord, normalized: NormalizedLog):
        """Normalize trace context."""
        if raw.trace:
            # Trace format: projects/PROJECT/traces/TRACE_ID
            trace = raw.trace
            if "/" in trace:
                normalized.trace_id = trace.split("/")[-1]
            else:
                normalized.trace_id = trace

        normalized.span_id = raw.span_id
        normalized.trace_sampled = raw.trace_sampled

    def _normalize_operation(self, raw: RawLogRecord, normalized: NormalizedLog):
        """Normalize operation context."""
        if not raw.operation:
            return

        op = raw.operation
        normalized.operation_id = op.get("id")
        normalized.operation_producer = op.get("producer")
        normalized.operation_first = op.get("first")
        normalized.operation_last = op.get("last")

    def _normalize_source_location(self, raw: RawLogRecord, normalized: NormalizedLog):
        """Normalize source location."""
        if not raw.source_location:
            return

        loc = raw.source_location
        normalized.source_file = loc.get("file")
        normalized.source_line = loc.get("line")
        normalized.source_function = loc.get("function")

    def _extract_principal(self, raw: RawLogRecord, normalized: NormalizedLog):
        """Extract principal information."""
        # Already handled in audit payload extraction
        pass

    def _detect_errors(self, raw: RawLogRecord, normalized: NormalizedLog):
        """Detect error information from log content."""
        # Check severity
        if normalized.severity_level >= 500:
            self.stats["errors"] += 1

        # Look for error patterns in text
        text = normalized.text_payload or ""
        if not normalized.error_message:
            # Common error patterns
            error_patterns = [
                r"error[:\s]+(.+?)(?:\n|$)",
                r"exception[:\s]+(.+?)(?:\n|$)",
                r"failed[:\s]+(.+?)(?:\n|$)",
            ]
            for pattern in error_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    normalized.error_message = match.group(1)[:500]
                    break

        # Extract stack trace
        if "Traceback" in text or "at " in text:
            normalized.error_stack_trace = text[:5000]

    def _build_message(self, raw: RawLogRecord, normalized: NormalizedLog) -> str:
        """Build unified message from all sources."""
        parts = []

        # Primary content
        if normalized.text_payload:
            parts.append(normalized.text_payload)
        elif normalized.json_payload:
            msg = normalized.json_payload.get("message")
            if msg:
                parts.append(str(msg))
            else:
                parts.append(json.dumps(normalized.json_payload, default=str)[:1000])
        elif normalized.audit_payload:
            method = normalized.service_method or ""
            service = normalized.service_name or ""
            parts.append(f"Audit: {service} {method}")

        # Add context
        if normalized.http_method and normalized.http_url:
            parts.append(f"[HTTP {normalized.http_method} {normalized.http_url}]")

        if normalized.error_message and normalized.error_message not in " ".join(parts):
            parts.append(f"Error: {normalized.error_message}")

        message = " | ".join(parts) if parts else f"[{normalized.severity}] {normalized.log_type}"

        # Truncate if too long
        if len(message) > 10000:
            message = message[:10000] + "..."

        return message

    def get_stats(self) -> Dict:
        """Get normalization statistics."""
        return self.stats.copy()

    def _derive_environment(self, raw: RawLogRecord, normalized: NormalizedLog) -> str:
        """
        Derive environment from labels or service name.

        Priority:
        1. Explicit 'env' or 'environment' label
        2. Service name patterns (-dev, -staging, -prod)
        3. Default to 'prod'
        """
        labels = raw.labels or {}

        # Check explicit labels
        if labels.get("env"):
            return labels["env"]
        if labels.get("environment"):
            return labels["environment"]

        # Check resource labels
        resource_labels = raw.resource_labels or {}
        if resource_labels.get("env"):
            return resource_labels["env"]
        if resource_labels.get("environment"):
            return resource_labels["environment"]

        # Derive from service name
        svc = normalized.service_name or ""
        svc_lower = svc.lower()
        if "-dev" in svc_lower or "_dev" in svc_lower:
            return "dev"
        if "-staging" in svc_lower or "_staging" in svc_lower:
            return "staging"
        if "-test" in svc_lower or "_test" in svc_lower:
            return "test"

        return "prod"

    def _classify_pii_risk(self, normalized: NormalizedLog) -> str:
        """
        Classify PII risk based on content patterns.

        Returns:
            'high': Contains secrets, passwords, tokens
            'moderate': Contains emails, IPs, phone numbers
            'low': Contains user IDs or account IDs
            'none': No PII detected
        """
        # Combine text sources for analysis
        text_parts = []
        if normalized.message:
            text_parts.append(normalized.message)
        if normalized.text_payload:
            text_parts.append(normalized.text_payload)
        if normalized.json_payload:
            text_parts.append(json.dumps(normalized.json_payload, default=str))

        text = " ".join(text_parts).lower()

        if not text:
            return "none"

        # High risk patterns (secrets, credentials)
        high_risk_patterns = [
            r"password\s*[=:]\s*\S+",
            r"secret\s*[=:]\s*\S+",
            r"api[_-]?key\s*[=:]\s*\S+",
            r"token\s*[=:]\s*\S+",
            r"authorization\s*[=:]\s*bearer",
            r"private[_-]?key",
            r"access[_-]?token",
            r"refresh[_-]?token",
        ]
        for pattern in high_risk_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return "high"

        # Moderate risk patterns (PII)
        moderate_risk_patterns = [
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",  # Email
            r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",  # IP address
            r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",  # Phone number
            r"ssn\s*[=:]\s*\d",  # SSN reference
        ]
        for pattern in moderate_risk_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return "moderate"

        # Low risk patterns (identifiers)
        low_risk_patterns = [
            r"user[_-]?id\s*[=:]\s*\S+",
            r"account[_-]?id\s*[=:]\s*\S+",
            r"customer[_-]?id\s*[=:]\s*\S+",
        ]
        for pattern in low_risk_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return "low"

        return "none"

    def _extract_correlation_ids(self, raw: RawLogRecord, normalized: NormalizedLog):
        """
        Extract correlation IDs from various sources.

        Populates:
        - correlation_request_id
        - correlation_session_id
        - correlation_conversation_id
        """
        labels = raw.labels or {}
        json_payload = raw.json_payload or {}

        # Request ID - check multiple sources
        normalized.correlation_request_id = (
            labels.get("request_id") or
            labels.get("requestId") or
            labels.get("x-request-id") or
            json_payload.get("request_id") or
            json_payload.get("requestId") or
            normalized.operation_id
        )

        # Session ID
        normalized.correlation_session_id = (
            labels.get("session_id") or
            labels.get("sessionId") or
            json_payload.get("session_id") or
            json_payload.get("sessionId")
        )

        # Conversation ID (for chat/AI interactions)
        normalized.correlation_conversation_id = (
            labels.get("conversation_id") or
            labels.get("conversationId") or
            json_payload.get("conversation_id") or
            json_payload.get("conversationId") or
            json_payload.get("chat_id") or
            json_payload.get("thread_id")
        )

    def _generate_message_summary(self, normalized: NormalizedLog) -> Optional[str]:
        """Generate a brief summary of the message (first 200 chars)."""
        if normalized.message:
            summary = normalized.message[:200]
            if len(normalized.message) > 200:
                summary += "..."
            return summary
        return None

    def _categorize_message(self, normalized: NormalizedLog) -> str:
        """
        Categorize the message based on content patterns.

        Returns category like: 'request', 'error', 'audit', 'metric', 'debug'
        """
        if normalized.is_audit:
            return "audit"
        if normalized.is_error:
            return "error"
        if normalized.http_method:
            return "request"

        # Check message content
        message = (normalized.message or "").lower()
        if any(word in message for word in ["metric", "gauge", "counter", "histogram"]):
            return "metric"
        if any(word in message for word in ["debug", "trace", "verbose"]):
            return "debug"
        if any(word in message for word in ["warn", "warning"]):
            return "warning"

        return "info"
