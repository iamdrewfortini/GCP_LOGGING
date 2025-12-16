"""Firebase service for Firestore and Realtime Database integration.

Uses Firestore for session/query persistence and optional Realtime DB for updates.

IMPORTANT: Do not initialize Firebase/Firestore at import time.
- CI environments may not have ADC.
- Import-time side effects can break pytest collection.
"""

from __future__ import annotations

import os
import json
import logging
import threading
import uuid
from datetime import datetime
from typing import Optional, Any, Dict, List

import firebase_admin
from firebase_admin import credentials, db, firestore

from src.services.redis_service import RedisService

logger = logging.getLogger(__name__)


def _firebase_enabled() -> bool:
    """Whether Firebase is enabled for this process.

    Defaults to disabled so CI/tests never depend on ADC.
    """
    return os.getenv("FIREBASE_ENABLED", "false").lower() == "true"


class FirebaseService:
    """Firebase service with Firestore for persistence and optional Realtime DB."""

    def __init__(self):
        self.redis = RedisService()
        self.app = None
        self.db_ref = None
        self.firestore_db = None

        self._lock = threading.Lock()
        self._init_error: Optional[Exception] = None

    def _ensure_initialized(self) -> None:
        """Ensure Firebase app + Firestore client are initialized.

        Safe to call repeatedly.
        """
        if self.firestore_db is not None:
            return

        if not _firebase_enabled():
            return

        if self._init_error is not None:
            return

        with self._lock:
            if self.firestore_db is not None:
                return
            if self._init_error is not None:
                return

            try:
                # Reuse existing app if already initialized elsewhere.
                try:
                    self.app = firebase_admin.get_app()
                except ValueError:
                    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
                    project_id = os.getenv(
                        "PROJECT_ID",
                        os.getenv("GCP_PROJECT_ID", "diatonic-ai-gcp"),
                    )

                    if cred_path:
                        cred = credentials.Certificate(cred_path)
                    else:
                        cred = credentials.ApplicationDefault()

                    db_url = os.getenv("FIREBASE_DATABASE_URL")
                    options = {"projectId": project_id}
                    if db_url:
                        options["databaseURL"] = db_url

                    self.app = firebase_admin.initialize_app(cred, options)

                # Initialize Firestore
                self.firestore_db = firestore.client()

                # Initialize Realtime DB reference if configured
                try:
                    self.db_ref = db.reference()
                except Exception:
                    self.db_ref = None

                logger.info("Firebase initialized")

            except Exception as e:
                self._init_error = e
                logger.warning(f"Firebase init failed: {e}")
                self.firestore_db = None
                self.db_ref = None

    @property
    def enabled(self) -> bool:
        """Whether Firebase is enabled and available."""
        if not _firebase_enabled():
            return False
        self._ensure_initialized()
        return self.firestore_db is not None

    def set_realtime_data(self, path: str, data: Any, use_cache: bool = True):
        """Set data in Firebase realtime DB, cache in Redis."""
        self._ensure_initialized()
        if self.db_ref:
            try:
                self.db_ref.child(path).set(data)
                if use_cache:
                    self.redis.cache_set_hashed(f"firebase:{path}", data, ttl=300)  # 5 min cache
                logger.info(f"Set realtime data at {path}")
            except Exception as e:
                logger.error(f"Firebase set error: {e}")

    def get_realtime_data(self, path: str, use_cache: bool = True) -> Optional[Any]:
        """Get data from cache first, then Firebase."""
        self._ensure_initialized()
        if use_cache:
            cached = self.redis.cache_get_hashed(f"firebase:{path}")
            if cached:
                return cached
        if self.db_ref:
            try:
                data = self.db_ref.child(path).get()
                if data and use_cache:
                    self.redis.cache_set_hashed(f"firebase:{path}", data, ttl=300)
                return data
            except Exception as e:
                logger.error(f"Firebase get error: {e}")
        return None

    def stream_realtime_updates(self, path: str, callback):
        """Listen for realtime updates."""
        self._ensure_initialized()
        if self.db_ref:
            def listener(event):
                callback(event.data)
            self.db_ref.child(path).listen(listener)

    # Specific for logs
    def push_log_update(self, log_id: str, update: Dict[str, Any]):
        """Push log update to realtime."""
        self.set_realtime_data(f"logs/{log_id}", update)

    def get_log_realtime(self, log_id: str) -> Optional[Dict[str, Any]]:
        """Get log from realtime."""
        return self.get_realtime_data(f"logs/{log_id}")

    # For chat or queries
    def push_query_result(self, query_id: str, result: Dict[str, Any]):
        """Push query result for realtime frontend."""
        self.set_realtime_data(f"queries/{query_id}", result)

    # ============================================
    # SESSION MANAGEMENT (Firestore)
    # ============================================

    def create_session(self, user_id: str, title: str = "New Session") -> str:
        """Create a new chat session."""
        self._ensure_initialized()
        if not self.firestore_db:
            raise RuntimeError("Firestore not initialized")

        session_id = str(uuid.uuid4())
        now = datetime.utcnow()

        session_data = {
            "id": session_id,
            "user_id": user_id,
            "title": title,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
        }

        self.firestore_db.collection("sessions").document(session_id).set(session_data)
        logger.info(f"Created session {session_id} for user {user_id}")
        return session_id

    def list_sessions(self, user_id: str, status: str = "active", limit: int = 50) -> List[Dict[str, Any]]:
        """List user's sessions."""
        self._ensure_initialized()
        if not self.firestore_db:
            return []

        try:
            query = (
                self.firestore_db.collection("sessions")
                .where("user_id", "==", user_id)
                .where("status", "==", status)
                .order_by("updated_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )

            sessions = []
            for doc in query.stream():
                session = doc.to_dict()
                # Convert timestamps to ISO strings
                if session.get("created_at"):
                    session["created_at"] = session["created_at"].isoformat() if hasattr(session["created_at"], 'isoformat') else str(session["created_at"])
                if session.get("updated_at"):
                    session["updated_at"] = session["updated_at"].isoformat() if hasattr(session["updated_at"], 'isoformat') else str(session["updated_at"])
                sessions.append(session)

            return sessions
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return []

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a session by ID."""
        self._ensure_initialized()
        if not self.firestore_db:
            return None

        try:
            doc = self.firestore_db.collection("sessions").document(session_id).get()
            if doc.exists:
                session = doc.to_dict()
                # Convert timestamps
                if session.get("created_at"):
                    session["created_at"] = session["created_at"].isoformat() if hasattr(session["created_at"], 'isoformat') else str(session["created_at"])
                if session.get("updated_at"):
                    session["updated_at"] = session["updated_at"].isoformat() if hasattr(session["updated_at"], 'isoformat') else str(session["updated_at"])

                # Get messages
                messages = self.get_session_messages(session_id)
                session["messages"] = messages

                return session
            return None
        except Exception as e:
            logger.error(f"Error getting session: {e}")
            return None

    def archive_session(self, session_id: str) -> bool:
        """Archive a session."""
        self._ensure_initialized()
        if not self.firestore_db:
            return False

        try:
            self.firestore_db.collection("sessions").document(session_id).update({
                "status": "archived",
                "updated_at": datetime.utcnow(),
            })
            return True
        except Exception as e:
            logger.error(f"Error archiving session: {e}")
            return False

    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> str:
        """Add a message to a session."""
        self._ensure_initialized()
        if not self.firestore_db:
            raise RuntimeError("Firestore not initialized")

        message_id = str(uuid.uuid4())
        now = datetime.utcnow()

        message_data = {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": now,
            "metadata": metadata or {},
        }

        self.firestore_db.collection("sessions").document(session_id).collection("messages").document(message_id).set(message_data)

        # Update session
        self.firestore_db.collection("sessions").document(session_id).update({
            "updated_at": now,
            "message_count": firestore.Increment(1),
        })

        return message_id

    def get_session_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get messages for a session."""
        self._ensure_initialized()
        if not self.firestore_db:
            return []

        try:
            query = (
                self.firestore_db.collection("sessions").document(session_id)
                .collection("messages")
                .order_by("timestamp")
                .limit(limit)
            )

            messages = []
            for doc in query.stream():
                msg = doc.to_dict()
                if msg.get("timestamp"):
                    msg["timestamp"] = msg["timestamp"].isoformat() if hasattr(msg["timestamp"], 'isoformat') else str(msg["timestamp"])
                messages.append(msg)

            return messages
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            return []

    # ============================================
    # SAVED QUERIES (Firestore)
    # ============================================

    def save_query(self, user_id: str, name: str, query_params: Dict[str, Any]) -> str:
        """Save a reusable query."""
        self._ensure_initialized()
        if not self.firestore_db:
            raise RuntimeError("Firestore not initialized")

        query_id = str(uuid.uuid4())
        now = datetime.utcnow()

        query_data = {
            "id": query_id,
            "user_id": user_id,
            "name": name,
            "query_params": query_params,
            "created_at": now,
            "updated_at": now,
        }

        self.firestore_db.collection("saved_queries").document(query_id).set(query_data)
        return query_id

    def list_saved_queries(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """List user's saved queries."""
        self._ensure_initialized()
        if not self.firestore_db:
            return []

        try:
            query = (
                self.firestore_db.collection("saved_queries")
                .where("user_id", "==", user_id)
                .order_by("updated_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )

            queries = []
            for doc in query.stream():
                q = doc.to_dict()
                if q.get("created_at"):
                    q["created_at"] = q["created_at"].isoformat() if hasattr(q["created_at"], 'isoformat') else str(q["created_at"])
                if q.get("updated_at"):
                    q["updated_at"] = q["updated_at"].isoformat() if hasattr(q["updated_at"], 'isoformat') else str(q["updated_at"])
                queries.append(q)

            return queries
        except Exception as e:
            logger.error(f"Error listing saved queries: {e}")
            return []

# Global instance
firebase_service = FirebaseService()