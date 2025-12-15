"""Analytics Worker Cloud Function.

This function consumes chat events from Pub/Sub and writes them to BigQuery
for long-term analytics and cold storage.

Additionally, it triggers embedding generation for log-related content
by publishing to the embedding-jobs topic (Phase 2).

Triggered by: chat-events Pub/Sub topic
Destination: chat_analytics.chat_events and chat_analytics.tool_invocations

Deployment:
    gcloud functions deploy analytics-worker \
        --trigger-topic=chat-events \
        --runtime=python312 \
        --entry-point=process_chat_event \
        --source=functions/analytics-worker \
        --region=us-central1 \
        --set-env-vars=PROJECT_ID=diatonic-ai-gcp,DATASET_ID=chat_analytics,ENABLE_EMBEDDINGS=true
"""

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from google.cloud import bigquery
from google.cloud import pubsub_v1

# Configuration
PROJECT_ID = os.getenv("PROJECT_ID", "diatonic-ai-gcp")
DATASET_ID = os.getenv("DATASET_ID", "chat_analytics")
CHAT_EVENTS_TABLE = "chat_events"
TOOL_INVOCATIONS_TABLE = "tool_invocations"
EMBEDDING_JOBS_TOPIC = os.getenv("EMBEDDING_JOBS_TOPIC", "embedding-jobs")

# Feature flags
ENABLE_EMBEDDINGS = os.getenv("ENABLE_EMBEDDINGS", "true").lower() == "true"

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lazy BigQuery client
_bq_client: Optional[bigquery.Client] = None
_publisher: Optional[pubsub_v1.PublisherClient] = None


def get_bq_client() -> bigquery.Client:
    """Get or create BigQuery client."""
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=PROJECT_ID)
    return _bq_client


