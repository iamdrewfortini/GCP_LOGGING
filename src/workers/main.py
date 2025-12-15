import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from src.services.redis_service import redis_service
from src.services.qdrant_service import qdrant_service
from src.services.embedding_service import embedding_service
from qdrant_client.http import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

QUEUE_REALTIME = "q:embeddings:realtime"
QUEUE_LOGS = "q:embeddings:logs"

async def process_task(task: Dict[str, Any]):
    """
    Dispatcher for different task types.
    """
    try:
        task_type = task.get("type", "chat_message") # Default to chat for backward compat
        
        if task_type == "chat_message":
            await process_chat_embedding(task)
        elif task_type == "log_entry":
            await process_log_embedding(task)
        else:
            logger.warning(f"Unknown task type: {task_type}")

    except Exception as e:
        logger.error(f"Error processing task: {e}")

async def process_chat_embedding(task: Dict[str, Any]):
    session_id = task.get("session_id")
    project_id = task.get("project_id", "default")
    role = task.get("role")
    content = task.get("content")
    
    if not all([session_id, role, content]):
        logger.error(f"Invalid chat task format: {task}")
        return

    logger.info(f"Processing chat embedding for session {session_id}...")
    embedding = embedding_service.get_embedding(content)
    
    # Upsert to conversation_history via service wrapper
    qdrant_service.upsert_memory(
        session_id=session_id,
        project_id=project_id,
        role=role,
        content=content,
        embedding=embedding
    )

async def process_log_embedding(task: Dict[str, Any]):
    """
    Process a log entry from BigQuery.
    """
    project_id = task.get("project_id")
    content = task.get("content")
    log_id = task.get("log_id") or str(uuid.uuid4())
    timestamp = task.get("timestamp")
    service = task.get("service")
    severity = task.get("severity")

    if not content:
        return

    # Generate embedding for the log message content
    embedding = embedding_service.get_embedding(content)

    # Direct upsert to 'app_logs' collection (bypassing specific helper for now or adding one)
    # Ideally, we add upsert_log to QdrantService, but direct client use here is fine for the worker pattern
    if qdrant_service.client:
        qdrant_service.client.upsert(
            collection_name="app_logs",
            points=[
                models.PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, str(log_id))), # Deterministic ID
                    vector=embedding,
                    payload={
                        "group_id": project_id,
                        "service": service,
                        "severity": severity,
                        "timestamp_iso": timestamp,
                        "content": content
                    }
                )
            ]
        )
        logger.info(f"Indexed log {log_id}")

async def worker_loop():
    logger.info(f"Worker started. Listening on {QUEUE_REALTIME} and {QUEUE_LOGS}...")
    while True:
        # Check Realtime Queue (Higher Priority)
        task_data = redis_service.dequeue(QUEUE_REALTIME, timeout=1)
        if task_data:
            # tag it if missing
            if "type" not in task_data: task_data["type"] = "chat_message"
            await process_task(task_data)
            continue

        # Check Logs Queue (Lower Priority)
        task_data = redis_service.dequeue(QUEUE_LOGS, timeout=1)
        if task_data:
            await process_task(task_data)
            continue
        
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    import uuid # Imported inside for scope if needed, but added to top level imports is better
    # Ensure connections
    if not redis_service.ping():
        logger.error("Could not connect to Redis. Exiting.")
        exit(1)
        
    asyncio.run(worker_loop())
