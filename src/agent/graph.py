"""LangGraph workflow for Glass Pane AI agent.

This module defines the agent workflow with the following phases:
1. retrieval - Semantic search for relevant context (Phase 2)
2. diagnose - Understand the request and gather evidence
3. verify - Confirm findings and dig deeper
4. optimize - Provide recommendations
5. persist - Save run to BigQuery
"""

import os
from langgraph.graph import StateGraph, END
from src.agent.state import AgentState
from src.agent.nodes import (
    diagnose_node,
    verify_node,
    optimize_node,
    tool_node,
    persist_node,
    retrieval_node,
)
from langgraph.prebuilt import tools_condition

# Feature flag for retrieval node (Phase 2)
ENABLE_RETRIEVAL = os.getenv("ENABLE_RETRIEVAL", "true").lower() == "true"

workflow = StateGraph(AgentState)

# Add retrieval node if enabled (Phase 2)
if ENABLE_RETRIEVAL:
    workflow.add_node("retrieval", retrieval_node)

workflow.add_node("diagnose", diagnose_node)
workflow.add_node("verify", verify_node)
workflow.add_node("optimize", optimize_node)
workflow.add_node("tools", tool_node)
workflow.add_node("persist", persist_node)


def dispatcher(state: AgentState):
    """Route tool results back to the calling phase."""
    phase = state.get("phase", "diagnose")
    return phase


# Set entry point based on retrieval flag
if ENABLE_RETRIEVAL:
    workflow.set_entry_point("retrieval")
    # Retrieval always goes to diagnose
    workflow.add_edge("retrieval", "diagnose")
else:
    workflow.set_entry_point("diagnose")

# Diagnose transitions
workflow.add_conditional_edges(
    "diagnose",
    tools_condition,
    {"tools": "tools", "__end__": "verify"}
)

# Verify transitions
workflow.add_conditional_edges(
    "verify",
    tools_condition,
    {"tools": "tools", "__end__": "optimize"}
)

# Optimize transitions
workflow.add_conditional_edges(
    "optimize",
    tools_condition,
    {"tools": "tools", "__end__": "persist"}
)

# Persist transitions
workflow.add_edge("persist", END)

# Tool transitions - return to caller
workflow.add_conditional_edges(
    "tools",
    dispatcher,
    {
        "diagnose": "diagnose",
        "verify": "verify",
        "optimize": "optimize"
    }
)

graph = workflow.compile()
