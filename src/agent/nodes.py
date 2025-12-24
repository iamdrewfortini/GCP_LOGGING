"""LangGraph nodes for the Glass Pane AI agent.

This module defines the node functions for the agent workflow,
including token budget tracking at each step.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from src.agent.state import AgentState, TokenBudgetState
from src.agent.llm import get_llm
from src.agent.tools.definitions import (
    bq_query_tool, search_logs_tool, runbook_search_tool, trace_lookup_tool,
    service_health_tool, repo_search_tool, create_view_tool, dashboard_spec_tool,
    # New enhanced tools
    analyze_logs, get_log_summary, find_related_logs, suggest_queries,
    # Semantic search tools (Phase 2)
    semantic_search_logs, find_similar_logs
)
from src.agent.tokenization import TokenBudgetManager, estimate_tool_output_tokens
try:
    from langgraph.prebuilt import ToolNode
except ModuleNotFoundError:  # Optional dependency for some dev/test environments
    ToolNode = None  # type: ignore
import json
import logging

logger = logging.getLogger(__name__)

# Global token budget manager (initialized per-request)
# This is a module-level reference that gets updated per request
_token_manager: Optional[TokenBudgetManager] = None


def get_token_manager(model: str = "gpt-4", max_tokens: int = 100_000) -> TokenBudgetManager:
    """Get or create token budget manager.

    Args:
        model: Model name for tokenizer
        max_tokens: Maximum token budget

    Returns:
        TokenBudgetManager instance
    """
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenBudgetManager(model=model, max_tokens=max_tokens)
    return _token_manager


def reset_token_manager() -> None:
    """Reset the token manager for a new request."""
    global _token_manager
    _token_manager = None


def update_token_budget(
    state: AgentState,
    manager: TokenBudgetManager,
    phase: str,
) -> TokenBudgetState:
    """Update token budget state with current manager state.

    Args:
        state: Current agent state
        manager: Token budget manager
        phase: Current phase (diagnose, verify, optimize, etc.)

    Returns:
        Updated TokenBudgetState
    """
    status = manager.get_budget_status()
    return TokenBudgetState(
        prompt_tokens=status["tokens_used"],
        completion_tokens=0,  # Updated during streaming
        total_tokens=status["tokens_used"],
        budget_max=status["max_tokens"],
        budget_remaining=status["tokens_remaining"],
        last_update_ts=datetime.now(timezone.utc).isoformat(),
        model=manager.encoding.name,
        should_summarize=manager.should_summarize(),
    )


def track_message_tokens(
    manager: TokenBudgetManager,
    messages: list[BaseMessage],
    phase: str = "unknown",
) -> int:
    """Track tokens for messages and reserve from budget.

    Args:
        manager: Token budget manager
        messages: Messages to track
        phase: Current phase for logging

    Returns:
        Token count for the messages
    """
    token_count = manager.count_messages(messages)
    try:
        manager.reserve_tokens(token_count)
        logger.debug(f"[{phase}] Reserved {token_count} tokens. Status: {manager.get_budget_status()}")
    except Exception as e:
        logger.warning(f"[{phase}] Token reservation warning: {e}")
    return token_count


def track_tool_tokens(
    manager: TokenBudgetManager,
    tool_name: str,
    tool_input: Dict[str, Any],
) -> int:
    """Estimate and track tokens for tool execution.

    Args:
        manager: Token budget manager
        tool_name: Name of the tool
        tool_input: Tool input parameters

    Returns:
        Estimated token count
    """
    estimated_tokens = estimate_tool_output_tokens(tool_name, tool_input)
    try:
        manager.reserve_tokens(estimated_tokens)
        logger.debug(f"[tools] Reserved {estimated_tokens} tokens for {tool_name}")
    except Exception as e:
        logger.warning(f"[tools] Token reservation warning for {tool_name}: {e}")
    return estimated_tokens


# Include all tools - prioritize smart tools
tools = [
    # Primary smart tools - use these first
    analyze_logs,
    get_log_summary,
    find_related_logs,
    suggest_queries,
    # Semantic search tools (Phase 2)
    semantic_search_logs,
    find_similar_logs,
    # Standard tools
    search_logs_tool,
    trace_lookup_tool,
    service_health_tool,
    bq_query_tool,
    # Supporting tools
    runbook_search_tool,
    repo_search_tool,
    create_view_tool,
    dashboard_spec_tool,
]

_bound_llm = None


def get_bound_llm():
    """Lazy init model binding.

    Avoids import-time failures when optional Vertex/GenAI deps aren't installed.
    """
    global _bound_llm
    if _bound_llm is None:
        _bound_llm = get_llm().bind_tools(tools)
    return _bound_llm

# Enhanced system prompt that's more proactive and uses smart defaults
SMART_AGENT_PROMPT = """You are an expert GCP Log Debugger AI assistant. You help users analyze logs, troubleshoot issues, and understand their infrastructure.

