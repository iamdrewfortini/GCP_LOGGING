"""Pydantic schemas for structured LLM outputs.

This module defines structured output models for LangGraph nodes,
enabling type-safe LLM responses with validation.

Phase 3, Task 3.1: Structured Outputs
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class IngressValidation(BaseModel):
    """Structured output for initial query validation and understanding.

    Used by the diagnose node to validate and parse user intent.
    """
    is_valid: bool = Field(
        description="Whether the query is valid and actionable"
    )
    intent: Literal["debug", "analyze", "search", "monitor", "other"] = Field(
        description="Primary intent of the user query"
    )
    entities: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Extracted entities (services, timeframes, error_types, etc.)"
    )
    timeframe: Optional[str] = Field(
        default=None,
        description="Extracted timeframe (e.g., '24h', '1h', '7d')"
    )
    severity_filter: Optional[List[str]] = Field(
        default=None,
        description="Severity levels to filter (ERROR, WARNING, INFO, etc.)"
    )
    clarification_needed: bool = Field(
        default=False,
        description="Whether clarification is needed from user"
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="Question to ask user if clarification needed"
    )
    suggested_tools: List[str] = Field(
        default_factory=list,
        description="Suggested tools to use for this query"
    )


class Hypothesis(BaseModel):
    """A hypothesis about the issue being investigated."""
    id: str = Field(description="Unique hypothesis identifier")
    description: str = Field(description="Hypothesis description")
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score (0.0 to 1.0)"
    )
    evidence_ids: List[str] = Field(
        default_factory=list,
        description="IDs of evidence supporting this hypothesis"
    )
    status: Literal["active", "confirmed", "rejected"] = Field(
        default="active",
        description="Current status of hypothesis"
    )


class Evidence(BaseModel):
    """Evidence gathered during investigation."""
    id: str = Field(description="Unique evidence identifier")
    source: str = Field(description="Source of evidence (tool name, etc.)")
    content: str = Field(description="Evidence content/summary")
    severity: Optional[str] = Field(
        default=None,
        description="Severity level if applicable"
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="Timestamp of evidence"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )
    relevance_score: float = Field(
        ge=0.0, le=1.0,
        default=1.0,
        description="Relevance to current investigation"
    )


class ToolInvocation(BaseModel):
    """Planned or executed tool invocation."""
    tool_name: str = Field(description="Name of the tool")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool parameters"
    )
    rationale: str = Field(description="Why this tool is being called")
    expected_outcome: str = Field(
        description="What we expect to learn from this tool"
    )
    priority: int = Field(
        ge=1, le=10,
        default=5,
        description="Priority (1=highest, 10=lowest)"
    )


class Plan(BaseModel):
    """Structured investigation plan.

    Used by diagnose/verify nodes to plan tool invocations.
    """
    phase: Literal["diagnose", "verify", "optimize"] = Field(
        description="Current investigation phase"
    )
    hypotheses: List[Hypothesis] = Field(
        default_factory=list,
        description="Current hypotheses being investigated"
    )
    tool_invocations: List[ToolInvocation] = Field(
        default_factory=list,
        description="Planned tool invocations"
    )
    reasoning: str = Field(
        description="Reasoning for this plan"
    )
    next_phase: Optional[Literal["diagnose", "verify", "optimize", "complete"]] = Field(
        default=None,
        description="Suggested next phase"
    )


class Finding(BaseModel):
    """A key finding from the investigation."""
    title: str = Field(description="Finding title")
    description: str = Field(description="Detailed description")
    severity: Literal["critical", "high", "medium", "low", "info"] = Field(
        description="Severity level"
    )
    evidence_ids: List[str] = Field(
        default_factory=list,
        description="Supporting evidence IDs"
    )
    recommendation: Optional[str] = Field(
        default=None,
        description="Recommended action"
    )


class Recommendation(BaseModel):
    """Actionable recommendation."""
    title: str = Field(description="Recommendation title")
    description: str = Field(description="Detailed description")
    priority: Literal["immediate", "high", "medium", "low"] = Field(
        description="Priority level"
    )
    effort: Literal["low", "medium", "high"] = Field(
        description="Estimated effort"
    )
    impact: Literal["low", "medium", "high"] = Field(
        description="Expected impact"
    )
    steps: List[str] = Field(
        default_factory=list,
        description="Implementation steps"
    )


class Citation(BaseModel):
    """Citation/source reference."""
    source: str = Field(description="Source identifier (log ID, trace ID, etc.)")
    content: str = Field(description="Relevant excerpt")
    relevance_score: float = Field(
        ge=0.0, le=1.0,
        description="Relevance score"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )


class Response(BaseModel):
    """Structured final response.

    Used by optimize node to provide final report.
    """
    summary: str = Field(description="Executive summary")
    findings: List[Finding] = Field(
        default_factory=list,
        description="Key findings"
    )
    recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="Actionable recommendations"
    )
    citations: List[Citation] = Field(
        default_factory=list,
        description="Sources and citations"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Overall confidence in analysis"
    )
    follow_up_questions: List[str] = Field(
        default_factory=list,
        description="Suggested follow-up questions"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )


class CheckpointMetadata(BaseModel):
    """Metadata for state checkpoint.

    Used by checkpoint node to save state snapshots.
    """
    checkpoint_id: str = Field(description="Unique checkpoint identifier")
    run_id: str = Field(description="Agent run ID")
    phase: str = Field(description="Phase when checkpoint was created")
    timestamp: str = Field(description="ISO timestamp")
    token_usage: Dict[str, int] = Field(
        default_factory=dict,
        description="Token usage at checkpoint"
    )
    message_count: int = Field(description="Number of messages at checkpoint")
    tool_call_count: int = Field(
        default=0,
        description="Number of tool calls at checkpoint"
    )
