"""Unit tests for structured output schemas.

Phase 3, Task 3.1: Structured Outputs
"""

import pytest
from datetime import datetime
from pydantic import ValidationError
from src.agent.schemas import (
    IngressValidation,
    Hypothesis,
    Evidence,
    ToolInvocation,
    Plan,
    Finding,
    Recommendation,
    Citation,
    Response,
    CheckpointMetadata,
)


class TestIngressValidation:
    """Tests for IngressValidation schema."""

    def test_valid_ingress(self):
        """Test valid ingress validation."""
        ingress = IngressValidation(
            is_valid=True,
            intent="debug",
            entities={"services": ["api-gateway"], "error_types": ["500"]},
            timeframe="24h",
            severity_filter=["ERROR"],
            suggested_tools=["analyze_logs", "search_logs_tool"],
        )
        assert ingress.is_valid is True
        assert ingress.intent == "debug"
        assert "services" in ingress.entities
        assert ingress.timeframe == "24h"

    def test_clarification_needed(self):
        """Test ingress with clarification needed."""
        ingress = IngressValidation(
            is_valid=True,
            intent="other",
            clarification_needed=True,
            clarification_question="Which service would you like to investigate?",
        )
        assert ingress.clarification_needed is True
        assert ingress.clarification_question is not None

    def test_minimal_ingress(self):
        """Test minimal valid ingress."""
        ingress = IngressValidation(
            is_valid=False,
            intent="other",
        )
        assert ingress.is_valid is False
        assert ingress.entities == {}
        assert ingress.suggested_tools == []


class TestHypothesis:
    """Tests for Hypothesis schema."""

    def test_valid_hypothesis(self):
        """Test valid hypothesis."""
        hyp = Hypothesis(
            id="hyp-1",
            description="API gateway experiencing high latency",
            confidence=0.8,
            evidence_ids=["ev-1", "ev-2"],
            status="active",
        )
        assert hyp.id == "hyp-1"
        assert hyp.confidence == 0.8
        assert len(hyp.evidence_ids) == 2

    def test_confidence_bounds(self):
        """Test confidence score validation."""
        # Valid confidence
        hyp = Hypothesis(
            id="hyp-1",
            description="Test",
            confidence=0.5,
        )
        assert hyp.confidence == 0.5

        # Invalid confidence (too high)
        with pytest.raises(ValidationError):
            Hypothesis(
                id="hyp-1",
                description="Test",
                confidence=1.5,
            )

        # Invalid confidence (negative)
        with pytest.raises(ValidationError):
            Hypothesis(
                id="hyp-1",
                description="Test",
                confidence=-0.1,
            )


class TestEvidence:
    """Tests for Evidence schema."""

    def test_valid_evidence(self):
        """Test valid evidence."""
        ev = Evidence(
            id="ev-1",
            source="search_logs_tool",
            content="Found 150 ERROR logs in last hour",
            severity="ERROR",
            timestamp="2024-01-15T10:30:00Z",
            metadata={"count": 150, "service": "api-gateway"},
            relevance_score=0.9,
        )
        assert ev.id == "ev-1"
        assert ev.source == "search_logs_tool"
        assert ev.relevance_score == 0.9

    def test_minimal_evidence(self):
        """Test minimal evidence."""
        ev = Evidence(
            id="ev-1",
            source="manual",
            content="User reported issue",
        )
        assert ev.severity is None
        assert ev.metadata == {}
        assert ev.relevance_score == 1.0


class TestToolInvocation:
    """Tests for ToolInvocation schema."""

    def test_valid_tool_invocation(self):
        """Test valid tool invocation."""
        tool = ToolInvocation(
            tool_name="analyze_logs",
            parameters={"intent": "errors", "timeframe": "1h"},
            rationale="Check for recent errors",
            expected_outcome="List of error logs",
            priority=1,
        )
        assert tool.tool_name == "analyze_logs"
        assert tool.priority == 1

    def test_priority_bounds(self):
        """Test priority validation."""
        # Valid priority
        tool = ToolInvocation(
            tool_name="test",
            rationale="test",
            expected_outcome="test",
            priority=5,
        )
        assert tool.priority == 5

        # Invalid priority (too high)
        with pytest.raises(ValidationError):
            ToolInvocation(
                tool_name="test",
                rationale="test",
                expected_outcome="test",
                priority=11,
            )


class TestPlan:
    """Tests for Plan schema."""

    def test_valid_plan(self):
        """Test valid investigation plan."""
        plan = Plan(
            phase="diagnose",
            hypotheses=[
                Hypothesis(
                    id="hyp-1",
                    description="Database connection issue",
                    confidence=0.7,
                )
            ],
            tool_invocations=[
                ToolInvocation(
                    tool_name="search_logs_tool",
                    rationale="Find database errors",
                    expected_outcome="Error logs",
                )
            ],
            reasoning="Need to investigate database connectivity",
            next_phase="verify",
        )
        assert plan.phase == "diagnose"
        assert len(plan.hypotheses) == 1
        assert len(plan.tool_invocations) == 1
        assert plan.next_phase == "verify"

    def test_empty_plan(self):
        """Test plan with no hypotheses or tools."""
        plan = Plan(
            phase="optimize",
            reasoning="Finalizing report",
        )
        assert plan.hypotheses == []
        assert plan.tool_invocations == []