## Key Behaviors:
1. **BE PROACTIVE**: Don't ask clarifying questions for common requests. Use smart defaults:
   - "check logs" / "show logs" / "summary" → Use `get_log_summary(hours=24)` or `analyze_logs(intent="summary")`
   - "errors" / "what's wrong" → Use `analyze_logs(intent="errors", timeframe="24h")`
   - "last hour" / "recent" → Use timeframe="1h"
   - "today" / "24 hours" → Use timeframe="24h"
   - "this week" → Use timeframe="7d"

2. **USE SMART TOOLS**: Prefer these tools that handle vague requests well:
   - `analyze_logs`: For comprehensive analysis - handles broad queries like "check all logs"
   - `get_log_summary`: For quick health checks and overviews
   - `find_related_logs`: For investigating specific errors
   - `suggest_queries`: When user needs guidance

3. **FORMAT RESPONSES WELL**:
   - Use markdown headers, bullet points, and tables
   - Highlight critical errors with severity indicators
   - Group related information together
   - Provide actionable recommendations

4. **PROVIDE CONTEXT**: After showing results, suggest next steps:
   - "Would you like me to investigate [specific error]?"
   - "I can show you more details about [service]"
   - "Here are some follow-up queries you might find useful"

5. **HANDLE AMBIGUITY**: If truly ambiguous, make a reasonable assumption and proceed:
   - "I'll check the last 24 hours (the most common timeframe)..."
   - "Looking at all severity levels to give you a complete picture..."

## Response Format:
Always structure your responses clearly:
- Start with a brief summary
- Present data in organized sections
- End with recommendations or suggested next steps

Remember: Users want answers, not questions. Take action first, ask later only if truly needed."""

def retrieval_node(state: AgentState):
    """Retrieval node - semantic search for relevant context (Phase 2).

    Performs vector search to find semantically similar logs/content
    before diagnosis begins. Adds context to help the agent.

    This node runs before diagnose to provide relevant background.
    """
    from src.services.vector_service import vector_service
    from src.config import config

    user_query = state.get("user_query", "")

    # Skip if vector search is disabled or no query
    if not vector_service.enabled or not user_query:
        logger.debug("Skipping retrieval: vector search disabled or no query")
        return {
            "phase": "diagnose",
            "evidence": state.get("evidence", []),
        }

    try:
        # Perform semantic search
        project_id = config.PROJECT_ID_LOGS
        results = vector_service.semantic_search_logs(
            query=user_query,
            project_id=project_id,
            top_k=5,  # Get top 5 relevant logs
        )

        if results:
            # Add results as evidence
            evidence = state.get("evidence", [])
            semantic_context = {
                "type": "semantic_search",
                "query": user_query,
                "results": [
                    {
                        "score": r.score,
                        "content": r.content[:500],  # Limit content length
                        "severity": r.metadata.get("severity"),
                        "service": r.metadata.get("service"),
                        "timestamp": r.timestamp,
                    }
                    for r in results
                ],
                "count": len(results),
            }
            evidence.append(semantic_context)

            logger.info(f"Retrieval found {len(results)} relevant logs for query")

            return {
                "phase": "diagnose",
                "evidence": evidence,
            }

    except Exception as e:
        logger.warning(f"Retrieval error (non-fatal): {e}")

    return {
        "phase": "diagnose",
        "evidence": state.get("evidence", []),
    }


def diagnose_node(state: AgentState):
    """Diagnose node - understand and gather evidence.

    Tracks tokens for input messages and LLM response.
    """
    messages = state['messages']
    sys_msg = SystemMessage(content=SMART_AGENT_PROMPT + """