def get_publisher() -> pubsub_v1.PublisherClient:
    """Get or create Pub/Sub publisher client."""
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def trigger_embedding(
    text: str,
    project_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Trigger embedding generation for text content.

    Publishes a message to the embedding-jobs topic to generate
    and store an embedding for the given text.

    Args:
        text: Text content to embed
        project_id: Project ID for tenant isolation
        metadata: Additional metadata (session_id, user_id, etc.)

    Returns:
        True if message published successfully
    """
    if not ENABLE_EMBEDDINGS:
        logger.debug("Embeddings disabled via feature flag")
        return False

    if not text or not text.strip():
        return False

    try:
        publisher = get_publisher()
        topic_path = publisher.topic_path(PROJECT_ID, EMBEDDING_JOBS_TOPIC)

        message = {
            "action": "embed_log",
            "project_id": project_id,
            "text": text,
            "metadata": metadata or {},
        }

        data = json.dumps(message).encode("utf-8")
        future = publisher.publish(topic_path, data)
        message_id = future.result(timeout=10)

        logger.info(f"Published embedding job: {message_id}")
        return True

    except Exception as e:
        logger.warning(f"Failed to trigger embedding (non-fatal): {e}")
        return False


def process_chat_event(event: Dict[str, Any], context) -> None:
    """Process a chat event from Pub/Sub and write to BigQuery.

    This is the Cloud Function entry point.

    Args:
        event: Pub/Sub event containing base64-encoded message data
        context: Cloud Function context (unused)
    """
    try:
        # Decode Pub/Sub message
        if "data" in event:
            message_data = base64.b64decode(event["data"]).decode("utf-8")
            payload = json.loads(message_data)
        else:
            logger.warning("No data in event")
            return

        # Get event type from attributes
        attributes = event.get("attributes", {})
        event_type = attributes.get("event_type", payload.get("event_type", "unknown"))

        logger.info(f"Processing event type: {event_type}")

        # Route to appropriate handler
        if event_type == "tool_invocation":
            write_tool_invocation(payload)
        else:
            write_chat_event(payload)

        logger.info(f"Successfully processed event: {payload.get('event_id', 'unknown')}")

    except Exception as e:
        logger.error(f"Error processing chat event: {e}")
        # Re-raise to trigger Pub/Sub retry
        raise


def write_chat_event(payload: Dict[str, Any]) -> None:
    """Write a chat event to BigQuery.

    Also triggers embedding generation for user messages (Phase 2).

    Args:
        payload: Chat event payload
    """
    client = get_bq_client()
    table_id = f"{PROJECT_ID}.{DATASET_ID}.{CHAT_EVENTS_TABLE}"

    # Transform payload to match BigQuery schema
    row = {
        "event_id": payload.get("event_id"),
        "event_timestamp": parse_timestamp(payload.get("timestamp")),
        "session_id": payload.get("session_id"),
        "user_id": payload.get("user_id"),
        "event_type": payload.get("event_type"),
        "role": payload.get("role"),
        "content": json.dumps({"text": payload.get("content")}) if payload.get("content") else None,
        "metadata": json.dumps(payload.get("metadata")) if payload.get("metadata") else None,
        "token_usage": transform_token_usage(payload.get("token_usage")),
        "client_info": json.dumps(payload.get("client_info")) if payload.get("client_info") else None,
    }

    # Remove None values for cleaner insert
    row = {k: v for k, v in row.items() if v is not None}

    # Insert row
    errors = client.insert_rows_json(table_id, [row])
    if errors:
        logger.error(f"BigQuery insert errors: {errors}")
        raise Exception(f"BigQuery insert failed: {errors}")

    logger.info(f"Wrote chat event to BigQuery: {row.get('event_id')}")

    # Phase 2: Trigger embedding for user messages
    # Only embed user messages to enable semantic search
    if payload.get("role") == "user" and payload.get("content"):
        trigger_embedding(
            text=payload.get("content"),
            project_id=PROJECT_ID,
            metadata={
                "source_type": "chat_message",
                "session_id": payload.get("session_id"),
                "user_id": payload.get("user_id"),
                "event_id": payload.get("event_id"),
            },
        )


def write_tool_invocation(payload: Dict[str, Any]) -> None:
    """Write a tool invocation to BigQuery.

    Args:
        payload: Tool invocation payload
    """
    client = get_bq_client()
    table_id = f"{PROJECT_ID}.{DATASET_ID}.{TOOL_INVOCATIONS_TABLE}"

    # Transform payload to match BigQuery schema
    row = {
        "invocation_id": payload.get("invocation_id"),
        "session_id": payload.get("session_id"),
        "user_id": payload.get("user_id"),
        "tool_name": payload.get("tool_name"),
        "started_at": parse_timestamp(payload.get("started_at")),
        "ended_at": parse_timestamp(payload.get("ended_at")) if payload.get("ended_at") else None,
        "duration_ms": payload.get("duration_ms"),
        "status": payload.get("status"),
        "input_args": json.dumps(payload.get("input_args")) if payload.get("input_args") else None,
        "output_summary": payload.get("output_summary"),
        "error_message": payload.get("error_message"),
        "bytes_billed": payload.get("bytes_billed"),
        "tokens_used": payload.get("tokens_used"),
    }

    # Remove None values
    row = {k: v for k, v in row.items() if v is not None}

    # Insert row
    errors = client.insert_rows_json(table_id, [row])
    if errors:
        logger.error(f"BigQuery insert errors: {errors}")
        raise Exception(f"BigQuery insert failed: {errors}")

    logger.info(f"Wrote tool invocation to BigQuery: {row.get('invocation_id')}")


def parse_timestamp(timestamp_str: Optional[str]) -> Optional[str]:
    """Parse and format timestamp for BigQuery.

    BigQuery expects TIMESTAMP in ISO 8601 format.

    Args:
        timestamp_str: ISO 8601 timestamp string

    Returns:
        Formatted timestamp or None
    """
    if not timestamp_str:
        return None

    try:
        # Handle various ISO 8601 formats
        ts = timestamp_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        return dt.isoformat()
    except Exception as e:
        logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
        return timestamp_str


def transform_token_usage(token_usage: Optional[Dict[str, int]]) -> Optional[Dict[str, int]]:
    """Transform token usage for BigQuery RECORD type.

    Args:
        token_usage: Token usage dictionary

    Returns:
        Transformed dictionary or None
    """
    if not token_usage:
        return None

    return {
        "prompt_tokens": token_usage.get("prompt_tokens", 0),
        "completion_tokens": token_usage.get("completion_tokens", 0),
        "total_tokens": token_usage.get("total_tokens", 0),
    }


# For local testing
if __name__ == "__main__":
    # Test event
    test_event = {
        "data": base64.b64encode(json.dumps({
            "event_id": "test-123",
            "event_type": "message_sent",
            "session_id": "session-456",
            "user_id": "user-789",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": "user",
            "content": "Test message",
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 0,
                "total_tokens": 10,
            },
        }).encode()).decode(),
        "attributes": {
            "event_type": "message_sent",
        },
    }

    print("Testing with event:")
    print(json.dumps(test_event, indent=2))

    # Uncomment to run test (requires BQ access)
    # process_chat_event(test_event, None)
