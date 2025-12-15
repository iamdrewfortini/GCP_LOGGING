"""Integration tests for chat streaming with token_count events."""

import json
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime


class TestTokenCountEventCreation:
    """Test token_count event creation."""

    def test_create_token_count_event_ingress(self):
        """Test creating token_count event for ingress phase."""
        from src.api.main import create_token_count_event

        event = create_token_count_event(
            phase="ingress",
            prompt_tokens=100,
            completion_tokens=0,
            total_tokens=100,
            remaining=99_900,
            budget_max=100_000,
        )

        assert event["type"] == "token_count"
        assert event["data"]["phase"] == "ingress"
        assert event["data"]["prompt"] == 100
        assert event["data"]["completion"] == 0
        assert event["data"]["total"] == 100
        assert event["data"]["remaining"] == 99_900
        assert event["data"]["budget_max"] == 100_000
        assert "ts" in event["data"]
        # Verify timestamp format
        assert event["data"]["ts"].endswith("Z")

    def test_create_token_count_event_model_stream(self):
        """Test creating token_count event for model_stream phase."""
        from src.api.main import create_token_count_event

        event = create_token_count_event(
            phase="model_stream",
            prompt_tokens=500,
            completion_tokens=150,
            total_tokens=650,
            remaining=99_350,
            budget_max=100_000,
        )

        assert event["type"] == "token_count"
        assert event["data"]["phase"] == "model_stream"
        assert event["data"]["prompt"] == 500
        assert event["data"]["completion"] == 150
        assert event["data"]["total"] == 650

    def test_create_token_count_event_tool(self):
        """Test creating token_count event for tool phase."""
        from src.api.main import create_token_count_event

        event = create_token_count_event(
            phase="tool",
            prompt_tokens=1000,
            completion_tokens=200,
            total_tokens=1200,
            remaining=98_800,
            budget_max=100_000,
        )

        assert event["type"] == "token_count"
        assert event["data"]["phase"] == "tool"

    def test_create_token_count_event_finalize(self):
        """Test creating token_count event for finalize phase."""
        from src.api.main import create_token_count_event

        event = create_token_count_event(
            phase="finalize",
            prompt_tokens=2000,
            completion_tokens=500,
            total_tokens=2500,
            remaining=97_500,
            budget_max=100_000,
        )

        assert event["type"] == "token_count"
        assert event["data"]["phase"] == "finalize"
        assert event["data"]["total"] == 2500


class TestTokenCountEventSchema:
    """Test token_count event schema compliance."""

    def test_event_has_required_fields(self):
        """Test that token_count event has all required fields."""
        from src.api.main import create_token_count_event

        event = create_token_count_event(
            phase="ingress",
            prompt_tokens=100,
            completion_tokens=0,
            total_tokens=100,
            remaining=99_900,
            budget_max=100_000,
        )

        # Required top-level fields
        assert "type" in event
        assert "data" in event

        # Required data fields
        data = event["data"]
        required_fields = ["prompt", "completion", "total", "remaining", "budget_max", "ts", "phase"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_event_types_are_correct(self):
        """Test that token_count event field types are correct."""
        from src.api.main import create_token_count_event

        event = create_token_count_event(
            phase="model_stream",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            remaining=99_850,
            budget_max=100_000,
        )

        data = event["data"]
        assert isinstance(data["prompt"], int)
        assert isinstance(data["completion"], int)
        assert isinstance(data["total"], int)
        assert isinstance(data["remaining"], int)
        assert isinstance(data["budget_max"], int)
        assert isinstance(data["ts"], str)
        assert isinstance(data["phase"], str)

    def test_event_is_json_serializable(self):
        """Test that token_count event can be JSON serialized."""
        from src.api.main import create_token_count_event

        event = create_token_count_event(
            phase="finalize",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            remaining=98_500,
            budget_max=100_000,
        )

        # Should not raise
        json_str = json.dumps(event)
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["type"] == "token_count"


class TestTokenEventPhases:
    """Test token_count events for different phases."""

    def test_valid_phases(self):
        """Test that all valid phases produce correct events."""
        from src.api.main import create_token_count_event

        valid_phases = ["ingress", "retrieval", "model_stream", "tool", "finalize"]

        for phase in valid_phases:
            event = create_token_count_event(
                phase=phase,
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                remaining=99_850,
                budget_max=100_000,
            )
            assert event["data"]["phase"] == phase


class TestSSEEventFormat:
    """Test SSE event formatting."""

    def test_sse_event_format(self):
        """Test that token_count events are formatted correctly for SSE."""
        from src.api.main import create_token_count_event

        event = create_token_count_event(
            phase="ingress",
            prompt_tokens=50,
            completion_tokens=0,
            total_tokens=50,
            remaining=99_950,
            budget_max=100_000,
        )

        # Format as SSE
        sse_line = f"data: {json.dumps(event)}\n\n"

        # Should start with "data: "
        assert sse_line.startswith("data: ")
        # Should end with double newline
        assert sse_line.endswith("\n\n")

        # Parse the JSON from the SSE line
        json_str = sse_line[6:-2]  # Remove "data: " prefix and "\n\n" suffix
        parsed = json.loads(json_str)
        assert parsed["type"] == "token_count"


class TestTokenTrackingIntegration:
    """Integration tests for token tracking in chat endpoint."""

    @pytest.fixture
    def mock_services(self):
        """Mock external services."""
        with patch("src.api.main.firebase_service") as mock_firebase, \
             patch("src.api.main.redis_service") as mock_redis, \
             patch("src.api.main.graph") as mock_graph:
            mock_firebase.enabled = False
            mock_redis.enqueue = Mock()
            yield {
                "firebase": mock_firebase,
                "redis": mock_redis,
                "graph": mock_graph,
            }

    def test_token_manager_reset_per_request(self):
        """Test that token manager is reset for each request."""
        from src.agent.nodes import get_token_manager, reset_token_manager

        # First request
        manager1 = get_token_manager()
        manager1.reserve_tokens(100)
        assert manager1.tokens_used == 100

        # Simulate request end
        reset_token_manager()

        # Second request
        manager2 = get_token_manager()
        assert manager2.tokens_used == 0

    def test_token_budget_defaults(self):
        """Test default token budget values."""
        from src.api.main import create_token_count_event

        event = create_token_count_event(phase="ingress")

        assert event["data"]["prompt"] == 0
        assert event["data"]["completion"] == 0
        assert event["data"]["total"] == 0
        assert event["data"]["remaining"] == 100_000
        assert event["data"]["budget_max"] == 100_000
