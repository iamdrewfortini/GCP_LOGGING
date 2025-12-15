from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from src.agent.state import AgentState
from src.agent.llm import get_llm
from src.agent.tools.definitions import (
    bq_query_tool, search_logs_tool, runbook_search_tool, trace_lookup_tool,
    service_health_tool, repo_search_tool, create_view_tool, dashboard_spec_tool,
    # New enhanced tools
    analyze_logs, get_log_summary, find_related_logs, suggest_queries
)
from langgraph.prebuilt import ToolNode
from src.agent.persistence import persist_agent_run
import json

# Include all tools - prioritize smart tools
tools = [
    # Primary smart tools - use these first
    analyze_logs,
    get_log_summary,
    find_related_logs,
    suggest_queries,
    # Standard tools
    search_logs_tool,
    trace_lookup_tool,
    service_health_tool,
    bq_query_tool,
    # Supporting tools
    runbook_search_tool,
    repo_search_tool,
    create_view_tool,
    dashboard_spec_tool
]
llm = get_llm().bind_tools(tools)

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

def diagnose_node(state: AgentState):
    messages = state['messages']
    sys_msg = SystemMessage(content=SMART_AGENT_PROMPT + """

## Current Phase: DIAGNOSE
Goal: Understand the request and gather evidence immediately.
- Use smart tools to get data first
- Don't ask clarifying questions for common requests
- Present findings clearly with markdown formatting
""")

    res = llm.invoke([sys_msg] + messages)

    return {
        "messages": [res],
        "phase": "diagnose"
    }

def verify_node(state: AgentState):
    messages = state['messages']
    sys_msg = SystemMessage(content=SMART_AGENT_PROMPT + """

## Current Phase: VERIFY
Goal: Confirm findings and dig deeper if needed.
- Use trace_lookup_tool for specific traces
- Use find_related_logs for error context
- Verify patterns identified in diagnosis
""")

    res = llm.invoke([sys_msg] + messages)

    return {
        "messages": [res],
        "phase": "verify"
    }

def optimize_node(state: AgentState):
    messages = state['messages']
    sys_msg = SystemMessage(content=SMART_AGENT_PROMPT + """

## Current Phase: OPTIMIZE
Goal: Provide actionable recommendations and final report.
- Summarize key findings
- Prioritize issues by severity
- Suggest specific fixes
- Offer follow-up actions
""")

    res = llm.invoke([sys_msg] + messages)

    return {
        "messages": [res],
        "phase": "optimize"
    }

def persist_node(state: AgentState):
    """
    Persists the run to BigQuery.
    """
    run_id = state.get("run_id")
    if run_id:
        # Extract evidence from messages (simplification)
        # Ideally we'd parse tool outputs
        persist_agent_run(
            run_id=run_id,
            user_query=state.get("user_query", ""),
            status="completed", # or state.get("status")
            scope=state.get("scope", {}),
            evidence=state.get("evidence", [])
        )
    return state

tool_node = ToolNode(tools)
