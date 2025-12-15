"""Dual-write service for hot (Firestore) and cold (BigQuery) storage.

This service handles writing chat events to:
1. Firestore (hot path) - for real-time UI sync
2. Pub/Sub (async) - for BigQuery cold storage via Cloud Function

The design ensures Firestore writes are synchronous while Pub/Sub
publishes are async and non-blocking.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# Feature flags
ENABLE_DUAL_WRITE = os.getenv("ENABLE_DUAL_WRITE", "true").lower() == "true"
ENABLE_FIRESTORE_WRITE = os.getenv("ENABLE_FIRESTORE_WRITE", "true").lower() == "true"
ENABLE_BQ_WRITE = os.getenv("ENABLE_BQ_WRITE", "true").lower() == "true"
ENABLE_PUBSUB = os.getenv("ENABLE_PUBSUB", "true").lower() == "true"

# Pub/Sub configuration
PUBSUB_PROJECT = os.getenv("PROJECT_ID", "diatonic-ai-gcp")
PUBSUB_TOPIC = os.getenv("CHAT_EVENTS_TOPIC", "chat-events")


@dataclass
class ChatEvent:
    """Chat event data model for dual-write.

    This represents a single event in the chat conversation,
    suitable for both Firestore and BigQuery storage.
    """
    event_id: str
    event_type: str  # message_sent, tool_start, tool_end, error
    session_id: str
    user_id: str
    timestamp: str  # ISO 8601 format
    role: Optional[str] = None  # user, assistant, system, tool
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    token_usage: Optional[Dict[str, int]] = None
    client_info: Optional[Dict[str, str]] = None

    @classmethod
    def create_message_event(
        cls,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        token_usage: Optional[Dict[str, int]] = None,
    ) -> "ChatEvent":
        """Create a message_sent event."""
        return cls(
            event_id=str(uuid.uuid4()),
            event_type="message_sent",
            session_id=session_id,
            user_id=user_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            role=role,
            content=content,
            metadata=metadata,
            token_usage=token_usage,
        )

    @classmethod
    def create_tool_start_event(
        cls,
        session_id: str,
        user_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> "ChatEvent":
        """Create a tool_start event."""
        return cls(
            event_id=str(uuid.uuid4()),
            event_type="tool_start",
            session_id=session_id,
            user_id=user_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            role="tool",
            metadata={
                "tool_name": tool_name,
                "tool_input": tool_input,
            },
        )

    @classmethod
    def create_tool_end_event(
        cls,
        session_id: str,
        user_id: str,
        tool_name: str,
        status: str,
        duration_ms: Optional[int] = None,
        output_summary: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> "ChatEvent":
        """Create a tool_end event."""
        return cls(
            event_id=str(uuid.uuid4()),
            event_type="tool_end",
            session_id=session_id,
            user_id=user_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            role="tool",
            metadata={
                "tool_name": tool_name,
                "status": status,
                "duration_ms": duration_ms,
                "output_summary": output_summary,
                "error_message": error_message,
            },
        )

    @classmethod
    def create_error_event(
        cls,
        session_id: str,
        user_id: str,
        error_message: str,
        error_type: Optional[str] = None,
    ) -> "ChatEvent":
        """Create an error event."""
        return cls(
            event_id=str(uuid.uuid4()),
            event_type="error",
            session_id=session_id,
            user_id=user_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "error_message": error_message,
                "error_type": error_type,
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class ToolInvocation:
    """Tool invocation record for analytics.

    This represents detailed metrics for a single tool execution.
    """
    invocation_id: str
    session_id: str
    user_id: str
    tool_name: str
    started_at: str
    ended_at: Optional[str] = None
    duration_ms: Optional[int] = None
    status: str = "running"  # running, success, failure
    input_args: Optional[Dict[str, Any]] = None
    output_summary: Optional[str] = None
    error_message: Optional[str] = None
    bytes_billed: Optional[int] = None
    tokens_used: Optional[int] = None

    @classmethod
    def start(
        cls,
        session_id: str,
        user_id: str,
        tool_name: str,
        input_args: Optional[Dict[str, Any]] = None,
    ) -> "ToolInvocation":
        """Create a new tool invocation in running state."""
        return cls(
            invocation_id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            tool_name=tool_name,
            started_at=datetime.now(timezone.utc).isoformat(),
            status="running",
            input_args=input_args,
        )

    def complete(
        self,
        output_summary: Optional[str] = None,
        bytes_billed: Optional[int] = None,
        tokens_used: Optional[int] = None,
    ) -> None:
        """Mark invocation as completed successfully."""
        self.ended_at = datetime.now(timezone.utc).isoformat()
        self.status = "success"
        self.output_summary = output_summary
        self.bytes_billed = bytes_billed
        self.tokens_used = tokens_used
        self._calculate_duration()

    def fail(self, error_message: str) -> None:
        """Mark invocation as failed."""
        self.ended_at = datetime.now(timezone.utc).isoformat()
        self.status = "failure"
        self.error_message = error_message
        self._calculate_duration()

    def _calculate_duration(self) -> None:
        """Calculate duration from started_at and ended_at."""
        if self.started_at and self.ended_at:
            start = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.ended_at.replace("Z", "+00:00"))
            self.duration_ms = int((end - start).total_seconds() * 1000)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class DualWriteService:
    """Service for dual-write to hot (Firestore) and cold (BigQuery) storage.

    This service ensures:
    - Firestore writes are synchronous for real-time UI
    - Pub/Sub publishes are async and non-blocking
    - Errors in cold path don't affect hot path
    """

    _instance: Optional["DualWriteService"] = None
    _publisher = None
    _topic_path: Optional[str] = None

    def __new__(cls) -> "DualWriteService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        pass

    def _get_publisher(self):
        """Lazy initialization of Pub/Sub publisher."""
        if not ENABLE_PUBSUB:
            return None

        if self._publisher is None:
            try:
                from google.cloud import pubsub_v1
                self._publisher = pubsub_v1.PublisherClient()
                self._topic_path = self._publisher.topic_path(PUBSUB_PROJECT, PUBSUB_TOPIC)
                logger.info(f"Pub/Sub publisher initialized for topic: {self._topic_path}")
            except Exception as e:
                logger.warning(f"Failed to initialize Pub/Sub publisher: {e}")
                return None
        return self._publisher

    @property
    def enabled(self) -> bool:
        """Check if dual-write is enabled."""
        return ENABLE_DUAL_WRITE

    @property
    def firestore_enabled(self) -> bool:
        """Check if Firestore writes are enabled."""
        return ENABLE_FIRESTORE_WRITE

    @property
    def bq_enabled(self) -> bool:
        """Check if BigQuery writes are enabled."""
        return ENABLE_BQ_WRITE

    def write_event(
        self,
        event: ChatEvent,
        firebase_service=None,
    ) -> bool:
        """Write a chat event to both hot and cold storage.

        Args:
            event: The chat event to write
            firebase_service: Optional Firebase service instance

        Returns:
            True if hot path succeeded, False otherwise
        """
        if not self.enabled:
            logger.debug("Dual-write disabled, skipping")
            return True

        hot_success = True
        cold_success = True

        # Hot path: Firestore (synchronous)
        if self.firestore_enabled and firebase_service and firebase_service.enabled:
            try:
                if event.event_type == "message_sent":
                    firebase_service.add_message(
                        session_id=event.session_id,
                        role=event.role or "unknown",
                        content=event.content or "",
                        metadata={
                            "event_id": event.event_id,
                            **(event.metadata or {}),
                            **({"token_usage": event.token_usage} if event.token_usage else {}),
                        },
                    )
                logger.debug(f"Hot path write successful for event {event.event_id}")
            except Exception as e:
                logger.error(f"Hot path write failed: {e}")
                hot_success = False

        # Cold path: Pub/Sub (async, non-blocking)
        if self.bq_enabled:
            try:
                self._publish_to_pubsub(event)
                logger.debug(f"Cold path publish successful for event {event.event_id}")
            except Exception as e:
                logger.error(f"Cold path publish failed: {e}")
                cold_success = False

        return hot_success

    def write_tool_invocation(
        self,
        invocation: ToolInvocation,
    ) -> bool:
        """Write a tool invocation record to cold storage.

        Tool invocations are only written to BigQuery for analytics,
        not to Firestore (which stores the tool events in chat history).

        Args:
            invocation: The tool invocation record

        Returns:
            True if publish succeeded, False otherwise
        """
        if not self.enabled or not self.bq_enabled:
            return True

        try:
            self._publish_tool_invocation(invocation)
            return True
        except Exception as e:
            logger.error(f"Tool invocation publish failed: {e}")
            return False

    def _publish_to_pubsub(self, event: ChatEvent) -> None:
        """Publish event to Pub/Sub for BigQuery ingestion.

        This is fire-and-forget - we don't wait for acknowledgment.
        """
        publisher = self._get_publisher()
        if not publisher:
            logger.debug("Pub/Sub publisher not available, skipping publish")
            return

        try:
            message_data = event.to_json().encode("utf-8")
            # Fire and forget - don't wait for result
            future = publisher.publish(
                self._topic_path,
                message_data,
                event_type=event.event_type,
                session_id=event.session_id,
            )
            # Optional: Add callback for monitoring
            future.add_done_callback(self._pubsub_callback)
        except Exception as e:
            logger.error(f"Pub/Sub publish error: {e}")
            raise

    def _publish_tool_invocation(self, invocation: ToolInvocation) -> None:
        """Publish tool invocation to Pub/Sub."""
        publisher = self._get_publisher()
        if not publisher:
            return

        try:
            message_data = json.dumps(invocation.to_dict()).encode("utf-8")
            future = publisher.publish(
                self._topic_path,
                message_data,
                event_type="tool_invocation",
                session_id=invocation.session_id,
            )
            future.add_done_callback(self._pubsub_callback)
        except Exception as e:
            logger.error(f"Tool invocation publish error: {e}")
            raise

    def _pubsub_callback(self, future):
        """Callback for Pub/Sub publish completion."""
        try:
            message_id = future.result()
            logger.debug(f"Published message: {message_id}")
        except Exception as e:
            logger.error(f"Pub/Sub publish callback error: {e}")


# Singleton instance
dual_write_service = DualWriteService()
