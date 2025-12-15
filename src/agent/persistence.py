from google.cloud import bigquery
from datetime import datetime
import json
from src.config import config
from typing import Dict, Any, List, Optional

client = bigquery.Client(project=config.PROJECT_ID_AGENT)

def persist_agent_run(
    run_id: str,
    user_query: str,
    status: str,
    scope: Optional[Dict[str, Any]] = None,
    graph_state: Optional[Dict[str, Any]] = None,
    tool_calls: Optional[Dict[str, Any]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
    cost_summary: Optional[Dict[str, Any]] = None,
    runbook_ids: Optional[List[str]] = None,
    confidence: float = 0.0,
    error: Optional[str] = None
):
    table_id = f"{config.PROJECT_ID_AGENT}.{config.AGENT_DATASET}.agent_runs"
    
    scope = scope or {}
    graph_state = graph_state or {}
    tool_calls = tool_calls or {}
    evidence = evidence or []
    cost_summary = cost_summary or {}
    runbook_ids = runbook_ids or []
    
    row = {
        "run_id": run_id,
        "ts": datetime.utcnow().isoformat(),
        "user_query": user_query,
        "scope": json.dumps(scope),
        "graph_state": json.dumps(graph_state),
        "tool_calls": json.dumps(tool_calls),
        "evidence": [json.dumps(e) for e in evidence],
        "cost_summary": json.dumps(cost_summary),
        "runbook_ids": runbook_ids,
        "confidence": confidence,
        "status": status,
        "error": error
    }
    
    # Insert
    errors = client.insert_rows_json(table_id, [row])
    if errors:
        print(f"Failed to persist agent run: {errors}")
