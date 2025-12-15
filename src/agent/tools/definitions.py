from langchain_core.tools import tool
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json
import hashlib

from src.agent.tools.bq import run_bq_query
from src.agent.tools.contracts import BQQueryInput, LogEvent, TraceSpan
from src.config import config
from google.cloud import trace_v2
from google.cloud import run_v2

def normalize_log_event(row: Dict[str, Any]) -> LogEvent:
    json_payload = None
    if row.get('json_payload_str'):
        try:
            json_payload = json.loads(row['json_payload_str'])
        except:
            json_payload = None

    # Extract fields from json_payload if available
    requestUrl = json_payload.get('requestUrl') if json_payload else row.get('requestUrl')
    requestMethod = json_payload.get('requestMethod') if json_payload else row.get('requestMethod')
    status = json_payload.get('status') if json_payload else row.get('status')
    latency_s = json_payload.get('latency_s') if json_payload else row.get('latency_s')
    userAgent = json_payload.get('userAgent') if json_payload else row.get('userAgent')
    remoteIp = json_payload.get('remoteIp') if json_payload else row.get('remoteIp')

    # Compute fingerprint
    key = f"{row['service']}{requestMethod or ''}{requestUrl or ''}{status or ''}{row.get('display_message', '')}"
    error_fingerprint = hashlib.md5(key.encode()).hexdigest()

    return LogEvent(
        event_ts=row['event_ts'],
        severity=row['severity'],
        service=row['service'],
        source_table=row['source_table'],
        display_message=row['display_message'],
        json_payload=json_payload,
        trace=row.get('trace'),
        spanId=row.get('spanId'),
        requestUrl=requestUrl,
        requestMethod=requestMethod,
        status=status,
        latency_s=latency_s,
        userAgent=userAgent,
        remoteIp=remoteIp,
        error_fingerprint=error_fingerprint
    )

@tool
def bq_query_tool(sql: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Executes a BigQuery query safely.
    Use this for custom analysis when other tools are insufficient.
    """
    try:
        res = run_bq_query(BQQueryInput(sql=sql, params=params))
        return {
            "job_id": res.job_id,
            "rows": res.rows,
            "bytes": res.total_bytes_processed
        }
    except Exception as e:
        return {"error": str(e)}

@tool
def dashboard_spec_tool(title: str, panels: List[Dict[str, Any]], filters: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate a vendor-neutral dashboard spec (can be mapped to Looker Studio/Grafana later).
    """
    spec = {
        "title": title,
        "panels": panels,
        "filters": filters,
        "alerts": alerts
    }
    return {"spec": spec}

@tool
def repo_search_tool(pattern: str, paths: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Find endpoint handlers, session code paths, auth middleware, firestore queries.
    """
    # Placeholder: use search tool logic
    # For now, return dummy
    return {"matches": []}

@tool
def create_view_tool(dataset: str, view_name: str, sql: str) -> Dict[str, Any]:
    """
    Materialize normalized views used by dashboards.
    """
    try:
        full_view = f"{config.PROJECT_ID_LOGS}.{dataset}.{view_name}"
        create_sql = f"CREATE OR REPLACE VIEW `{full_view}` AS {sql}"
        res = run_bq_query(BQQueryInput(sql=create_sql))
        return {"status": "success", "view": full_view}
    except Exception as e:
        return {"error": str(e)}

@tool
def search_logs_tool(query: str, severity: Optional[str] = None, service: Optional[str] = None, hours: int = 1, limit: int = 20) -> Dict[str, Any]:
    """
    Searches logs in the central logging dataset.
    Args:
        query: Search term to find in log messages (searches display_message and json_payload_str)
        severity: Optional severity filter (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        service: Optional service filter
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

    if service:
        sql += " AND service = @service"
        params["service"] = service

    if query:
        # Search in display_message and json_payload_str
        sql += " AND (LOWER(display_message) LIKE LOWER(@query_pattern) OR LOWER(json_payload_str) LIKE LOWER(@query_pattern))"
        params["query_pattern"] = f"%{query}%"

    sql += f" ORDER BY event_ts DESC LIMIT {limit}"

    try:
        res = run_bq_query(BQQueryInput(sql=sql, params=params, max_rows=limit))
        events = [normalize_log_event(row).dict() for row in res.rows]
        return {"events": events}
    except Exception as e:
        return {"error": str(e)}

@tool
def runbook_search_tool(query: str) -> str:
    """
    Searches for relevant runbooks.
    """
    # Placeholder
    return json.dumps([])

@tool
def trace_lookup_tool(trace: str, project: str) -> Dict[str, Any]:
    """
    Fetch spans for a trace to pinpoint failing handler + latency breakdown.
    """
    try:
        client = trace_v2.TraceServiceClient()
        request = trace_v2.GetTraceRequest(
            project_id=project,
            trace_id=trace
        )
        trace_data = client.get_trace(request)
        spans = []
        for span in trace_data.spans:
            spans.append(TraceSpan(
                spanId=span.span_id,
                parentSpanId=span.parent_span_id,
                name=span.name,
                startTime=span.start_time.isoformat() if span.start_time else None,
                endTime=span.end_time.isoformat() if span.end_time else None,
                attributes=dict(span.attributes.attribute_map),
                status={"code": span.status.code, "message": span.status.message} if span.status else None
            ).dict())
        return {"spans": spans}
    except Exception as e:
        return {"error": str(e)}

@tool
def service_health_tool(service: str, region: Optional[str] = None) -> Dict[str, Any]:
    """
    Detect bad deploys, env drift, missing secrets, revision regressions.
    """
    try:
        client = run_v2.ServicesClient()
        parent = f"projects/{config.PROJECT_ID_AGENT}/locations/{region or 'us-central1'}"
        request = run_v2.ListServicesRequest(parent=parent)
        services = client.list_services(request)
        for svc in services:
            if svc.name.endswith(f"/services/{service}"):
                revisions = []
                for rev in svc.revisions:
                    revisions.append({
                        "name": rev.name,
                        "image": rev.containers[0].image if rev.containers else None,
                        "env": dict(rev.containers[0].env) if rev.containers and rev.containers[0].env else {},
                        "created": rev.create_time.isoformat() if rev.create_time else None
                    })
                latest_rev = revisions[0] if revisions else None
                env = latest_rev.get("env") if latest_rev else {}
                return {
                    "revisions": revisions,
                    "latestRevision": latest_rev,
                    "env": env
                }
        return {"error": "Service not found"}
    except Exception as e:
        return {"error": str(e)}
