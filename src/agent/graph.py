from langgraph.graph import StateGraph, END
from src.agent.state import AgentState
from src.agent.nodes import diagnose_node, verify_node, optimize_node, tool_node, persist_node
from langgraph.prebuilt import tools_condition

workflow = StateGraph(AgentState)

workflow.add_node("diagnose", diagnose_node)
workflow.add_node("verify", verify_node)
workflow.add_node("optimize", optimize_node)
workflow.add_node("tools", tool_node)
workflow.add_node("persist", persist_node)

def dispatcher(state: AgentState):
    phase = state.get("phase", "diagnose")
    return phase

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
