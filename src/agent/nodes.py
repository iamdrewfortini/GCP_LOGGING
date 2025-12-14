from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from src.agent.state import AgentState
from src.agent.llm import get_llm
from src.agent.tools.definitions import bq_query_tool, search_logs_tool, runbook_search_tool
from langgraph.prebuilt import ToolNode
from src.agent.persistence import persist_agent_run
import json

tools = [bq_query_tool, search_logs_tool, runbook_search_tool]
llm = get_llm().bind_tools(tools)

def diagnose_node(state: AgentState):
    messages = state['messages']
    sys_msg = SystemMessage(content="""PHASE: DIAGNOSE
    Goal: Understand the issue and gather initial evidence.
    1. Identify scope.
    2. Search logs and metrics.
    If you have sufficient evidence, stop calling tools and just reply with your findings to proceed to verification.
    """)
    
    res = llm.invoke([sys_msg] + messages)
    
    return {
        "messages": [res],
        "phase": "diagnose"
    }

def verify_node(state: AgentState):
    messages = state['messages']
    sys_msg = SystemMessage(content="""PHASE: VERIFY
    Goal: Confirm hypotheses.
    Review the findings from Diagnosis.
    Use tools to verify specific details (e.g. check specific traces, billing tables).
    If verified, stop calling tools to proceed to optimization.
    """)
    
    res = llm.invoke([sys_msg] + messages)
    
    return {
        "messages": [res],
        "phase": "verify"
    }

def optimize_node(state: AgentState):
    messages = state['messages']
    sys_msg = SystemMessage(content="""PHASE: OPTIMIZE
    Goal: Suggest improvements.
    Check for cost/performance optimizations.
    Provide your final report.
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
