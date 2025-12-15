"""
Firebase service for realtime database integration.

Uses Firebase Realtime DB for realtime updates, with Redis as edge cache.
"""

import os
import json
import logging
from typing import Optional, Any, Dict
import firebase_admin
from firebase_admin import credentials, db
from src.services.redis_service import RedisService

logger = logging.getLogger(__name__)

class FirebaseService:
    """Firebase realtime service with Redis cache."""

    def __init__(self):
        self.redis = RedisService()
        self.app = None
        self.db_ref = None
        self._init_firebase()

    def _init_firebase(self):
        """Initialize Firebase app."""
        try:
            # Skip if already initialized
            if firebase_admin._apps:
                self.app = firebase_admin.get_app()
                try:
                    self.db_ref = db.reference()
                except Exception:
                    pass  # DB not configured, that's ok
                logger.info("Firebase already initialized")
                return

            cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
            project_id = os.getenv("PROJECT_ID", os.getenv("GCP_PROJECT_ID", "diatonic-ai-gcp"))

            if cred_path:
                # Use explicit credentials file (local dev)
                cred = credentials.Certificate(cred_path)
            else:
                # Use Application Default Credentials (Cloud Run)
                cred = credentials.ApplicationDefault()

            db_url = os.getenv("FIREBASE_DATABASE_URL")
            options = {'projectId': project_id}
            if db_url:
                options['databaseURL'] = db_url

            self.app = firebase_admin.initialize_app(cred, options)

            if db_url:
                self.db_ref = db.reference()

            logger.info(f"Firebase initialized for project: {project_id}")
        except Exception as e:
            logger.error(f"Firebase init error: {e}")

    def set_realtime_data(self, path: str, data: Any, use_cache: bool = True):
        """Set data in Firebase realtime DB, cache in Redis."""
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

# Global instance
firebase_service = FirebaseService()