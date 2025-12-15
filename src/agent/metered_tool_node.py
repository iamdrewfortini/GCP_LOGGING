"""Metered tool node wrapper for tracking tool invocation metrics.

This module wraps LangGraph's ToolNode to track detailed metrics
for each tool invocation, including duration, status, and cost.

Phase 3, Task 3.4: MeteredToolNode wrapper
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence
from datetime import datetime, timezone
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage
from langgraph.prebuilt import ToolNode
from src.agent.state import AgentState
from src.agent.tokenization import estimate_tool_output_tokens

logger = logging.getLogger(__name__)


class ToolInvocationMetrics:
    """Metrics for a single tool invocation."""

    def __init__(
        self,
        invocation_id: str,
        run_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        phase: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.invocation_id = invocation_id
        self.run_id = run_id
        self.session_id = session_id
        self.user_id = user_id
        self.tool_name = tool_name
        self.tool_category = self._categorize_tool(tool_name)
        self.parameters = parameters
        self.phase = phase
        self.started_at = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
        self.duration_ms: Optional[int] = None
        self.status = "running"
        self.error_message: Optional[str] = None
        self.result: Optional[Any] = None
        self.token_count: Optional[int] = None
        self.cost_usd: Optional[float] = None
        self.metadata: Dict[str, Any] = {}

    @staticmethod
    def _categorize_tool(tool_name: str) -> str:
        """Categorize tool by name."""
        tool_lower = tool_name.lower()
        # Check in priority order (most specific first)
        if "runbook" in tool_lower or "repo" in tool_lower:
            return "knowledge"
        elif "search" in tool_lower or "find" in tool_lower:
            return "search"
        elif "query" in tool_lower or "bq" in tool_lower:
            return "query"
        elif "analyze" in tool_lower or "summary" in tool_lower:
            return "analysis"
        elif "health" in tool_lower or "trace" in tool_lower:
            return "monitoring"
        else:
            return "other"

    def complete(self, result: Any, status: str = "success"):
        """Mark invocation as complete."""
        self.completed_at = datetime.now(timezone.utc)
        self.duration_ms = int(
            (self.completed_at - self.started_at).total_seconds() * 1000
        )
        self.status = status
        self.result = result

        # Estimate token count
        if result and status == "success":
            self.token_count = estimate_tool_output_tokens(
                self.tool_name, self.parameters
            )

        # Estimate cost (rough approximation)
        if self.token_count:
            # Assume $0.01 per 1000 tokens for tool outputs
            self.cost_usd = (self.token_count / 1000) * 0.01

    def fail(self, error_message: str):
        """Mark invocation as failed."""
        self.completed_at = datetime.now(timezone.utc)
        self.duration_ms = int(
            (self.completed_at - self.started_at).total_seconds() * 1000
        )
        self.status = "error"
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for BigQuery."""
        return {
            "invocation_id": self.invocation_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tool_name": self.tool_name,
            "tool_category": self.tool_category,
            "parameters": self.parameters,
            "result": self.result if isinstance(self.result, (dict, list)) else str(self.result) if self.result else None,
            "status": self.status,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "token_count": self.token_count,
            "cost_usd": self.cost_usd,
            "phase": self.phase,
            "metadata": self.metadata,
        }


