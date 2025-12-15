import os
import json
import redis
from typing import Optional, Any, List

class RedisService:
    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", 6379))
        self.username = os.getenv("REDIS_USERNAME", None) 
        self.password = os.getenv("REDIS_PASSWORD", None)
        self.client: Optional[redis.Redis] = None
        self._connect()

    def _connect(self):
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                decode_responses=True, # Auto-decode bytes to strings
                socket_timeout=5
            )
        except Exception as e:
            print(f"Failed to connect to Redis: {e}")
            self.client = None

    def ping(self) -> bool:
        if not self.client:
            self._connect()
        try:
            return self.client.ping()
        except Exception:
            return False

    def enqueue(self, queue_name: str, payload: dict) -> bool:
        """Push a job to a Redis List queue."""
        if not self.client:
            return False
        try:
            self.client.rpush(queue_name, json.dumps(payload))
            return True
        except Exception as e:
            print(f"Redis enqueue error: {e}")
            return False

    def dequeue(self, queue_name: str, timeout: int = 5) -> Optional[dict]:
        """Blocking pop from a Redis List queue."""
        if not self.client:
            return None
        try:
            # blpop returns (queue_name, element) tuple
            result = self.client.blpop(queue_name, timeout=timeout)
            if result:
                return json.loads(result[1])
            return None
        except Exception as e:
            print(f"Redis dequeue error: {e}")
            return None
            
    def set_cache(self, key: str, value: Any, ttl: int = 3600):
        if not self.client:
            return
        try:
            self.client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            print(f"Redis set_cache error: {e}")

    def get_cache(self, key: str) -> Optional[Any]:
        if not self.client:
            return None
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None

redis_service = RedisService()
