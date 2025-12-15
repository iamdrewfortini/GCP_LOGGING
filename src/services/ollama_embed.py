"""
Ollama embedding service for batch embedding with caching and metrics.

Uses Redis for caching embeddings by content hash.
Supports batch inputs, enforces dimension checks.
Records timings and metrics.

Based on spec: embed.ollama module.
"""

import os
import hashlib
import time
import logging
from typing import List, Optional, Dict, Any
import httpx
from src.services.redis_service import RedisService

logger = logging.getLogger(__name__)

# Config from env
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))  # Updated for qwen3
REDIS_EMBED_CACHE_KEY_PREFIX = "embed_cache:"
MAX_TEXT_LENGTH = 8192  # Ollama limit
MAX_RETRIES = 3
RETRY_DELAY = 1.0

class OllamaEmbedService:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL.rstrip("/")
        self.embed_url = f"{self.base_url}/api/embed"
        self.model = OLLAMA_EMBED_MODEL
        self.expected_dim = EMBED_DIM
        self.redis = RedisService()
        self.cache_hits = 0
        self.cache_misses = 0
        logger.info(f"Initialized Ollama embed service: {self.model} @ {self.base_url}, dim {self.expected_dim}")

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key: sha256(model|text)"""
        content = f"{self.model}|{text}"
        return content

    def _cache_get(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache."""
        key = self._get_cache_key(text)
        try:
            cached = self.redis.cache_get_hashed(key)
            if cached:
                self.cache_hits += 1
                return cached
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        self.cache_misses += 1
        return None

    def _cache_set(self, text: str, embedding: List[float]):
        """Set embedding in cache."""
        key = self._get_cache_key(text)
        try:
            self.redis.cache_set_hashed(key, embedding, ttl=86400)  # Expire in 1 day
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    def _embed_single(self, text: str) -> List[float]:
        """Embed single text via Ollama."""
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "... [truncated]"
        payload = {"model": self.model, "input": text}
        for attempt in range(MAX_RETRIES):
            try:
                start_time = time.time()
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(self.embed_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                elapsed = time.time() - start_time
                emb = data.get("embeddings")
                if not emb or not isinstance(emb, list) or not emb[0]:
                    raise ValueError("No embedding returned")
                embedding = emb[0]
                if len(embedding) != self.expected_dim:
                    raise ValueError(f"Dimension mismatch: got {len(embedding)}, expected {self.expected_dim}")
                logger.debug(f"Embedded text in {elapsed:.3f}s")
                # TODO: Record to bench tables (embed_ms, etc.)
                return embedding
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (2 ** attempt))
                    continue
                logger.error(f"Ollama HTTP error: {e}")
                raise
            except Exception as e:
                logger.error(f"Embed error: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                raise
        raise RuntimeError("Embedding failed after retries")

    def embed_batch(self, texts: List[str], use_cache: bool = True) -> List[List[float]]:
        """
        Batch embed texts, with caching.

        Returns list of embeddings, same order as input.
        """
        if not texts:
            return []
        embeddings = []
        total_start = time.time()
        for text in texts:
            if use_cache:
                cached = self._cache_get(text)
                if cached:
                    embeddings.append(cached)
                    continue
            emb = self._embed_single(text)
            embeddings.append(emb)
            if use_cache:
                self._cache_set(text, emb)
        total_elapsed = time.time() - total_start
        hit_rate = self.cache_hits / (self.cache_hits + self.cache_misses) if (self.cache_hits + self.cache_misses) > 0 else 0
        logger.info(f"Embedded {len(texts)} texts in {total_elapsed:.3f}s, cache hit rate: {hit_rate:.2f}")
        return embeddings

    def embed_single(self, text: str, use_cache: bool = True) -> List[float]:
        """Embed single text, with cache."""
        if use_cache:
            cached = self._cache_get(text)
            if cached:
                return cached
        emb = self._embed_single(text)
        if use_cache:
            self._cache_set(text, emb)
        return emb

    def get_metrics(self) -> Dict[str, Any]:
        """Return current metrics."""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total_requests if total_requests > 0 else 0
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": hit_rate,
            "model": self.model,
            "expected_dim": self.expected_dim
        }