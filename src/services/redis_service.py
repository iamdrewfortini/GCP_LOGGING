import os
import json
import redis
import time
import logging
import hashlib
import pickle
import threading
from typing import Optional, Any, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


def _redis_enabled() -> bool:
    """Whether Redis-backed features are enabled.

    Defaults to disabled so CI/tests never depend on external Redis.
    """
    return os.getenv("ENABLE_REDIS", "false").lower() == "true"


class RedisService:
    """Enhanced Redis service for caching, queuing, streaming."""

    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", 6379))
        self.username = os.getenv("REDIS_USERNAME", None)
        self.password = os.getenv("REDIS_PASSWORD", None)
        self.client: Optional[redis.Redis] = None
        self._connect_lock = threading.Lock()

    def _connect_if_needed(self) -> None:
        """Lazy-connect to Redis.

        Must be safe at import time and in CI environments.
        """
        if self.client is not None:
            return

        if not _redis_enabled():
            return

        with self._connect_lock:
            if self.client is not None:
                return

            try:
                self.client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    decode_responses=True,  # Auto-decode bytes to strings for strings, but we'll handle binary
                    socket_timeout=5,
                )
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self.client = None

    def ping(self) -> bool:
        self._connect_if_needed()
        if not self.client:
            return False
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def enqueue(self, queue_name: str, payload: dict) -> bool:
        """Push a job to a Redis List queue."""
        self._connect_if_needed()
        if not self.client:
            return False
        try:
            self.client.rpush(queue_name, json.dumps(payload))
            return True
        except Exception as e:
            logger.error(f"Redis enqueue error: {e}")
            return False

    def dequeue(self, queue_name: str, timeout: int = 5) -> Optional[dict]:
        """Blocking pop from a Redis List queue."""
        self._connect_if_needed()
        if not self.client:
            return None
        try:
            # blpop returns (queue_name, element) tuple
            result = self.client.blpop(queue_name, timeout=timeout)
            if result:
                return json.loads(result[1])
            return None
        except Exception as e:
            logger.error(f"Redis dequeue error: {e}")
            return None
            
    def set_cache(self, key: str, value: Any, ttl: int = 3600):
        self._connect_if_needed()
        if not self.client:
            return
        try:
            self.client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.error(f"Redis set_cache error: {e}")

    def get_cache(self, key: str) -> Optional[Any]:
        self._connect_if_needed()
        if not self.client:
            return None
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None

    def _hash_key(self, key: str) -> str:
        """Generate consistent hash for keys."""
        return hashlib.sha256(key.encode()).hexdigest()

    def _serialize(self, data: Any) -> bytes:
        """Serialize data: JSON for dicts, pickle for others."""
        if isinstance(data, (dict, list, str, int, float, bool)):
            return json.dumps(data).encode('utf-8')
        else:
            return pickle.dumps(data)

    def _deserialize(self, data: bytes) -> Any:
        """Deserialize data."""
        try:
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return pickle.loads(data)

    # Enhanced caching with hashing and serialization
    def cache_set_hashed(self, key: str, value: Any, ttl: int = 3600):
        """Set cache with hashed key and proper serialization."""
        self._connect_if_needed()
        if self.client:
            hashed_key = self._hash_key(key)
            serialized = self._serialize(value)
            self.client.setex(hashed_key, ttl, serialized)

    def cache_get_hashed(self, key: str) -> Optional[Any]:
        """Get from hashed cache."""
        self._connect_if_needed()
        if self.client:
            hashed_key = self._hash_key(key)
            data = self.client.get(hashed_key)
            if data:
                return self._deserialize(data)
        return None

    # Streaming methods
    def stream_add(self, stream_name: str, data: Dict[str, Any]) -> Optional[str]:
        """Add to stream."""
        self._connect_if_needed()
        if self.client:
            try:
                return self.client.xadd(stream_name, data)
            except Exception as e:
                logger.error(f"Stream add error: {e}")
        return None

    def stream_read(self, stream_name: str, last_id: str = '0', count: int = 10) -> List[Dict[str, Any]]:
        """Read from stream."""
        self._connect_if_needed()
        if self.client:
            try:
                entries = self.client.xread({stream_name: last_id}, count=count, block=1000)
                return entries
            except Exception as e:
                logger.error(f"Stream read error: {e}")
        return []

    # Pipeline specific caching
    def cache_normalized_log(self, log_id: str, normalized_data: Dict[str, Any]):
        """Cache normalized log data."""
        self.cache_set_hashed(f"normalized:{log_id}", normalized_data, ttl=86400)

    def get_cached_normalized_log(self, log_id: str) -> Optional[Dict[str, Any]]:
        """Get cached normalized log."""
        return self.cache_get_hashed(f"normalized:{log_id}")

    def cache_chunks(self, log_id: str, chunks: List[str]):
        """Cache chunks for log."""
        self.cache_set_hashed(f"chunks:{log_id}", chunks, ttl=86400)

    def get_cached_chunks(self, log_id: str) -> Optional[List[str]]:
        """Get cached chunks."""
        return self.cache_get_hashed(f"chunks:{log_id}")

    # ============================================================
    # Checkpoint Management (for embedding worker)
    # ============================================================

    def set_checkpoint(self, table: str, offset: int, total: int = 0) -> bool:
        """Store checkpoint for a table's embedding progress."""
        self._connect_if_needed()
        if not self.client:
            return False
        try:
            key = f"checkpoint:{table}"
            data = {
                "offset": offset,
                "total": total,
                "updated_at": datetime.utcnow().isoformat()
            }
            self.client.set(key, json.dumps(data))
            return True
        except Exception as e:
            logger.error(f"Redis set_checkpoint error: {e}")
            return False

    def get_checkpoint(self, table: str) -> Optional[Dict]:
        """Get checkpoint for a table."""
        self._connect_if_needed()
        if not self.client:
            return None
        try:
            key = f"checkpoint:{table}"
            data = self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Redis get_checkpoint error: {e}")
            return None

    def get_all_checkpoints(self) -> Dict[str, Dict]:
        """Get all table checkpoints."""
        self._connect_if_needed()
        if not self.client:
            return {}
        try:
            checkpoints = {}
            cursor = 0
            while True:
                cursor, keys = self.client.scan(cursor, match="checkpoint:*", count=100)
                for key in keys:
                    if key != "checkpoint:global":
                        table = key.replace("checkpoint:", "")
                        data = self.client.get(key)
                        if data:
                            checkpoints[table] = json.loads(data)
                if cursor == 0:
                    break
            return checkpoints
        except Exception as e:
            logger.error(f"Redis get_all_checkpoints error: {e}")
            return {}

    def set_global_checkpoint(self, tables_completed: int, total_embedded: int) -> bool:
        """Store global embedding progress."""
        self._connect_if_needed()
        if not self.client:
            return False
        try:
            data = {
                "tables_completed": tables_completed,
                "total_embedded": total_embedded,
                "updated_at": datetime.utcnow().isoformat()
            }
            self.client.set("checkpoint:global", json.dumps(data))
            return True
        except Exception as e:
            logger.error(f"Redis set_global_checkpoint error: {e}")
            return False

    def get_global_checkpoint(self) -> Optional[Dict]:
        """Get global embedding progress."""
        self._connect_if_needed()
        if not self.client:
            return None
        try:
            data = self.client.get("checkpoint:global")
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Redis get_global_checkpoint error: {e}")
            return None

    def delete_checkpoint(self, table: str) -> bool:
        """Delete a table's checkpoint."""
        self._connect_if_needed()
        if not self.client:
            return False
        try:
            self.client.delete(f"checkpoint:{table}")
            return True
        except Exception as e:
            logger.error(f"Redis delete_checkpoint error: {e}")
            return False

    def reset_all_checkpoints(self) -> int:
        """Delete all checkpoints. Returns count of deleted keys."""
        self._connect_if_needed()
        if not self.client:
            return 0
        try:
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = self.client.scan(cursor, match="checkpoint:*", count=100)
                if keys:
                    deleted += self.client.delete(*keys)
                if cursor == 0:
                    break
            return deleted
        except Exception as e:
            logger.error(f"Redis reset_all_checkpoints error: {e}")
            return 0

    # ============================================================
    # Metrics Management (for batch optimizer)
    # ============================================================

    def record_latency(self, service: str, latency_ms: float, max_samples: int = 100) -> bool:
        """Record a latency sample for a service (ollama, qdrant)."""
        self._connect_if_needed()
        if not self.client:
            return False
        try:
            key = f"metrics:{service}:latency"
            self.client.lpush(key, latency_ms)
            self.client.ltrim(key, 0, max_samples - 1)  # Keep last N samples
            return True
        except Exception as e:
            logger.error(f"Redis record_latency error: {e}")
            return False

    def get_latency_stats(self, service: str) -> Dict:
        """Get latency statistics for a service."""
        self._connect_if_needed()
        if not self.client:
            return {"avg": 0, "min": 0, "max": 0, "samples": 0}
        try:
            key = f"metrics:{service}:latency"
            values = self.client.lrange(key, 0, -1)
            if not values:
                return {"avg": 0, "min": 0, "max": 0, "samples": 0}
            latencies = [float(v) for v in values]
            return {
                "avg": sum(latencies) / len(latencies),
                "min": min(latencies),
                "max": max(latencies),
                "samples": len(latencies)
            }
        except Exception as e:
            logger.error(f"Redis get_latency_stats error: {e}")
            return {"avg": 0, "min": 0, "max": 0, "samples": 0}

    def increment_error_count(self, service: str, window_seconds: int = 300) -> int:
        """Increment error count for a service with auto-expire."""
        self._connect_if_needed()
        if not self.client:
            return 0
        try:
            key = f"metrics:{service}:errors"
            count = self.client.incr(key)
            self.client.expire(key, window_seconds)  # Auto-expire after window
            return count
        except Exception as e:
            logger.error(f"Redis increment_error_count error: {e}")
            return 0

    def get_error_count(self, service: str) -> int:
        """Get current error count for a service."""
        self._connect_if_needed()
        if not self.client:
            return 0
        try:
            key = f"metrics:{service}:errors"
            count = self.client.get(key)
            return int(count) if count else 0
        except Exception as e:
            logger.error(f"Redis get_error_count error: {e}")
            return 0

    def reset_error_count(self, service: str) -> bool:
        """Reset error count for a service."""
        self._connect_if_needed()
        if not self.client:
            return False
        try:
            self.client.delete(f"metrics:{service}:errors")
            return True
        except Exception as e:
            logger.error(f"Redis reset_error_count error: {e}")
            return False

    def set_optimal_batch_sizes(self, embed_size: int, upsert_size: int) -> bool:
        """Store optimal batch sizes determined by auto-tuner."""
        self._connect_if_needed()
        if not self.client:
            return False
        try:
            data = {
                "embed": embed_size,
                "upsert": upsert_size,
                "updated_at": datetime.utcnow().isoformat()
            }
            self.client.set("metrics:batch:optimal", json.dumps(data))
            return True
        except Exception as e:
            logger.error(f"Redis set_optimal_batch_sizes error: {e}")
            return False

    def get_optimal_batch_sizes(self) -> Dict:
        """Get optimal batch sizes."""
        self._connect_if_needed()
        if not self.client:
            return {"embed": 10, "upsert": 20}  # Defaults
        try:
            data = self.client.get("metrics:batch:optimal")
            if data:
                return json.loads(data)
            return {"embed": 10, "upsert": 20}
        except Exception as e:
            logger.error(f"Redis get_optimal_batch_sizes error: {e}")
            return {"embed": 10, "upsert": 20}

    # ============================================================
    # Queue Management (extended)
    # ============================================================

    def queue_length(self, queue_name: str) -> int:
        """Get the length of a queue."""
        self._connect_if_needed()
        if not self.client:
            return 0
        try:
            return self.client.llen(queue_name)
        except Exception as e:
            logger.error(f"Redis queue_length error: {e}")
            return 0

    def peek_queue(self, queue_name: str, count: int = 10) -> List[Dict]:
        """Peek at items in a queue without removing them."""
        self._connect_if_needed()
        if not self.client:
            return []
        try:
            items = self.client.lrange(queue_name, 0, count - 1)
            return [json.loads(item) for item in items]
        except Exception as e:
            logger.error(f"Redis peek_queue error: {e}")
            return []

    def move_to_failed(self, queue_name: str, job: Dict, error: str) -> bool:
        """Move a failed job to the dead letter queue."""
        self._connect_if_needed()
        if not self.client:
            return False
        try:
            job["error"] = error
            job["failed_at"] = datetime.utcnow().isoformat()
            job["original_queue"] = queue_name
            self.client.rpush("q:embed:failed", json.dumps(job))
            return True
        except Exception as e:
            logger.error(f"Redis move_to_failed error: {e}")
            return False

    def retry_failed_jobs(self, target_queue: str, count: int = 10) -> int:
        """Move failed jobs back to processing queue."""
        self._connect_if_needed()
        if not self.client:
            return 0
        try:
            retried = 0
            for _ in range(count):
                job_data = self.client.lpop("q:embed:failed")
                if not job_data:
                    break
                job = json.loads(job_data)
                job["retry_count"] = job.get("retry_count", 0) + 1
                job.pop("error", None)
                job.pop("failed_at", None)
                self.client.rpush(target_queue, json.dumps(job))
                retried += 1
            return retried
        except Exception as e:
            logger.error(f"Redis retry_failed_jobs error: {e}")
            return 0

    def clear_queue(self, queue_name: str) -> int:
        """Clear all items from a queue."""
        self._connect_if_needed()
        if not self.client:
            return 0
        try:
            length = self.client.llen(queue_name)
            self.client.delete(queue_name)
            return length
        except Exception as e:
            logger.error(f"Redis clear_queue error: {e}")
            return 0


redis_service = RedisService()
