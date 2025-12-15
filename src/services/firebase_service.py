"""Firebase service for session and message persistence."""

from __future__ import annotations

import os
from typing import Any, Optional

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter


class FirebaseService:
    """Singleton service for Firebase/Firestore operations."""

    _instance: Optional[FirebaseService] = None
    _db: Optional[firestore.Client] = None
    _initialized: bool = False

    def __new__(cls) -> FirebaseService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not self._initialized:
            self._initialize_firebase()
            FirebaseService._initialized = True

    @classmethod
    def _initialize_firebase(cls) -> None:
        """Initialize Firebase Admin SDK."""
        if not firebase_admin._apps:
            # In Cloud Run, use Application Default Credentials
            # Locally, use GOOGLE_APPLICATION_CREDENTIALS env var
            project_id = os.getenv("PROJECT_ID", "diatonic-ai-gcp")
            firebase_admin.initialize_app(options={"projectId": project_id})

        cls._db = firestore.client()

    @property
    def db(self) -> firestore.Client:
        """Get Firestore client."""
        if self._db is None:
            self._initialize_firebase()
        return self._db

    @property
    def enabled(self) -> bool:
        """Check if Firebase is enabled."""
        return os.getenv("FIREBASE_ENABLED", "true").lower() == "true"

    # ============================================
    # SESSION MANAGEMENT
    # ============================================

    def create_session(
        self,
        user_id: str,
        title: str = "New Session",
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Create a new AI chat session.

        Args:
            user_id: The user ID for the session owner.
            title: Display title for the session.
            metadata: Additional metadata to store.

        Returns:
            The session ID.
        """
        if not self.enabled:
            return "local-session"

        session_ref = self.db.collection("sessions").document()
        session_data = {
            "userId": user_id,
            "title": title,
            "status": "active",
            "createdAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "metadata": {
                "totalMessages": 0,
                "totalCost": 0,
                "tags": [],
                **(metadata or {}),
            },
        }
        session_ref.set(session_data)
        return session_ref.id

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        """Get session by ID.

        Args:
            session_id: The session document ID.

        Returns:
            Session data dict or None if not found.
        """
        if not self.enabled:
            return None

        doc = self.db.collection("sessions").document(session_id).get()
        if doc.exists:
            return doc.to_dict() | {"id": doc.id}
        return None

    def list_sessions(
        self,
        user_id: str,
        status: str = "active",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List user's sessions.

        Args:
            user_id: The user ID to filter by.
            status: Session status filter (active, archived, deleted).
            limit: Maximum number of sessions to return.

        Returns:
            List of session dicts.
        """
        if not self.enabled:
            return []

        query = (
            self.db.collection("sessions")
            .where(filter=FieldFilter("userId", "==", user_id))
            .where(filter=FieldFilter("status", "==", status))
            .order_by("updatedAt", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )

        return [doc.to_dict() | {"id": doc.id} for doc in query.stream()]

    def update_session(
        self,
        session_id: str,
        updates: dict[str, Any],
    ) -> None:
        """Update session fields.

        Args:
            session_id: The session document ID.
            updates: Fields to update.
        """
        if not self.enabled:
            return

        session_ref = self.db.collection("sessions").document(session_id)
        session_ref.update(
            {
                **updates,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
        )

    def archive_session(self, session_id: str) -> None:
        """Archive a session.

        Args:
            session_id: The session document ID.
        """
        self.update_session(session_id, {"status": "archived"})

    # ============================================
    # MESSAGE MANAGEMENT
    # ============================================

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Add message to session.

        Args:
            session_id: The session document ID.
            role: Message role (user, assistant, system, tool).
            content: Message content.
            metadata: Additional metadata (tokens, cost, etc.).

        Returns:
            The message document ID.
        """
        if not self.enabled:
            return "local-message"

        message_ref = (
            self.db.collection("sessions")
            .document(session_id)
            .collection("messages")
            .document()
        )

        message_ref.set(
            {
                "role": role,
                "content": content,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "metadata": metadata or {},
            }
        )

        # Update session metadata
        session_ref = self.db.collection("sessions").document(session_id)
        session_ref.update(
            {
                "updatedAt": firestore.SERVER_TIMESTAMP,
                "metadata.totalMessages": firestore.Increment(1),
            }
        )

        return message_ref.id

    def get_messages(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get session messages.

        Args:
            session_id: The session document ID.
            limit: Maximum number of messages to return.

        Returns:
            List of message dicts ordered by timestamp.
        """
        if not self.enabled:
            return []

        query = (
            self.db.collection("sessions")
            .document(session_id)
            .collection("messages")
            .order_by("timestamp")
            .limit(limit)
        )

        return [doc.to_dict() | {"id": doc.id} for doc in query.stream()]

    # ============================================
    # GRAPH STATE PERSISTENCE
    # ============================================

    def save_graph_state(
        self,
        session_id: str,
        state: dict[str, Any],
        checkpoint_id: Optional[str] = None,
    ) -> str:
        """Save LangGraph state for a session.

        Args:
            session_id: The session document ID.
            state: The serialized graph state.
            checkpoint_id: Optional checkpoint identifier.

        Returns:
            The state document ID.
        """
        if not self.enabled:
            return "local-state"

        state_ref = (
            self.db.collection("sessions")
            .document(session_id)
            .collection("graphStates")
            .document()
        )

        state_ref.set(
            {
                "state": state,
                "checkpointId": checkpoint_id,
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )

        return state_ref.id

    def get_latest_graph_state(
        self,
        session_id: str,
    ) -> Optional[dict[str, Any]]:
        """Get the most recent graph state for a session.

        Args:
            session_id: The session document ID.

        Returns:
            The latest state dict or None.
        """
        if not self.enabled:
            return None

        query = (
            self.db.collection("sessions")
            .document(session_id)
            .collection("graphStates")
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(1)
        )

        docs = list(query.stream())
        if docs:
            return docs[0].to_dict() | {"id": docs[0].id}
        return None

    # ============================================
    # SAVED QUERIES
    # ============================================

    def save_query(
        self,
        user_id: str,
        name: str,
        query_params: dict[str, Any],
    ) -> str:
        """Save a reusable log query.

        Args:
            user_id: The user ID.
            name: Display name for the saved query.
            query_params: The query parameters to save.

        Returns:
            The saved query document ID.
        """
        if not self.enabled:
            return "local-query"

        query_ref = self.db.collection("savedQueries").document()
        query_ref.set(
            {
                "userId": user_id,
                "name": name,
                "queryParams": query_params,
                "createdAt": firestore.SERVER_TIMESTAMP,
                "lastRunAt": firestore.SERVER_TIMESTAMP,
                "runCount": 0,
            }
        )

        return query_ref.id

    def list_saved_queries(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List user's saved queries.

        Args:
            user_id: The user ID.
            limit: Maximum queries to return.

        Returns:
            List of saved query dicts.
        """
        if not self.enabled:
            return []

        query = (
            self.db.collection("savedQueries")
            .where(filter=FieldFilter("userId", "==", user_id))
            .order_by("lastRunAt", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )

        return [doc.to_dict() | {"id": doc.id} for doc in query.stream()]


# Singleton instance
firebase_service = FirebaseService()
