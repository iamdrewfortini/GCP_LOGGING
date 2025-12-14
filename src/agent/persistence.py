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
    scope: Dict[str, Any] = {},
    graph_state: Dict[str, Any] = {},
    tool_calls: Dict[str, Any] = {},
    evidence: List[Dict[str, Any]] = [],
    cost_summary: Dict[str, Any] = {},
    runbook_ids: List[str] = [],
    confidence: float = 0.0,
    error: Optional[str] = None
):
    table_id = f"{config.PROJECT_ID_AGENT}.{config.AGENT_DATASET}.agent_runs"
    
    # Check if table exists, create if not (simplified for this context, ideally terraform/migration)
    # For now, we assume the setup phase handles table creation or we do a lazy check.
    # Given the prompt tasks, T5 is tool layer + artifact write.
    
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
