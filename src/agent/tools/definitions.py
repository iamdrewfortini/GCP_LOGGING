from langchain_core.tools import tool
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json
import hashlib
import re

from src.agent.tools.bq import run_bq_query
from src.agent.tools.contracts import BQQueryInput, LogEvent, TraceSpan
from src.config import config

# Smart defaults for common queries
DEFAULT_HOURS = 24
DEFAULT_LIMIT = 50
SEVERITY_LEVELS = ["DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY"]

def normalize_log_event(row: Dict[str, Any]) -> LogEvent:
    """Normalize a BigQuery row from master_logs to LogEvent model."""
    # Handle json_payload - can be string or dict from master_logs
    json_payload = None
    raw_json = row.get('json_payload')
    if raw_json:
        if isinstance(raw_json, str):
            try:
                json_payload = json.loads(raw_json)
            except:
                json_payload = None
        elif isinstance(raw_json, dict):
            json_payload = raw_json

    # Extract HTTP fields - prefer direct columns, fallback to json_payload
    http_url = row.get('http_url') or (json_payload.get('requestUrl') if json_payload else None)
    http_method = row.get('http_method') or (json_payload.get('requestMethod') if json_payload else None)
    http_status = row.get('http_status') or (json_payload.get('status') if json_payload else None)
    http_latency_ms = row.get('http_latency_ms') or (json_payload.get('latency_s') if json_payload else None)
    http_user_agent = row.get('http_user_agent') or (json_payload.get('userAgent') if json_payload else None)
    http_remote_ip = row.get('http_remote_ip') or (json_payload.get('remoteIp') if json_payload else None)

    # Compute fingerprint from key fields
    service = row.get('service_name') or 'unknown'
    message = row.get('message') or ''
    key = f"{service}{http_method or ''}{http_url or ''}{http_status or ''}{message}"
    error_fingerprint = hashlib.md5(key.encode()).hexdigest()

    return LogEvent(
        event_timestamp=str(row.get('event_timestamp', '')),
        severity=row.get('severity', 'DEFAULT'),
        service_name=service,
        source_table=row.get('source_table', ''),
        message=message,
        json_payload=json_payload,
        trace_id=row.get('trace_id'),
        span_id=row.get('span_id'),
        http_url=http_url,
        http_method=http_method,
        http_status=http_status,
        http_latency_ms=http_latency_ms,
        http_user_agent=http_user_agent,
        http_remote_ip=http_remote_ip,
        error_fingerprint=error_fingerprint,
        stream_id=row.get('stream_id'),
        log_type=row.get('log_type'),
        resource_type=row.get('resource_type')
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
    Searches logs in the central logging dataset (master_logs).
    Args:
        query: Search term to find in log messages (searches message and json_payload)
        severity: Optional severity filter (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        service: Optional service filter
        hours: Number of hours to look back (default: 1)
        limit: Maximum number of logs to return (default: 20)
    """
    from src.config import config

    # Use the unified master_logs table
    project_id = config.PROJECT_ID_LOGS
    dataset_id = "central_logging_v1"
    table = f"{project_id}.{dataset_id}.master_logs"

    # Calculate partition date for efficient querying
    start_date = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    end_time = datetime.utcnow().isoformat()

    sql = f"""
    SELECT
        event_timestamp,
        severity,
        service_name,
        source_table,
        stream_id,
        message,
        json_payload,
        trace_id,
        span_id,
        http_url,
        http_method,
        http_status,
        log_type,
        resource_type
    FROM `{table}`
    WHERE log_date BETWEEN @start_date AND @end_date
      AND event_timestamp BETWEEN TIMESTAMP(@start_time) AND TIMESTAMP(@end_time)
    """

    params = {
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time
    }

    if severity:
        sql += " AND severity = @severity"
        params["severity"] = severity

    if service:
        sql += " AND service_name LIKE @service"
        params["service"] = f"%{service}%"

    if query:
        # Search in message and json_payload
        sql += " AND (LOWER(message) LIKE LOWER(@query_pattern) OR LOWER(CAST(json_payload AS STRING)) LIKE LOWER(@query_pattern))"
        params["query_pattern"] = f"%{query}%"

    sql += f" ORDER BY event_timestamp DESC LIMIT {limit}"

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
        try:
            from google.cloud import trace_v2
        except ModuleNotFoundError as e:
            return {"error": "Missing optional dependency 'google-cloud-trace'", "details": str(e)}

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
        try:
            from google.cloud import run_v2
        except ModuleNotFoundError as e:
            return {"error": "Missing optional dependency 'google-cloud-run'", "details": str(e)}

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


# ============================================
# ENHANCED SMART TOOLS
# ============================================

@tool
def analyze_logs(
    intent: str = "summary",
    timeframe: str = "24h",
    severity_filter: Optional[str] = None,
    service_filter: Optional[str] = None,
    include_patterns: bool = True
) -> Dict[str, Any]:
    """
    Smart log analysis tool that handles broad queries with intelligent defaults.
    Use this as the PRIMARY tool for log analysis - it handles vague requests well.

    Args:
        intent: What to analyze - "summary", "errors", "warnings", "all", "patterns", "anomalies"
        timeframe: Time period - "1h", "6h", "24h", "7d", "30d" (default: 24h)
        severity_filter: Optional - "ERROR", "WARNING", "INFO", etc. or "errors_only", "warnings_up"
        service_filter: Optional service name to filter
        include_patterns: Whether to group similar errors (default: True)

    Returns:
        Comprehensive analysis with stats, top issues, patterns, and recommendations
    """
    from src.config import config

    # Parse timeframe
    hours = 24
    timeframe_match = re.match(r'(\d+)([hdwm])', timeframe.lower())
    if timeframe_match:
        num, unit = int(timeframe_match.group(1)), timeframe_match.group(2)
        if unit == 'h': hours = num
        elif unit == 'd': hours = num * 24
        elif unit == 'w': hours = num * 24 * 7
        elif unit == 'm': hours = num * 24 * 30

    project_id = config.PROJECT_ID_LOGS
    dataset_id = "central_logging_v1"
    table = f"{project_id}.{dataset_id}.master_logs"

    # Calculate date range for partition pruning
    start_date = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    end_time = datetime.utcnow().isoformat()

    results = {
        "timeframe": f"Last {timeframe}",
        "analyzed_at": datetime.utcnow().isoformat(),
        "stats": {},
        "top_errors": [],
        "top_warnings": [],
        "services_affected": [],
        "patterns": [],
        "recommendations": []
    }

    # Common partition filter for all queries
    partition_filter = f"log_date BETWEEN '{start_date}' AND '{end_date}'"

    try:
        # 1. Get severity distribution
        stats_sql = f"""
        SELECT
            severity,
            COUNT(*) as count
        FROM `{table}`
        WHERE {partition_filter}
          AND event_timestamp BETWEEN TIMESTAMP(@start_time) AND TIMESTAMP(@end_time)
        GROUP BY severity
        ORDER BY count DESC
        """
        stats_res = run_bq_query(BQQueryInput(sql=stats_sql, params={"start_time": start_time, "end_time": end_time}))
        severity_counts = {row['severity']: row['count'] for row in stats_res.rows}
        results["stats"]["by_severity"] = severity_counts
        results["stats"]["total_logs"] = sum(severity_counts.values())
        results["stats"]["error_count"] = severity_counts.get('ERROR', 0) + severity_counts.get('CRITICAL', 0)
        results["stats"]["warning_count"] = severity_counts.get('WARNING', 0)

        # 2. Get service distribution
        service_sql = f"""
        SELECT
            service_name,
            COUNT(*) as total,
            COUNTIF(severity IN ('ERROR', 'CRITICAL')) as errors,
            COUNTIF(severity = 'WARNING') as warnings
        FROM `{table}`
        WHERE {partition_filter}
          AND event_timestamp BETWEEN TIMESTAMP(@start_time) AND TIMESTAMP(@end_time)
        GROUP BY service_name
        ORDER BY errors DESC, total DESC
        LIMIT 10
        """
        service_res = run_bq_query(BQQueryInput(sql=service_sql, params={"start_time": start_time, "end_time": end_time}))
        results["services_affected"] = [
            {"service": row['service_name'] or 'unknown', "total": row['total'], "errors": row['errors'], "warnings": row['warnings']}
            for row in service_res.rows
        ]

        # 3. Get top errors with details
        error_sql = f"""
        SELECT
            event_timestamp,
            severity,
            service_name,
            source_table,
            message,
            trace_id,
            span_id,
            resource_type
        FROM `{table}`
        WHERE {partition_filter}
          AND event_timestamp BETWEEN TIMESTAMP(@start_time) AND TIMESTAMP(@end_time)
          AND severity IN ('ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY')
        ORDER BY event_timestamp DESC
        LIMIT 25
        """
        error_res = run_bq_query(BQQueryInput(sql=error_sql, params={"start_time": start_time, "end_time": end_time}))
        results["top_errors"] = [
            {
                "timestamp": str(row['event_timestamp']),
                "severity": row['severity'],
                "service": row['service_name'] or 'unknown',
                "message": (row['message'] or '')[:300],
                "trace_id": row.get('trace_id'),
                "source": row['source_table'],
                "resource_type": row.get('resource_type')
            }
            for row in error_res.rows
        ]

        # 4. Get top warnings
        warning_sql = f"""
        SELECT
            event_timestamp,
            service_name,
            message
        FROM `{table}`
        WHERE {partition_filter}
          AND event_timestamp BETWEEN TIMESTAMP(@start_time) AND TIMESTAMP(@end_time)
          AND severity = 'WARNING'
        ORDER BY event_timestamp DESC
        LIMIT 15
        """
        warning_res = run_bq_query(BQQueryInput(sql=warning_sql, params={"start_time": start_time, "end_time": end_time}))
        results["top_warnings"] = [
            {
                "timestamp": str(row['event_timestamp']),
                "service": row['service_name'] or 'unknown',
                "message": (row['message'] or '')[:200]
            }
            for row in warning_res.rows
        ]

        # 5. Pattern detection - group similar errors
        if include_patterns and results["top_errors"]:
            pattern_sql = f"""
            SELECT
                service_name,
                REGEXP_EXTRACT(message, r'^([A-Za-z]+Error|Exception|[A-Z][a-z]+Exception):?') as error_type,
                COUNT(*) as occurrences,
                MIN(event_timestamp) as first_seen,
                MAX(event_timestamp) as last_seen
            FROM `{table}`
            WHERE {partition_filter}
              AND event_timestamp BETWEEN TIMESTAMP(@start_time) AND TIMESTAMP(@end_time)
              AND severity IN ('ERROR', 'CRITICAL')
              AND message IS NOT NULL
            GROUP BY service_name, error_type
            HAVING error_type IS NOT NULL
            ORDER BY occurrences DESC
            LIMIT 10
            """
            try:
                pattern_res = run_bq_query(BQQueryInput(sql=pattern_sql, params={"start_time": start_time, "end_time": end_time}))
                results["patterns"] = [
                    {
                        "service": row['service_name'] or 'unknown',
                        "error_type": row['error_type'],
                        "occurrences": row['occurrences'],
                        "first_seen": str(row['first_seen']),
                        "last_seen": str(row['last_seen'])
                    }
                    for row in pattern_res.rows
                ]
            except:
                pass  # Pattern detection is optional

        # 6. Generate recommendations
        if results["stats"]["error_count"] > 0:
            results["recommendations"].append({
                "priority": "high",
                "action": f"Investigate {results['stats']['error_count']} errors in the last {timeframe}",
                "details": "Focus on the top error patterns identified"
            })

        if results["services_affected"]:
            top_error_service = max(results["services_affected"], key=lambda x: x['errors'])
            if top_error_service['errors'] > 5:
                results["recommendations"].append({
                    "priority": "high",
                    "action": f"Review service '{top_error_service['service']}'",
                    "details": f"This service has {top_error_service['errors']} errors"
                })

        return results

    except Exception as e:
        return {"error": str(e), "partial_results": results}


@tool
def get_log_summary(hours: int = 24) -> Dict[str, Any]:
    """
    Quick summary of log activity. Use this for overview requests like
    "what's happening", "show me a summary", "overview of logs".

    Args:
        hours: Hours to look back (default: 24)

    Returns:
        Quick summary with counts and health status
    """
    from src.config import config

    project_id = config.PROJECT_ID_LOGS
    table = f"{project_id}.central_logging_v1.master_logs"

    # Calculate date range for partition pruning
    start_date = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    end_time = datetime.utcnow().isoformat()

    try:
        sql = f"""
        SELECT
            COUNT(*) as total_logs,
            COUNTIF(severity = 'ERROR') as errors,
            COUNTIF(severity = 'CRITICAL') as critical,
            COUNTIF(severity = 'WARNING') as warnings,
            COUNTIF(severity = 'INFO') as info,
            COUNT(DISTINCT service_name) as services_active,
            MIN(event_timestamp) as earliest,
            MAX(event_timestamp) as latest
        FROM `{table}`
        WHERE log_date BETWEEN '{start_date}' AND '{end_date}'
          AND event_timestamp BETWEEN TIMESTAMP(@start_time) AND TIMESTAMP(@end_time)
        """

        res = run_bq_query(BQQueryInput(sql=sql, params={"start_time": start_time, "end_time": end_time}))

        if res.rows:
            row = res.rows[0]
            total = row['total_logs']
            errors = row['errors'] + row['critical']
            error_rate = (errors / total * 100) if total > 0 else 0

            # Determine health status
            if error_rate > 5:
                health = "critical"
                health_msg = f"High error rate ({error_rate:.1f}%) - immediate attention needed"
            elif error_rate > 1:
                health = "warning"
                health_msg = f"Elevated error rate ({error_rate:.1f}%) - monitor closely"
            elif errors > 0:
                health = "fair"
                health_msg = f"Some errors present ({errors} total) - review recommended"
            else:
                health = "healthy"
                health_msg = "No errors detected in the timeframe"

            return {
                "timeframe": f"Last {hours} hours",
                "health_status": health,
                "health_message": health_msg,
                "total_logs": total,
                "errors": errors,
                "warnings": row['warnings'],
                "info": row['info'],
                "services_active": row['services_active'],
                "error_rate_percent": round(error_rate, 2),
                "time_range": {
                    "start": str(row['earliest']),
                    "end": str(row['latest'])
                }
            }

        return {"error": "No data found"}

    except Exception as e:
        return {"error": str(e)}


@tool
def find_related_logs(
    error_message: str,
    time_window_minutes: int = 30,
    include_context: bool = True
) -> Dict[str, Any]:
    """
    Find logs related to a specific error, including context before/after.
    Use this when investigating a specific error to find root cause.

    Args:
        error_message: The error message or keyword to search for
        time_window_minutes: Minutes before/after to search (default: 30)
        include_context: Include surrounding logs from same service/trace
    """
    from src.config import config

    project_id = config.PROJECT_ID_LOGS
    table = f"{project_id}.central_logging_v1.master_logs"

    # Use recent partition for error search
    recent_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        # First, find the error
        find_sql = f"""
        SELECT
            event_timestamp,
            severity,
            service_name,
            trace_id,
            span_id,
            message,
            source_table
        FROM `{table}`
        WHERE log_date >= '{recent_date}'
            AND LOWER(message) LIKE LOWER(@pattern)
            AND severity IN ('ERROR', 'CRITICAL', 'WARNING')
        ORDER BY event_timestamp DESC
        LIMIT 5
        """

        find_res = run_bq_query(BQQueryInput(
            sql=find_sql,
            params={"pattern": f"%{error_message}%"}
        ))

        if not find_res.rows:
            return {"error": "No matching errors found", "search_term": error_message}

        error_log = find_res.rows[0]
        error_time = error_log['event_timestamp']
        error_service = error_log['service_name']
        error_trace = error_log.get('trace_id')

        results = {
            "primary_error": {
                "timestamp": str(error_time),
                "severity": error_log['severity'],
                "service": error_service,
                "message": error_log['message'],
                "trace_id": error_trace
            },
            "related_logs": [],
            "trace_logs": [],
            "timeline": []
        }

        if include_context:
            # Get logs from same service around the same time
            context_sql = f"""
            SELECT
                event_timestamp,
                severity,
                service_name,
                message,
                trace_id
            FROM `{table}`
            WHERE log_date >= '{recent_date}'
                AND service_name = @service
                AND event_timestamp BETWEEN TIMESTAMP_SUB(@error_time, INTERVAL {time_window_minutes} MINUTE)
                                         AND TIMESTAMP_ADD(@error_time, INTERVAL {time_window_minutes} MINUTE)
            ORDER BY event_timestamp
            LIMIT 50
            """

            context_res = run_bq_query(BQQueryInput(
                sql=context_sql,
                params={"service": error_service, "error_time": str(error_time)}
            ))

            results["related_logs"] = [
                {
                    "timestamp": str(row['event_timestamp']),
                    "severity": row['severity'],
                    "message": (row['message'] or '')[:200],
                    "is_error": row['event_timestamp'] == error_time
                }
                for row in context_res.rows
            ]

            # If there's a trace, get all logs in that trace
            if error_trace:
                trace_sql = f"""
                SELECT
                    event_timestamp,
                    severity,
                    service_name,
                    span_id,
                    message
                FROM `{table}`
                WHERE log_date >= '{recent_date}'
                    AND trace_id = @trace
                ORDER BY event_timestamp
                LIMIT 30
                """

                trace_res = run_bq_query(BQQueryInput(
                    sql=trace_sql,
                    params={"trace": error_trace}
                ))

                results["trace_logs"] = [
                    {
                        "timestamp": str(row['event_timestamp']),
                        "severity": row['severity'],
                        "service": row['service_name'],
                        "span_id": row['span_id'],
                        "message": (row['message'] or '')[:200]
                    }
                    for row in trace_res.rows
                ]

        return results

    except Exception as e:
        return {"error": str(e)}


@tool
def suggest_queries(context: str = "") -> Dict[str, Any]:
    """
    Suggest relevant queries based on current context or common use cases.
    Use this when user asks "what can you do" or needs guidance.

    Args:
        context: Optional context about what user is investigating

    Returns:
        List of suggested queries with explanations
    """
    suggestions = {
        "quick_actions": [
            {
                "query": "Show me errors from the last hour",
                "description": "View recent errors for immediate issues",
                "tool": "analyze_logs",
                "params": {"intent": "errors", "timeframe": "1h"}
            },
            {
                "query": "Give me a health summary",
                "description": "Quick overview of system health",
                "tool": "get_log_summary",
                "params": {"hours": 24}
            },
            {
                "query": "What services have the most errors?",
                "description": "Identify problematic services",
                "tool": "analyze_logs",
                "params": {"intent": "summary", "include_patterns": True}
            },
            {
                "query": "Show me warning trends",
                "description": "View warnings that might become errors",
                "tool": "analyze_logs",
                "params": {"intent": "warnings", "timeframe": "24h"}
            }
        ],
        "investigation_queries": [
            {
                "query": "Find logs related to [error message]",
                "description": "Deep dive into a specific error",
                "tool": "find_related_logs"
            },
            {
                "query": "Check health of [service name]",
                "description": "Service-specific health check",
                "tool": "service_health_tool"
            },
            {
                "query": "Trace [trace_id]",
                "description": "Follow a request through the system",
                "tool": "trace_lookup_tool"
            }
        ],
        "advanced_queries": [
            {
                "query": "Run custom BigQuery: SELECT ...",
                "description": "Execute custom SQL queries",
                "tool": "bq_query_tool"
            },
            {
                "query": "Create a view for [analysis]",
                "description": "Save a query as a reusable view",
                "tool": "create_view_tool"
            }
        ]
    }

    # Add context-specific suggestions if provided
    if "error" in context.lower():
        suggestions["recommended"] = suggestions["quick_actions"][0:2]
    elif "slow" in context.lower() or "latency" in context.lower():
        suggestions["recommended"] = [
            {
                "query": "Find slow requests",
                "description": "Look for high latency logs",
                "tool": "search_logs_tool",
                "params": {"query": "latency", "hours": 6}
            }
        ]

    return suggestions


# ============================================
# SEMANTIC SEARCH TOOLS (Phase 2)
# ============================================

@tool
def semantic_search_logs(
    query: str,
    top_k: int = 10,
    severity: Optional[str] = None,
    service: Optional[str] = None,
    score_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Search logs using semantic similarity (vector search).
    Use this for natural language queries like "authentication failures",
    "slow database queries", "memory issues", etc.

    This is more powerful than keyword search for finding related logs
    that may not contain exact keyword matches.

    Args:
        query: Natural language description of what you're looking for
        top_k: Number of results to return (default: 10)
        severity: Optional severity filter (ERROR, WARNING, INFO, etc.)
        service: Optional service name filter
        score_threshold: Minimum similarity score 0-1 (default: 0.5)

    Returns:
        List of semantically similar log entries with scores
    """
    try:
        from src.services.vector_service import vector_service
        from src.config import config

        if not vector_service.enabled:
            return {
                "error": "Vector search is not enabled",
                "fallback": "Use search_logs_tool for keyword-based search instead"
            }

        project_id = config.PROJECT_ID_LOGS

        results = vector_service.semantic_search_logs(
            query=query,
            project_id=project_id,
            top_k=top_k,
            severity=severity,
            service=service,
        )

        if not results:
            return {
                "results": [],
                "message": "No semantically similar logs found. Try a different query or use keyword search."
            }

        return {
            "query": query,
            "results": [
                {
                    "score": round(r.score, 3),
                    "content": r.content,
                    "severity": r.metadata.get("severity"),
                    "service": r.metadata.get("service"),
                    "timestamp": r.timestamp,
                    "id": r.id
                }
                for r in results
            ],
            "total_found": len(results)
        }

    except ImportError:
        return {
            "error": "Vector service not available",
            "fallback": "Use search_logs_tool for keyword-based search"
        }
    except Exception as e:
        return {"error": str(e)}


@tool
def find_similar_logs(
    log_text: str,
    top_k: int = 5,
    exclude_self: bool = True
) -> Dict[str, Any]:
    """
    Find logs similar to a given log entry.
    Use this to find patterns, related errors, or recurring issues.

    Args:
        log_text: The log message to find similar entries for
        top_k: Number of similar logs to return (default: 5)
        exclude_self: Exclude exact matches (default: True)

    Returns:
        List of similar log entries with similarity scores
    """
    try:
        from src.services.vector_service import vector_service
        from src.config import config

        if not vector_service.enabled:
            return {
                "error": "Vector search is not enabled",
                "message": "Similar log search requires vector embeddings"
            }

        project_id = config.PROJECT_ID_LOGS

        results = vector_service.get_similar_logs(
            log_text=log_text,
            project_id=project_id,
            top_k=top_k,
            exclude_self=exclude_self,
        )

        if not results:
            return {
                "results": [],
                "message": "No similar logs found in the vector database"
            }

        return {
            "source_log": log_text[:200] + "..." if len(log_text) > 200 else log_text,
            "similar_logs": [
                {
                    "similarity_score": round(r.score, 3),
                    "content": r.content,
                    "severity": r.metadata.get("severity"),
                    "service": r.metadata.get("service"),
                    "timestamp": r.timestamp
                }
                for r in results
            ],
            "total_found": len(results)
        }

    except ImportError:
        return {"error": "Vector service not available"}
    except Exception as e:
        return {"error": str(e)}
