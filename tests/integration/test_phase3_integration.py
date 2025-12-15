"""
Integration tests for Phase 3 components.

Tests the complete flow of:
- Structured outputs
- Checkpointing
- Tool metrics tracking
- Token budget management
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from src.agent.state import create_initial_state
from src.agent.schemas import Response, Plan, Finding, Recommendation, Citation
from src.agent.checkpoint import save_checkpoint, load_checkpoint, restore_state_from_checkpoint
from src.agent.metered_tool_node import create_metered_tool_node, ToolInvocationMetrics
from src.agent.tokenization import TokenBudgetManager


class TestStructuredOutputIntegration:
    """Test structured outputs in realistic scenarios."""

    def test_response_schema_with_complete_data(self):
        """Test Response schema with all fields populated."""
        response = Response(
            summary="Database connection pool exhausted",
            findings=[
                Finding(
                    title="Connection Pool Exhausted",
                    description="All 50 connections in use",
                    severity="critical",
                    evidence_ids=["ev-1", "ev-2"],
                    recommendation="Increase pool size to 100"
                ),
                Finding(
                    title="High Query Latency",
                    description="P95 latency at 2.5s",
                    severity="high",
                    evidence_ids=["ev-3"],
                    recommendation="Add database indexes"
                )
            ],
            recommendations=[
                Recommendation(
                    title="Scale Database Connection Pool",
                    description="Increase max_connections from 50 to 100",
                    priority="immediate",
                    effort="low",
                    impact="high",
                    steps=[
                        "Update database config",
                        "Restart database",
                        "Monitor connection usage"
                    ]
                )
            ],
            citations=[
                Citation(
                    source="log-12345",
                    content="ERROR: Connection pool exhausted",
                    relevance_score=0.95,
                    metadata={"severity": "ERROR", "service": "api-gateway"}
                )
            ],
            confidence=0.9,
            follow_up_questions=[
                "Should we also scale the database instance?",
                "Are there any slow queries we should optimize?"
            ]
        )

        # Verify structure
        assert response.summary == "Database connection pool exhausted"
        assert len(response.findings) == 2
        assert len(response.recommendations) == 1
        assert len(response.citations) == 1
        assert response.confidence == 0.9

        # Verify can serialize
        response_dict = response.model_dump()
        assert response_dict["findings"][0]["severity"] == "critical"

    def test_plan_schema_with_tool_invocations(self):
        """Test Plan schema with tool invocations."""
        from src.agent.schemas import Hypothesis, ToolInvocation

        plan = Plan(
            phase="diagnose",
            hypotheses=[
                Hypothesis(
                    id="hyp-1",
                    description="Database connection timeout",
                    confidence=0.8,
                    evidence_ids=["ev-1"],
                    status="active"
                )
            ],
            tool_invocations=[
                ToolInvocation(
                    tool_name="search_logs_tool",
                    parameters={"query": "timeout", "hours": 24},
                    rationale="Find timeout errors in logs",
                    expected_outcome="List of timeout errors",
                    priority=1
                ),
                ToolInvocation(
                    tool_name="service_health_tool",
                    parameters={"service": "database"},
                    rationale="Check database health metrics",
                    expected_outcome="Database health status",
                    priority=2
                )
            ],
            reasoning="Need to investigate database connectivity issues",
            next_phase="verify"
        )

        assert plan.phase == "diagnose"
        assert len(plan.hypotheses) == 1
        assert len(plan.tool_invocations) == 2
        assert plan.tool_invocations[0].priority == 1


class TestCheckpointIntegration:
    """Test checkpoint system in realistic scenarios."""

    @patch("src.agent.checkpoint.db")
    def test_checkpoint_save_and_restore_flow(self, mock_db):
        """Test complete checkpoint save and restore flow."""
        # Setup mock
        mock_doc_ref = Mock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Create initial state
        state = create_initial_state(
            run_id="test-run-123",
            user_query="Check logs for errors",
            messages=[
                HumanMessage(content="Check logs for errors"),
                AIMessage(content="I'll analyze the logs"),
            ],
            budget_max=100000
        )

        # Add some execution data
        state["evidence"] = [
            {"type": "log", "content": "Found 150 errors"},
            {"type": "metric", "value": 0.95}
        ]
        state["tool_calls"] = [
            {
                "tool_name": "search_logs_tool",
                "status": "completed",
                "duration_ms": 1500
            }
        ]
        state["token_budget"]["total_tokens"] = 5000
        state["token_budget"]["budget_remaining"] = 95000

        # Save checkpoint
        metadata = save_checkpoint(state)

        # Verify checkpoint metadata
        assert metadata.run_id == "test-run-123"
        assert metadata.phase == "diagnose"
        assert metadata.message_count == 2
        assert metadata.tool_call_count == 1
        assert metadata.token_usage["total_tokens"] == 5000

        # Verify Firestore was called
        mock_db.collection.assert_called_with("checkpoints")
        mock_doc_ref.set.assert_called_once()

        # Get the saved document
        saved_doc = mock_doc_ref.set.call_args[0][0]
        assert saved_doc["run_id"] == "test-run-123"
        assert saved_doc["state"]["user_query"] == "Check logs for errors"
        assert len(saved_doc["state"]["evidence"]) == 2

    @patch("src.agent.checkpoint.db")
    def test_checkpoint_list_and_load(self, mock_db):
        """Test listing and loading checkpoints."""
        # Setup mock for list
        mock_doc1 = Mock()
        mock_doc1.to_dict.return_value = {
            "checkpoint_id": "ckpt-1",
            "run_id": "run-123",
            "phase": "diagnose"
        }
        mock_doc2 = Mock()
        mock_doc2.to_dict.return_value = {
            "checkpoint_id": "ckpt-2",
            "run_id": "run-123",
            "phase": "verify"
        }

        mock_query = Mock()
        mock_query.stream.return_value = [mock_doc1, mock_doc2]
        mock_collection = Mock()
        mock_collection.where.return_value.order_by.return_value.limit.return_value = mock_query
        mock_db.collection.return_value = mock_collection

        # List checkpoints
        from src.agent.checkpoint import list_checkpoints_for_run
        checkpoints = list_checkpoints_for_run("run-123")

        assert len(checkpoints) == 2
        assert checkpoints[0]["checkpoint_id"] == "ckpt-1"
        assert checkpoints[1]["checkpoint_id"] == "ckpt-2"


class TestToolMetricsIntegration:
    """Test tool metrics tracking in realistic scenarios."""

    def test_tool_invocation_metrics_lifecycle(self):
        """Test complete tool invocation metrics lifecycle."""
        # Create metrics
        metrics = ToolInvocationMetrics(
            invocation_id="inv-123",
            run_id="run-456",
            tool_name="search_logs_tool",
            parameters={"query": "ERROR", "hours": 24},
            phase="diagnose",
            session_id="sess-789",
            user_id="user-001"
        )

        # Verify initial state
        assert metrics.status == "running"
        assert metrics.started_at is not None
        assert metrics.completed_at is None

        # Complete successfully
        result = {"count": 150, "logs": ["log1", "log2"]}
        metrics.complete(result, status="success")

        # Verify completion
        assert metrics.status == "success"
        assert metrics.completed_at is not None
        assert metrics.duration_ms is not None
        assert metrics.duration_ms >= 0
        assert metrics.result == result
        assert metrics.token_count is not None
        assert metrics.cost_usd is not None

        # Convert to dict for BigQuery
        metrics_dict = metrics.to_dict()
        assert metrics_dict["invocation_id"] == "inv-123"
        assert metrics_dict["status"] == "success"
        assert metrics_dict["duration_ms"] >= 0

    def test_tool_metrics_error_handling(self):
        """Test tool metrics with error."""
        metrics = ToolInvocationMetrics(
            invocation_id="inv-456",
            run_id="run-789",
            tool_name="bq_query_tool",
            parameters={"query": "SELECT * FROM logs"},
            phase="verify"
        )

        # Fail with error
        error_msg = "Query timeout after 30s"
        metrics.fail(error_msg)

        # Verify error state
        assert metrics.status == "error"
        assert metrics.error_message == error_msg
        assert metrics.completed_at is not None
        assert metrics.duration_ms is not None


class TestTokenBudgetIntegration:
    """Test token budget management in realistic scenarios."""

    def test_token_budget_tracking_across_nodes(self):
        """Test token tracking across multiple nodes."""
        manager = TokenBudgetManager(model="gpt-4", max_tokens=10000)

        # Simulate diagnose node
        diagnose_messages = [
            HumanMessage(content="Check logs for errors in the last 24 hours"),
            AIMessage(content="I'll search the logs for error messages")
        ]
        diagnose_tokens = manager.count_messages(diagnose_messages)
        manager.reserve_tokens(diagnose_tokens)

        status_after_diagnose = manager.get_budget_status()
        assert status_after_diagnose["tokens_used"] > 0
        assert status_after_diagnose["tokens_remaining"] < 10000

        # Simulate tool execution
        tool_tokens = 500
        manager.reserve_tokens(tool_tokens)

        # Simulate verify node
        verify_messages = [
            AIMessage(content="Found 150 ERROR logs. Let me verify the patterns.")
        ]
        verify_tokens = manager.count_messages(verify_messages)
        manager.reserve_tokens(verify_tokens)

        # Check final status
        final_status = manager.get_budget_status()
        assert final_status["tokens_used"] > diagnose_tokens + tool_tokens
        assert final_status["tokens_remaining"] > 0

    def test_token_budget_warning_threshold(self):
        """Test token budget warning at 80% threshold."""
        manager = TokenBudgetManager(model="gpt-4", max_tokens=1000)

        # Use 850 tokens (85% - above 80% threshold)
        manager.reserve_tokens(850)

        # Should trigger summarization warning
        assert manager.should_summarize() is True

        status = manager.get_budget_status()
        assert status["tokens_used"] == 850
        assert status["tokens_remaining"] == 150


class TestEndToEndFlow:
    """Test complete end-to-end flow with all Phase 3 components."""

    @patch("src.agent.checkpoint.db")
    def test_complete_agent_run_with_phase3_features(self, mock_db):
        """Test complete agent run using all Phase 3 features."""
        # Setup mocks
        mock_doc_ref = Mock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # 1. Create initial state with token budget
        state = create_initial_state(
            run_id="test-run-complete",
            user_query="Investigate high error rate in api-gateway",
            messages=[
                HumanMessage(content="Investigate high error rate in api-gateway")
            ],
            budget_max=50000
        )

        # 2. Initialize token manager
        token_manager = TokenBudgetManager(model="gpt-4", max_tokens=50000)

        # 3. Simulate diagnose phase
        diagnose_response = AIMessage(
            content="I'll search for errors in the api-gateway service"
        )
        state["messages"].append(diagnose_response)
        
        # Track tokens
        tokens_used = token_manager.count_messages([diagnose_response])
        token_manager.reserve_tokens(tokens_used)
        
        # Update state
        state["token_budget"]["total_tokens"] = tokens_used
        state["token_budget"]["budget_remaining"] = 50000 - tokens_used
        state["phase"] = "diagnose"

        # 4. Simulate tool execution with metrics
        tool_metrics = ToolInvocationMetrics(
            invocation_id="inv-1",
            run_id="test-run-complete",
            tool_name="search_logs_tool",
            parameters={"service": "api-gateway", "severity": "ERROR"},
            phase="diagnose"
        )
        
        tool_result = {"count": 250, "error_rate": 0.15}
        tool_metrics.complete(tool_result, status="success")
        
        state["tool_calls"].append(tool_metrics.to_dict())

        # 5. Save checkpoint after diagnose
        checkpoint_metadata = save_checkpoint(state, checkpoint_id="ckpt-diagnose")
        
        assert checkpoint_metadata.phase == "diagnose"
        assert checkpoint_metadata.tool_call_count == 1

        # 6. Simulate verify phase
        state["phase"] = "verify"
        verify_response = AIMessage(
            content="The error rate is 15%, which is above the 5% threshold"
        )
        state["messages"].append(verify_response)

        # Track more tokens
        verify_tokens = token_manager.count_messages([verify_response])
        token_manager.reserve_tokens(verify_tokens)
        state["token_budget"]["total_tokens"] += verify_tokens
        state["token_budget"]["budget_remaining"] -= verify_tokens

        # 7. Save checkpoint after verify
        checkpoint_metadata_2 = save_checkpoint(state, checkpoint_id="ckpt-verify")
        
        assert checkpoint_metadata_2.phase == "verify"
        assert checkpoint_metadata_2.message_count == 3

        # 8. Create structured response
        final_response = Response(
            summary="High error rate detected in api-gateway service",
            findings=[
                Finding(
                    title="Error Rate Above Threshold",
                    description="15% error rate vs 5% threshold",
                    severity="high",
                    recommendation="Investigate root cause"
                )
            ],
            recommendations=[
                Recommendation(
                    title="Scale API Gateway",
                    description="Increase replicas to handle load",
                    priority="high",
                    effort="low",
                    impact="high",
                    steps=["Update deployment", "Monitor metrics"]
                )
            ],
            citations=[
                Citation(
                    source="log-analysis",
                    content="250 ERROR logs found",
                    relevance_score=0.9
                )
            ],
            confidence=0.85
        )

        # Verify complete flow
        assert len(state["messages"]) == 3
        assert len(state["tool_calls"]) == 1
        assert state["token_budget"]["total_tokens"] > 0
        assert final_response.confidence == 0.85
        assert len(final_response.findings) == 1
        assert len(final_response.recommendations) == 1

        # Verify checkpoints were saved
        assert mock_doc_ref.set.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