def create_metered_tool_node(
    tools: Sequence[BaseTool],
    publish_metrics: bool = True,
) -> callable:
    """Create a metered tool node function.

    This creates a node function that wraps ToolNode execution
    with metrics tracking.

    Args:
        tools: List of tools
        publish_metrics: Whether to publish metrics to Pub/Sub

    Returns:
        Node function that tracks metrics
    """
    tool_node = ToolNode(tools)
    metrics_buffer: List[ToolInvocationMetrics] = []

    def metered_tool_node_func(state: AgentState) -> Dict[str, Any]:
        """Execute tools with metrics tracking."""
        run_id = state.get("run_id", "unknown")
        phase = state.get("phase", "unknown")
        session_id = state.get("scope", {}).get("session_id")
        user_id = state.get("scope", {}).get("user_id")

        # Get messages with tool calls
        messages = state.get("messages", [])
        if not messages:
            return {}

        last_message = messages[-1]
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return {}

        # Track metrics for each tool call
        tool_call_metrics = []

        for tool_call in last_message.tool_calls:
            invocation_id = str(uuid.uuid4())
            tool_name = tool_call.get("name", "unknown")
            parameters = tool_call.get("args", {})

            # Create metrics tracker
            metrics = ToolInvocationMetrics(
                invocation_id=invocation_id,
                run_id=run_id,
                tool_name=tool_name,
                parameters=parameters,
                phase=phase,
                session_id=session_id,
                user_id=user_id,
            )

            try:
                # Execute tool via ToolNode
                start_time = time.time()
                result = tool_node.invoke(state)
                duration_ms = int((time.time() - start_time) * 1000)

                # Mark as complete
                metrics.complete(result, status="success")
                metrics.duration_ms = duration_ms

                logger.info(
                    f"Tool invocation: {tool_name} completed in {duration_ms}ms "
                    f"(tokens={metrics.token_count}, cost=${metrics.cost_usd:.4f})"
                )

            except Exception as e:
                # Mark as failed
                metrics.fail(str(e))
                logger.error(f"Tool invocation failed: {tool_name} - {e}")
                raise

            finally:
                # Buffer metrics
                tool_call_metrics.append(metrics)
                metrics_buffer.append(metrics)

        # Publish metrics if enabled
        if publish_metrics and tool_call_metrics:
            _publish_metrics_batch(tool_call_metrics)

        # Add metrics to state
        existing_tool_calls = state.get("tool_calls", [])
        new_tool_calls = [m.to_dict() for m in tool_call_metrics]

        return {
            "tool_calls": existing_tool_calls + new_tool_calls,
        }

    # Attach helper methods
    metered_tool_node_func.get_metrics_buffer = lambda: [m.to_dict() for m in metrics_buffer]
    metered_tool_node_func.clear_metrics_buffer = lambda: metrics_buffer.clear()

    return metered_tool_node_func


def _publish_metrics_batch(metrics: List[ToolInvocationMetrics]):
    """Publish metrics batch to Pub/Sub.

    Args:
        metrics: List of metrics to publish
    """
    try:
        from google.cloud import pubsub_v1
        from src.config import config
        import json

        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(
            config.PROJECT_ID, "tool-invocation-metrics"
        )

        for metric in metrics:
            message_data = json.dumps(metric.to_dict()).encode("utf-8")
            future = publisher.publish(topic_path, message_data)
            # Don't wait for result (fire and forget)

        logger.debug(f"Published {len(metrics)} tool metrics to Pub/Sub")

    except Exception as e:
        # Non-fatal error - log and continue
        logger.warning(f"Failed to publish tool metrics: {e}")


class MeteredToolNode:
    """Wrapper class for metered tool node (for compatibility).

    This provides a class-based interface that wraps the functional
    metered tool node.
    """

    def __init__(
        self,
        tools: Sequence[BaseTool],
        publish_metrics: bool = True,
    ):
        """Initialize metered tool node.

        Args:
            tools: List of tools to wrap
            publish_metrics: Whether to publish metrics to Pub/Sub
        """
        self._node_func = create_metered_tool_node(tools, publish_metrics)
        self.publish_metrics = publish_metrics

    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Execute tools with metrics tracking."""
        return self._node_func(state)

    def get_metrics_buffer(self) -> List[Dict[str, Any]]:
        """Get buffered metrics."""
        return self._node_func.get_metrics_buffer()

    def clear_metrics_buffer(self):
        """Clear the metrics buffer."""
        self._node_func.clear_metrics_buffer()


