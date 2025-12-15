"""Unit tests for dual-write service."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from src.services.dual_write_service import (
    ChatEvent,
    ToolInvocation,
    DualWriteService,
    ENABLE_DUAL_WRITE,
)


class TestChatEvent:
    """Test ChatEvent dataclass."""

    def test_create_message_event(self):
        """Test creating a message event."""
        event = ChatEvent.create_message_event(
            session_id="session-123",
            user_id="user-456",
            role="user",
            content="Hello, world!",
        )

        assert event.event_type == "message_sent"
        assert event.session_id == "session-123"
        assert event.user_id == "user-456"
        assert event.role == "user"
        assert event.content == "Hello, world!"
        assert event.event_id is not None
        assert event.timestamp is not None

    def test_create_message_event_with_metadata(self):
        """Test creating a message event with metadata."""
        event = ChatEvent.create_message_event(
            session_id="session-123",
            user_id="user-456",
            role="assistant",
            content="Response",
            metadata={"tools_used": ["search"]},
            token_usage={"prompt_tokens": 100, "completion_tokens": 50},
        )

        assert event.metadata == {"tools_used": ["search"]}
        assert event.token_usage == {"prompt_tokens": 100, "completion_tokens": 50}

    def test_create_tool_start_event(self):
        """Test creating a tool start event."""
        event = ChatEvent.create_tool_start_event(
            session_id="session-123",
            user_id="user-456",
            tool_name="search_logs",
            tool_input={"query": "errors", "limit": 10},
        )

        assert event.event_type == "tool_start"
        assert event.role == "tool"
        assert event.metadata["tool_name"] == "search_logs"
        assert event.metadata["tool_input"]["query"] == "errors"

    def test_create_tool_end_event_success(self):
        """Test creating a successful tool end event."""
        event = ChatEvent.create_tool_end_event(
            session_id="session-123",
            user_id="user-456",
            tool_name="search_logs",
            status="success",
            duration_ms=150,
            output_summary="Found 5 errors",
        )

        assert event.event_type == "tool_end"
        assert event.metadata["status"] == "success"
        assert event.metadata["duration_ms"] == 150

    def test_create_tool_end_event_failure(self):
        """Test creating a failed tool end event."""
        event = ChatEvent.create_tool_end_event(
            session_id="session-123",
            user_id="user-456",
            tool_name="search_logs",
            status="failure",
            error_message="Connection timeout",
        )

        assert event.event_type == "tool_end"
        assert event.metadata["status"] == "failure"
        assert event.metadata["error_message"] == "Connection timeout"

    def test_create_error_event(self):
        """Test creating an error event."""
        event = ChatEvent.create_error_event(
            session_id="session-123",
            user_id="user-456",
            error_message="Internal server error",
            error_type="ServerError",
        )

        assert event.event_type == "error"
        assert event.metadata["error_message"] == "Internal server error"
        assert event.metadata["error_type"] == "ServerError"

    def test_to_dict(self):
        """Test converting event to dictionary."""
        event = ChatEvent.create_message_event(
            session_id="session-123",
            user_id="user-456",
            role="user",
            content="Test",
        )

        result = event.to_dict()

        assert isinstance(result, dict)
        assert result["session_id"] == "session-123"
        assert result["event_type"] == "message_sent"
        # None values should be excluded
        assert "client_info" not in result or result["client_info"] is None

    def test_to_json(self):
        """Test converting event to JSON."""
        event = ChatEvent.create_message_event(
            session_id="session-123",
            user_id="user-456",
            role="user",
            content="Test",
        )

        json_str = event.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["session_id"] == "session-123"


class TestToolInvocation:
    """Test ToolInvocation dataclass."""

    def test_start(self):
        """Test creating a new tool invocation."""
        invocation = ToolInvocation.start(
            session_id="session-123",
            user_id="user-456",
            tool_name="search_logs",
            input_args={"query": "errors"},
        )

        assert invocation.status == "running"
        assert invocation.tool_name == "search_logs"
        assert invocation.started_at is not None
        assert invocation.ended_at is None

    def test_complete(self):
        """Test completing an invocation successfully."""
        invocation = ToolInvocation.start(
            session_id="session-123",
            user_id="user-456",
            tool_name="search_logs",
        )

        invocation.complete(
            output_summary="Found 5 errors",
            bytes_billed=1000,
            tokens_used=500,
        )

        assert invocation.status == "success"
        assert invocation.ended_at is not None
        assert invocation.output_summary == "Found 5 errors"
        assert invocation.bytes_billed == 1000
        assert invocation.duration_ms is not None

    def test_fail(self):
        """Test marking an invocation as failed."""
        invocation = ToolInvocation.start(
            session_id="session-123",
            user_id="user-456",
            tool_name="search_logs",
        )

        invocation.fail("Connection error")

        assert invocation.status == "failure"
        assert invocation.ended_at is not None
        assert invocation.error_message == "Connection error"

    def test_duration_calculation(self):
        """Test duration is calculated correctly."""
        invocation = ToolInvocation.start(
            session_id="session-123",
            user_id="user-456",
            tool_name="test",
        )

        # Manually set timestamps for testing
        invocation.started_at = "2025-01-01T10:00:00+00:00"
        invocation.ended_at = "2025-01-01T10:00:01.500+00:00"
        invocation._calculate_duration()

        assert invocation.duration_ms == 1500


class TestDualWriteService:
    """Test DualWriteService class."""

    def test_singleton(self):
        """Test DualWriteService is a singleton."""
        service1 = DualWriteService()
        service2 = DualWriteService()
        assert service1 is service2

    def test_enabled_property(self):
        """Test enabled property."""
        service = DualWriteService()
        # Should return boolean based on env var
        assert isinstance(service.enabled, bool)

    @patch.dict("os.environ", {"ENABLE_DUAL_WRITE": "false"})
    def test_write_event_disabled(self):
        """Test write_event when dual-write is disabled."""
        # Need to reimport to pick up env var change
        from src.services import dual_write_service

        # Reset singleton for test
        dual_write_service.DualWriteService._instance = None
        service = dual_write_service.DualWriteService()

        event = ChatEvent.create_message_event(
            session_id="session-123",
            user_id="user-456",
            role="user",
            content="Test",
        )

        # Should return True without writing anything
        result = service.write_event(event)
        assert result is True

    def test_write_event_with_firebase(self):
        """Test write_event writes to Firestore."""
        service = DualWriteService()

        mock_firebase = Mock()
        mock_firebase.enabled = True
        mock_firebase.add_message = Mock()

        event = ChatEvent.create_message_event(
            session_id="session-123",
            user_id="user-456",
            role="user",
            content="Test message",
        )

        with patch.object(service, "_publish_to_pubsub"):
            result = service.write_event(event, firebase_service=mock_firebase)

        assert result is True
        mock_firebase.add_message.assert_called_once()

    def test_write_event_firestore_error_doesnt_block(self):
        """Test that Firestore error doesn't block cold path."""
        service = DualWriteService()

        mock_firebase = Mock()
        mock_firebase.enabled = True
        mock_firebase.add_message = Mock(side_effect=Exception("Firestore error"))

        event = ChatEvent.create_message_event(
            session_id="session-123",
            user_id="user-456",
            role="user",
            content="Test",
        )

        with patch.object(service, "_publish_to_pubsub") as mock_publish:
            result = service.write_event(event, firebase_service=mock_firebase)

        # Hot path failed but cold path should still be attempted
        assert result is False
        mock_publish.assert_called_once()

    def test_write_tool_invocation(self):
        """Test write_tool_invocation publishes to Pub/Sub."""
        service = DualWriteService()

        invocation = ToolInvocation.start(
            session_id="session-123",
            user_id="user-456",
            tool_name="test_tool",
        )
        invocation.complete(output_summary="Done")

        with patch.object(service, "_publish_tool_invocation") as mock_publish:
            result = service.write_tool_invocation(invocation)

        assert result is True
        mock_publish.assert_called_once_with(invocation)


