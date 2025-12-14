from typing import TypedDict, List, Dict, Any, Optional, Annotated
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
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
    status: str
    error: Optional[str]
