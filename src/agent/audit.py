import uuid
import logging
import datetime
from typing import Dict, Any, Optional

# We can re-use the redis service to enqueue audit logs to the same 'logs' queue
# so they get indexed into Qdrant 'app_logs' collection.
from src.services.redis_service import redis_service

logger = logging.getLogger("audit")

def log_tool_use(phase: str, tool_id: str, payload: Dict[str, Any], audit_id: Optional[str] = None) -> str:
    """
    Logs tool execution lifecycle events.
    Phase: 'start', 'end', 'error'
    """
    if not audit_id:
        audit_id = str(uuid.uuid4())
        
    entry = {
        "type": "log_entry", # Reuse the worker's log handler
        "project_id": "audit-system",
        "service": "agent-tool-executor",
        "severity": "INFO" if phase != "error" else "ERROR",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "content": f"Tool: {tool_id} | Phase: {phase} | ID: {audit_id} | Payload: {payload}",
        "log_id": str(uuid.uuid4())
    }
    
    # Push to Redis for async indexing into Qdrant
    redis_service.enqueue("q:embeddings:logs", entry)
    
    # Also log to standard out for Cloud Logging
    logger.info(f"AUDIT [{phase}] {tool_id} ({audit_id}): {payload}")
    
    return audit_id
