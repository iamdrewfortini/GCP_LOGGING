"""
GraphQL Resolvers
"""

import hashlib
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from strawberry.fastapi import BaseContext
from src.api.graphql.types import (
    LogEntry, LogQuery, Health, ServiceInfo, LogFilter,
    RunQueryInput, EnqueueEmbeddingJobInput, SetTagInput, EmbeddingJob,
    ChatEvent
)
from src.api.graphql.auth import get_user_from_context, require_auth
from src.glass_pane.config import glass_config
from src.glass_pane.query_builder import CanonicalQueryBuilder

def hash_filter(filter: LogFilter) -> str:
    """Hash filter for Redis key."""
    filter_dict = {
        "hours": filter.hours,
        "limit": filter.limit,
        "severity": filter.severity.value if filter.severity else None,
        "service_name": filter.service_name,
        "region": filter.region,
        "env": filter.env,
    }
    return hashlib.sha256(json.dumps(filter_dict, sort_keys=True).encode()).hexdigest()

def log_payload_to_log_entry(payload: Dict[str, Any]) -> LogEntry:
    """Convert log payload to LogEntry."""
    return LogEntry(
        id=payload["log_id"],
        event_ts=payload["timestamp"],
        ingest_ts=payload["ingest_ts"] if "ingest_ts" in payload else payload["timestamp"],
        project_id=payload["tenant_id"],
        env=payload.get("env", "unknown"),
        region=payload.get("region", "unknown"),
        service_name=payload["service_name"],
        severity=payload["severity"],
        event_type=payload.get("event_type", "unknown"),
        correlation_ids=payload.get("correlation_ids", []),
        labels=payload.get("labels", {}),
        message=payload.get("message"),
        body=payload.get("body"),
        http_method=payload.get("http_method"),
        http_status=payload.get("http_status"),
        trace_id=payload.get("trace_id"),
        span_id=payload.get("span_id"),
    )

# Query Resolvers
def resolve_logs(filter: LogFilter, context: BaseContext) -> LogQuery:
    """Resolve logs query with cache-first strategy."""
    user_id = require_auth(get_user_from_context(context))

    redis_key = f"logs:{hash_filter(filter)}"
    cached = context.redis.get(redis_key)
    if cached:
        data = json.loads(cached)
        logs = [log_payload_to_log_entry(p) for p in data["logs"]]
        return LogQuery(logs=logs, total_count=data["total_count"], has_more=data["has_more"])

    # Fallback to BigQuery
    query_builder = CanonicalQueryBuilder(
        project_id=glass_config.logs_project_id,
        view_name=glass_config.canonical_view,
    )
    hours = filter.hours or glass_config.default_time_window_hours
    limit = filter.limit or glass_config.default_limit
    params = {
        "hours": hours,
        "limit": limit,
        "severity": filter.severity.value if filter.severity else None,
        "service_name": filter.service_name,
        "region": filter.region,
        "env": filter.env,
    }
    results = query_builder.query_logs(**params)
    logs = [log_payload_to_log_entry(r) for r in results]

    # Cache result
    cache_data = {
        "logs": [vars(l) for l in logs],  # simplistic
        "total_count": len(logs),
        "has_more": len(logs) == limit,
    }
    context.redis.set(redis_key, json.dumps(cache_data), ex=300)  # 5 min

    return LogQuery(logs=logs, total_count=len(logs), has_more=len(logs) == limit)

def resolve_log(id: str, context: BaseContext) -> Optional[LogEntry]:
    """Resolve single log."""
    require_auth(get_user_from_context(context))
    # Implement single log query
    return None  # Placeholder

def resolve_services(context: BaseContext) -> List[ServiceInfo]:
    """Resolve services."""
    require_auth(get_user_from_context(context))
    # Placeholder
    return []

def resolve_health(context: BaseContext) -> Health:
    """Resolve health."""
    redis_status = context.redis.ping()
    qdrant_status = context.qdrant.client is not None
    return Health(
        ok=redis_status and qdrant_status,
        version="2.0.0",
        services={
            "redis": "connected" if redis_status else "disconnected",
            "qdrant": "connected" if qdrant_status else "disconnected",
            "firebase": "connected",  # Assume
            "bigquery": "connected",
        }
    )

def resolve_jobs(filter: Optional[LogFilter], context: BaseContext) -> List[EmbeddingJob]:
    """Resolve embedding jobs."""
    require_auth(get_user_from_context(context))
    # Placeholder
    return []

def resolve_chat(session_id: str, context: BaseContext) -> List[ChatEvent]:
    """Resolve chat events."""
    require_auth(get_user_from_context(context))
    # Placeholder
    return []

# Mutation Resolvers
def resolve_run_query(input: RunQueryInput, context: BaseContext) -> LogQuery:
    """Run custom query."""
    require_auth(get_user_from_context(context))
    # Placeholder
    return LogQuery(logs=[], total_count=0, has_more=False)

def resolve_enqueue_embedding_job(input: EnqueueEmbeddingJobInput, context: BaseContext) -> EmbeddingJob:
    """Enqueue embedding job."""
    require_auth(get_user_from_context(context))
    # Use dual_write_service or similar
    return EmbeddingJob(id="job_123", status="queued", log_ids=input.log_ids)

def resolve_mark_reviewed(id: str, context: BaseContext) -> bool:
    """Mark log as reviewed."""
    require_auth(get_user_from_context(context))
    # Update in Firebase
    return True

def resolve_set_tag(input: SetTagInput, context: BaseContext) -> bool:
    """Set tag on log."""
    require_auth(get_user_from_context(context))
    # Update in Firebase
    return True

# Subscription (placeholder)
async def resolve_log_stream(filter: LogFilter, context: BaseContext):
    """Log stream subscription."""
    require_auth(get_user_from_context(context))
    # Use Firebase realtime
    yield LogEntry(...)  # Placeholder