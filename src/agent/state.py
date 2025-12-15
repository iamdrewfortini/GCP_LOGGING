"""Agent state definition for LangGraph orchestration.

This module defines the state schema for the Glass Pane AI agent,
including token budget tracking for context management.
"""

from typing import TypedDict, List, Dict, Any, Optional, Annotated
import operator
from datetime import datetime, timezone
from langchain_core.messages import BaseMessage


class TokenBudgetState(TypedDict, total=False):
    """Token budget tracking state.

    All fields are optional to allow incremental updates.
    """
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    budget_max: int
    budget_remaining: int
    last_update_ts: str
    model: str
    should_summarize: bool


class AgentState(TypedDict, total=False):
    """Complete agent state for LangGraph.

    Includes token budget tracking as first-class fields
    to enable budget enforcement and monitoring.
    """
    # Core execution state
    run_id: str
    user_query: str
    messages: Annotated[List[BaseMessage], operator.add]
    scope: Dict[str, Any]
    hypotheses: List[str]
    evidence: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    cost_summary: Dict[str, Any]
    runbook_ids: List[str]
    phase: str
    mode: str
    status: str
    error: Optional[str]

    # Token budget tracking (Task 1.2)
    token_budget: TokenBudgetState


def create_initial_state(
    run_id: str,
    user_query: str,
    messages: List[BaseMessage],
    scope: Optional[Dict[str, Any]] = None,
    budget_max: int = 100_000,
    model: str = "gpt-4",
) -> AgentState:
    """Create initial agent state with token budget initialized.

    Args:
        run_id: Unique run identifier
        user_query: The user's query
        messages: Initial message list
        scope: Query scope/context
        budget_max: Maximum token budget
        model: Model name for tokenizer

    Returns:
        Initialized AgentState
    """
    return AgentState(
        run_id=run_id,
        user_query=user_query,
        messages=messages,
        scope=scope or {},
        hypotheses=[],
        evidence=[],
        tool_calls=[],
        cost_summary={},
        runbook_ids=[],
        phase="diagnose",
        mode="interactive",
        status="running",
        error=None,
        token_budget=TokenBudgetState(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            budget_max=budget_max,
            budget_remaining=budget_max,
            last_update_ts=datetime.now(timezone.utc).isoformat(),
            model=model,
            should_summarize=False,
        ),
    )