class TestChatEventIntegration:
    """Integration tests for chat events."""

    def test_event_lifecycle(self):
        """Test complete event lifecycle."""
        # User sends message
        user_event = ChatEvent.create_message_event(
            session_id="session-123",
            user_id="user-456",
            role="user",
            content="Show me recent errors",
            token_usage={"prompt_tokens": 10, "total_tokens": 10},
        )
        assert user_event.event_type == "message_sent"

        # Tool starts
        tool_start = ChatEvent.create_tool_start_event(
            session_id="session-123",
            user_id="user-456",
            tool_name="search_logs",
            tool_input={"severity": "ERROR", "limit": 10},
        )
        assert tool_start.event_type == "tool_start"

        # Tool ends
        tool_end = ChatEvent.create_tool_end_event(
            session_id="session-123",
            user_id="user-456",
            tool_name="search_logs",
            status="success",
            duration_ms=250,
        )
        assert tool_end.event_type == "tool_end"

        # Assistant responds
        assistant_event = ChatEvent.create_message_event(
            session_id="session-123",
            user_id="user-456",
            role="assistant",
            content="Here are the recent errors...",
            metadata={"tools_used": ["search_logs"]},
            token_usage={"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
        )
        assert assistant_event.event_type == "message_sent"
        assert assistant_event.role == "assistant"
