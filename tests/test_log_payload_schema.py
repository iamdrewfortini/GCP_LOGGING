"""
Tests for log payload schema validation.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError
from src.schemas.log_payload_schema import LogPayloadV1, normalize_log_payload, Severity, LogType


def test_valid_payload():
    payload = {
        "log_id": "test-log-123",
        "tenant_id": "tenant1",
        "service_name": "my-service",
        "severity": "INFO",
        "log_type": "application",
        "timestamp": datetime(2023, 10, 1, 12, 0, 0),
        "source_table": "logs.app_logs",
        "message": "Test message"
    }
    log = LogPayloadV1(**payload)
    assert log.log_id == "test-log-123"
    assert log.timestamp_year == 2023
    assert log.severity == Severity.INFO


def test_derived_fields():
    payload = {
        "log_id": "test-log-123",
        "tenant_id": "tenant1",
        "service_name": "my-service",
        "severity": "ERROR",
        "log_type": "system",
        "timestamp": datetime(2023, 5, 15, 14, 30, 0),
        "source_table": "logs.sys_logs"
    }
    log = LogPayloadV1(**payload)
    assert log.timestamp_year == 2023
    assert log.timestamp_month == 5
    assert log.timestamp_day == 15
    assert log.timestamp_hour == 14


def test_missing_required_field():
    payload = {
        "tenant_id": "tenant1",
        "service_name": "my-service",
        "severity": "INFO",
        "log_type": "application",
        "timestamp": datetime.now(),
        "source_table": "logs.app_logs"
    }
    with pytest.raises(ValidationError) as exc_info:
        LogPayloadV1(**payload)
    assert "log_id" in str(exc_info.value)


def test_invalid_severity():
    payload = {
        "log_id": "test-log-123",
        "tenant_id": "tenant1",
        "service_name": "my-service",
        "severity": "INVALID",
        "log_type": "application",
        "timestamp": datetime.now(),
        "source_table": "logs.app_logs"
    }
    with pytest.raises(ValidationError) as exc_info:
        LogPayloadV1(**payload)
    assert "severity" in str(exc_info.value)


def test_extra_field_forbidden():
    payload = {
        "log_id": "test-log-123",
        "tenant_id": "tenant1",
        "service_name": "my-service",
        "severity": "INFO",
        "log_type": "application",
        "timestamp": datetime.now(),
        "source_table": "logs.app_logs",
        "extra_field": "not allowed"
    }
    with pytest.raises(ValidationError) as exc_info:
        LogPayloadV1(**payload)
    assert "extra_field" in str(exc_info.value)


def test_normalize_function():
    raw = {
        "log_id": "test-log-123",
        "tenant_id": "tenant1",
        "service_name": "my-service",
        "severity": "WARNING",
        "log_type": "audit",
        "timestamp": "2023-10-01T12:00:00",
        "source_table": "logs.audit_logs",
        "message": "Normalized message"
    }
    log = normalize_log_payload(raw)
    assert isinstance(log.timestamp, datetime)
    assert log.timestamp_year == 2023


def test_long_content_warning():
    payload = {
        "log_id": "test-log-123",
        "tenant_id": "tenant1",
        "service_name": "my-service",
        "severity": "INFO",
        "log_type": "application",
        "timestamp": datetime.now(),
        "source_table": "logs.app_logs",
        "message": "a" * 15000  # Too long
    }
    with pytest.raises(ValidationError) as exc_info:
        LogPayloadV1(**payload)
    assert "too long" in str(exc_info.value)