class TestFinding:
    """Tests for Finding schema."""

    def test_valid_finding(self):
        """Test valid finding."""
        finding = Finding(
            title="High Error Rate",
            description="API gateway showing 500 errors",
            severity="high",
            evidence_ids=["ev-1", "ev-2"],
            recommendation="Restart api-gateway service",
        )
        assert finding.title == "High Error Rate"
        assert finding.severity == "high"
        assert len(finding.evidence_ids) == 2


class TestRecommendation:
    """Tests for Recommendation schema."""

    def test_valid_recommendation(self):
        """Test valid recommendation."""
        rec = Recommendation(
            title="Scale API Gateway",
            description="Increase replicas to handle load",
            priority="high",
            effort="low",
            impact="high",
            steps=[
                "Update deployment config",
                "Apply changes",
                "Monitor metrics",
            ],
        )
        assert rec.title == "Scale API Gateway"
        assert rec.priority == "high"
        assert len(rec.steps) == 3


class TestCitation:
    """Tests for Citation schema."""

    def test_valid_citation(self):
        """Test valid citation."""
        citation = Citation(
            source="log-12345",
            content="ERROR: Connection timeout",
            relevance_score=0.95,
            metadata={"timestamp": "2024-01-15T10:30:00Z"},
        )
        assert citation.source == "log-12345"
        assert citation.relevance_score == 0.95


class TestResponse:
    """Tests for Response schema."""

    def test_valid_response(self):
        """Test valid structured response."""
        response = Response(
            summary="Found database connection issues",
            findings=[
                Finding(
                    title="Connection Timeout",
                    description="Database timing out",
                    severity="critical",
                )
            ],
            recommendations=[
                Recommendation(
                    title="Increase timeout",
                    description="Set timeout to 30s",
                    priority="immediate",
                    effort="low",
                    impact="high",
                )
            ],
            citations=[
                Citation(
                    source="log-123",
                    content="ERROR: timeout",
                    relevance_score=0.9,
                )
            ],
            confidence=0.85,
            follow_up_questions=["Should we check other services?"],
        )
        assert response.summary == "Found database connection issues"
        assert len(response.findings) == 1
        assert len(response.recommendations) == 1
        assert response.confidence == 0.85

    def test_minimal_response(self):
        """Test minimal response."""
        response = Response(
            summary="No issues found",
            confidence=0.5,
        )
        assert response.findings == []
        assert response.recommendations == []
        assert response.citations == []


class TestCheckpointMetadata:
    """Tests for CheckpointMetadata schema."""

    def test_valid_checkpoint(self):
        """Test valid checkpoint metadata."""
        checkpoint = CheckpointMetadata(
            checkpoint_id="ckpt-123",
            run_id="run-456",
            phase="diagnose",
            timestamp=datetime.utcnow().isoformat(),
            token_usage={"total": 1000, "remaining": 99000},
            message_count=5,
            tool_call_count=2,
        )
        assert checkpoint.checkpoint_id == "ckpt-123"
        assert checkpoint.run_id == "run-456"
        assert checkpoint.message_count == 5
        assert checkpoint.tool_call_count == 2


class TestSchemaIntegration:
    """Integration tests for schema usage."""

    def test_plan_with_full_structure(self):
        """Test complete plan with all nested structures."""
        plan = Plan(
            phase="verify",
            hypotheses=[
                Hypothesis(
                    id="hyp-1",
                    description="Memory leak in service",
                    confidence=0.8,
                    evidence_ids=["ev-1"],
                    status="active",
                ),
                Hypothesis(
                    id="hyp-2",
                    description="Network congestion",
                    confidence=0.3,
                    status="rejected",
                ),
            ],
            tool_invocations=[
                ToolInvocation(
                    tool_name="service_health_tool",
                    parameters={"service": "api-gateway"},
                    rationale="Check memory usage",
                    expected_outcome="Memory metrics",
                    priority=1,
                ),
            ],
            reasoning="Verifying memory leak hypothesis",
            next_phase="optimize",
        )

        # Verify structure
        assert len(plan.hypotheses) == 2
        assert plan.hypotheses[0].confidence > plan.hypotheses[1].confidence
        assert plan.tool_invocations[0].priority == 1

    def test_response_with_full_structure(self):
        """Test complete response with all nested structures."""
        response = Response(
            summary="Critical database issue identified",
            findings=[
                Finding(
                    title="Connection Pool Exhausted",
                    description="All connections in use",
                    severity="critical",
                    evidence_ids=["ev-1", "ev-2"],
                    recommendation="Increase pool size",
                ),
            ],
            recommendations=[
                Recommendation(
                    title="Increase Connection Pool",
                    description="Set max_connections to 100",
                    priority="immediate",
                    effort="low",
                    impact="high",
                    steps=["Update config", "Restart service"],
                ),
            ],
            citations=[
                Citation(
                    source="log-123",
                    content="ERROR: No available connections",
                    relevance_score=0.95,
                    metadata={"severity": "ERROR"},
                ),
            ],
            confidence=0.9,
            follow_up_questions=["Should we monitor other services?"],
            metadata={"analysis_duration_ms": 1500},
        )

        # Verify structure
        assert response.findings[0].severity == "critical"
        assert response.recommendations[0].priority == "immediate"
        assert response.citations[0].relevance_score == 0.95
        assert response.confidence == 0.9
