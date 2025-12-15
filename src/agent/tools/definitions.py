from langchain_core.tools import tool
from typing import Optional, Dict, Any
import json
from datetime import datetime, timedelta

from src.agent.tools.bq import run_bq_query
from src.agent.tools.contracts import BQQueryInput
from src.config import config

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
    Searches logs in the central logging dataset.
    Args:
        query: Search term to find in log messages (searches display_message and json_payload_str)
        severity: Optional severity filter (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        hours: Number of hours to look back (default: 1)
        limit: Maximum number of logs to return (default: 20)
    """
    from src.config import config

    # Use the canonical view that unions all log tables
    project_id = config.PROJECT_ID_LOGS
    dataset_id = "central_logging_v1"
    view = f"{project_id}.{dataset_id}.view_canonical_logs"

    start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    end_time = datetime.utcnow().isoformat()

    sql = f"""
    SELECT
        event_ts,
        severity,
        service,
        source_table,
        display_message,
        json_payload_str,
        trace,
        spanId
    FROM `{view}`
    WHERE event_ts BETWEEN TIMESTAMP(@start_time) AND TIMESTAMP(@end_time)
    """

    params = {
        "start_time": start_time,
        "end_time": end_time
    }

    if severity:
        sql += " AND severity = @severity"
        params["severity"] = severity

    if query:
        # Search in display_message and json_payload_str
        sql += " AND (LOWER(display_message) LIKE LOWER(@query_pattern) OR LOWER(json_payload_str) LIKE LOWER(@query_pattern))"
        params["query_pattern"] = f"%{query}%"

    sql += f" ORDER BY event_ts DESC LIMIT {limit}"

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