## Current Phase: DIAGNOSE
Goal: Understand the request and gather evidence immediately.
- Use smart tools to get data first
- Don't ask clarifying questions for common requests
- Present findings clearly with markdown formatting
""")

    # Track input tokens
    manager = get_token_manager()
    track_message_tokens(manager, [sys_msg] + messages, "diagnose")

    llm = get_bound_llm()
    res = llm.invoke([sys_msg] + messages)

    # Track output tokens
    track_message_tokens(manager, [res], "diagnose")

    return {
        "messages": [res],
        "phase": "diagnose",
        "token_budget": update_token_budget(state, manager, "diagnose"),
    }

def verify_node(state: AgentState):
    """Verify node - confirm findings and dig deeper.

    Tracks tokens for input messages and LLM response.
    """
    messages = state['messages']
    sys_msg = SystemMessage(content=SMART_AGENT_PROMPT + """

## Current Phase: VERIFY
Goal: Confirm findings and dig deeper if needed.
- Use trace_lookup_tool for specific traces
- Use find_related_logs for error context
- Verify patterns identified in diagnosis
""")

    # Track input tokens
    manager = get_token_manager()
    track_message_tokens(manager, [sys_msg] + messages, "verify")

    llm = get_bound_llm()
    res = llm.invoke([sys_msg] + messages)

    # Track output tokens
    track_message_tokens(manager, [res], "verify")

    return {
        "messages": [res],
        "phase": "verify",
        "token_budget": update_token_budget(state, manager, "verify"),
    }

def optimize_node(state: AgentState):
    """Optimize node - provide recommendations and final report.

    Tracks tokens for input messages and LLM response.
    """
    messages = state['messages']
    sys_msg = SystemMessage(content=SMART_AGENT_PROMPT + """

## Current Phase: OPTIMIZE
Goal: Provide actionable recommendations and final report.
- Summarize key findings
- Prioritize issues by severity
- Suggest specific fixes
- Offer follow-up actions
""")

    # Track input tokens
    manager = get_token_manager()
    track_message_tokens(manager, [sys_msg] + messages, "optimize")

    llm = get_bound_llm()
    res = llm.invoke([sys_msg] + messages)

    # Track output tokens
    track_message_tokens(manager, [res], "optimize")

    return {
        "messages": [res],
        "phase": "optimize",
        "token_budget": update_token_budget(state, manager, "optimize"),
    }

def checkpoint_node(state: AgentState):
    """Checkpoint node - save state snapshot to Firestore.

    Saves current state to Firestore and emits checkpoint event.
    Phase 3, Task 3.2: Checkpoint Node
    """
    try:
        from src.agent.checkpoint import save_checkpoint

        # Save checkpoint
        metadata = save_checkpoint(state)

        logger.info(
            f"Checkpoint created: {metadata.checkpoint_id} "
            f"(phase={metadata.phase}, tokens={metadata.token_usage.get('total_tokens', 0)})"
        )

        # Return state with checkpoint metadata
        return {
            "status": "checkpoint_saved",
            "evidence": state.get("evidence", []) + [
                {
                    "type": "checkpoint",
                    "checkpoint_id": metadata.checkpoint_id,
                    "timestamp": metadata.timestamp,
                    "phase": metadata.phase,
                }
            ],
        }

    except Exception as e:
        logger.error(f"Checkpoint failed: {e}")
        # Non-fatal error - continue execution
        return {"status": "checkpoint_failed", "error": str(e)}


def persist_node(state: AgentState):
    """Persist node - save run to BigQuery with token stats.

    Includes final token budget information in persistence.
    """
    run_id = state.get("run_id")
    manager = get_token_manager()

    # Get final token budget status
    final_budget = update_token_budget(state, manager, "persist")

    if run_id:
        # Extract evidence from messages (simplification)
        # Ideally we'd parse tool outputs
        from src.agent.persistence import persist_agent_run

        persist_agent_run(
            run_id=run_id,
            user_query=state.get("user_query", ""),
            status="completed",
            scope=state.get("scope", {}),
            evidence=state.get("evidence", []),
            token_usage={
                "prompt_tokens": final_budget.get("prompt_tokens", 0),
                "completion_tokens": final_budget.get("completion_tokens", 0),
                "total_tokens": final_budget.get("total_tokens", 0),
            }
        )

    # Reset token manager for next request
    reset_token_manager()

    return {
        **state,
        "token_budget": final_budget,
        "status": "completed",
    }

tool_node = ToolNode(tools) if ToolNode is not None else None
