from langchain_core.tools import tool
from typing import Optional, List, Dict, Any
import json
from datetime import datetime, timedelta
from src.agent.tools.bq import run_bq_query, BQQueryInput
# No longer need to import BQQueryInput from contracts if it's from bq
from src.config import config # Keep this import for other tools if needed

@tool
def bq_query_tool(sql: str, params: Optional[Dict[str, Any]] = None) -> str:
    """
    Executes a BigQuery query safely.
    Use this for custom analysis when other tools are insufficient.
    """
    try:
        res = run_bq_query(BQQueryInput(sql=sql, params=params))
        return json.dumps({
            "job_id": res.job_id,
            "rows": res.rows,
            "bytes": res.total_bytes_processed
        }, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
def search_logs_tool(query: str, severity: Optional[str] = None, hours: int = 1, limit: int = 20) -> str:
    """
    Searches logs in the linked log analytics dataset.
    """
    # Re-import config here to try and get the latest version
    import importlib
    import src.config
    importlib.reload(src.config)
    from src.config import config

    # Construct SQL dynamically
    table = f"{config.PROJECT_ID_LOGS}.{config.LOG_ANALYTICS_LINKED_DATASET}._AllLogs" # Assumption based on standard Linked Dataset
    
    # Linked datasets usually have `timestamp`, `textPayload`, `jsonPayload`, `severity` etc.
    # We might need to adjust column names based on the actual schema of the linked dataset.
    # For now, I'll use standard columns.
    
    start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    
    sql = f"""
    SELECT timestamp, severity, log_name, text_payload, json_payload
    FROM `{table}`
    WHERE timestamp > TIMESTAMP(@start_time)
    """
    
    params = {"start_time": start_time}
    
    if severity:
        sql += " AND severity = @severity"
        params["severity"] = severity
        
    if query:
        # Search in text_payload or json_payload
        sql += " AND (SEARCH(text_payload, @query) OR SEARCH(json_payload, @query))"
        params["query"] = query
        
    sql += " ORDER BY timestamp DESC LIMIT @limit"
    
    try:
        res = run_bq_query(BQQueryInput(sql=sql, params=params, max_rows=limit))
        return json.dumps(res.rows, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
def runbook_search_tool(query: str) -> str:
    """
    Searches for relevant runbooks.
    """
    # Placeholder
    return json.dumps([])
