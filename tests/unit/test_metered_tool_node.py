"""Unit tests for MeteredToolNode.

Phase 3, Task 3.4: MeteredToolNode wrapper
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from src.agent.metered_tool_node import (
    ToolInvocationMetrics,
    MeteredToolNode,
)
from src.agent.state import create_initial_state


# Sample tool for testing
@tool
def sample_tool(query: str) -> str:
    """Sample tool for testing."""
    return f"Result for: {query}"


@tool
def failing_tool(query: str) -> str:
    """Tool that always fails."""
    raise ValueError("Tool error")


class TestToolInvocationMetrics:
    """Tests for ToolInvocationMetrics class."""

    def test_metrics_initialization(self):
        """Test metrics initialization."""
        metrics = ToolInvocationMetrics(
            invocation_id="inv-123",
            run_id="run-456",
            tool_name="search_logs_tool",
            parameters={"query": "ERROR"},
            phase="diagnose",
            session_id="sess-789",
            user_id="user-001",
        )

        assert metrics.invocation_id == "inv-123"
        assert metrics.run_id == "run-456"
        assert metrics.tool_name == "search_logs_tool"
        assert metrics.tool_category == "search"
        assert metrics.phase == "diagnose"
        assert metrics.status == "running"
        assert metrics.started_at is not None

    def test_tool_categorization(self):
        """Test tool categorization logic."""
        test_cases = [
            ("search_logs_tool", "search"),
            ("find_related_logs", "search"),
            ("bq_query_tool", "query"),
            ("analyze_logs", "analysis"),
            ("service_health_tool", "monitoring"),
            ("runbook_search_tool", "knowledge"),
            ("unknown_tool", "other"),
        ]

        for tool_name, expected_category in test_cases:
            metrics = ToolInvocationMetrics(
                invocation_id="test",
                run_id="test",
                tool_name=tool_name,
                parameters={},
                phase="test",
            )
            assert metrics.tool_category == expected_category

    def test_metrics_complete(self):
        """Test marking metrics as complete."""
        metrics = ToolInvocationMetrics(
            invocation_id="inv-123",
            run_id="run-456",
            tool_name="search_logs_tool",
            parameters={"query": "ERROR"},
            phase="diagnose",
        )

        result = {"logs": ["log1", "log2"]}
        metrics.complete(result, status="success")

        assert metrics.status == "success"
        assert metrics.completed_at is not None
        assert metrics.duration_ms is not None
        assert metrics.duration_ms >= 0
        assert metrics.result == result
        assert metrics.token_count is not None

    def test_metrics_fail(self):
        """Test marking metrics as failed."""
        metrics = ToolInvocationMetrics(
            invocation_id="inv-123",
            run_id="run-456",
            tool_name="search_logs_tool",
            parameters={"query": "ERROR"},
            phase="diagnose",
        )

        error_msg = "Connection timeout"
        metrics.fail(error_msg)

        assert metrics.status == "error"
        assert metrics.error_message == error_msg
        assert metrics.completed_at is not None
        assert metrics.duration_ms is not None

    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = ToolInvocationMetrics(
            invocation_id="inv-123",
            run_id="run-456",
            tool_name="search_logs_tool",
            parameters={"query": "ERROR"},
            phase="diagnose",
            session_id="sess-789",
            user_id="user-001",
        )

        metrics.complete({"count": 10}, status="success")

        metrics_dict = metrics.to_dict()

        assert metrics_dict["invocation_id"] == "inv-123"
        assert metrics_dict["run_id"] == "run-456"
        assert metrics_dict["tool_name"] == "search_logs_tool"
        assert metrics_dict["status"] == "success"
        assert metrics_dict["duration_ms"] is not None
        assert "started_at" in metrics_dict
        assert "completed_at" in metrics_dict


class TestMeteredToolNode:
    """Tests for MeteredToolNode class."""

    def test_initialization(self):
        """Test MeteredToolNode initialization."""
        tools = [sample_tool]
        node = MeteredToolNode(tools, publish_metrics=False)

        assert node.publish_metrics is False
        assert len(node.get_metrics_buffer()) == 0

    def test_tool_execution_with_metrics(self):
        """Test tool execution tracks metrics."""
        tools = [sample_tool]
        node = MeteredToolNode(tools, publish_metrics=False)

        # Create state with tool call
        state = create_initial_state(
            run_id="test-run",
            user_query="test",
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "sample_tool",
                            "args": {"query": "test query"},
                            "id": "call-123",
                        }
                    ],
                )
            ],
        )

        # Execute tool
        result = node(state)

        # Verify metrics were tracked
        assert "tool_calls" in result
        assert len(result["tool_calls"]) == 1

        tool_call = result["tool_calls"][0]
        assert tool_call["tool_name"] == "sample_tool"
        assert tool_call["status"] == "success"
        assert tool_call["duration_ms"] is not None
        assert tool_call["token_count"] is not None

    def test_tool_execution_error_handling(self):
        """Test tool execution handles errors."""
        tools = [failing_tool]
        node = MeteredToolNode(tools, publish_metrics=False)

        state = create_initial_state(
            run_id="test-run",
            user_query="test",
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "failing_tool",
                            "args": {"query": "test"},
                            "id": "call-123",
                        }
                    ],
                )
            ],
        )

        # Execute tool (should raise)
        with pytest.raises(ValueError, match="Tool error"):
            node(state)

        # Verify error was tracked
        metrics_buffer = node.get_metrics_buffer()
        assert len(metrics_buffer) == 1
        assert metrics_buffer[0]["status"] == "error"
        assert "Tool error" in metrics_buffer[0]["error_message"]

    def test_no_tool_calls(self):
        """Test handling state with no tool calls."""
        tools = [sample_tool]
        node = MeteredToolNode(tools, publish_metrics=False)

        state = create_initial_state(
            run_id="test-run",
            user_query="test",
            messages=[AIMessage(content="No tools needed")],
        )

        result = node(state)

        # Should return empty dict
        assert result == {}
        assert len(node.get_metrics_buffer()) == 0

    def test_metrics_buffer_operations(self):
        """Test metrics buffer operations."""
        tools = [sample_tool]
        node = MeteredToolNode(tools, publish_metrics=False)

        # Initially empty
        assert len(node.get_metrics_buffer()) == 0

        # Execute tool
        state = create_initial_state(
            run_id="test-run",
            user_query="test",
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "sample_tool",
                            "args": {"query": "test"},
                            "id": "call-123",
                        }
                    ],
                )
            ],
        )

        node(state)

        # Buffer should have metrics
        assert len(node.get_metrics_buffer()) == 1

        # Clear buffer
        node.clear_metrics_buffer()
        assert len(node.get_metrics_buffer()) == 0

    @patch("google.cloud.pubsub_v1.PublisherClient")
    def test_metrics_publishing(self, mock_publisher_class):
        """Test metrics publishing to Pub/Sub."""
        mock_publisher = Mock()
        mock_publisher_class.return_value = mock_publisher
        mock_publisher.topic_path.return_value = "projects/test/topics/metrics"
        mock_future = Mock()
        mock_publisher.publish.return_value = mock_future

        tools = [sample_tool]
        node = MeteredToolNode(tools, publish_metrics=True)

        state = create_initial_state(
            run_id="test-run",
            user_query="test",
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "sample_tool",
                            "args": {"query": "test"},
                            "id": "call-123",
                        }
                    ],
                )
            ],
        )

        node(state)

        # Verify publish was called
        mock_publisher.publish.assert_called_once()

    def test_multiple_tool_calls(self):
        """Test handling multiple tool calls."""
        tools = [sample_tool]
        node = MeteredToolNode(tools, publish_metrics=False)

        state = create_initial_state(
            run_id="test-run",
            user_query="test",
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "sample_tool",
                            "args": {"query": "query1"},
                            "id": "call-1",
                        },
                        {
                            "name": "sample_tool",
                            "args": {"query": "query2"},
                            "id": "call-2",
                        },
                    ],
                )
            ],
        )

        result = node(state)

        # Should track both calls
        assert len(result["tool_calls"]) == 2
        assert len(node.get_metrics_buffer()) == 2
