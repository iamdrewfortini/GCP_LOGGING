"""
Batch Optimizer Service

Adaptive batch size tuning based on latency and error rates.
Automatically adjusts embedding and upsert batch sizes to optimize throughput.
"""

import time
import logging
from typing import Dict, Tuple, Callable, Any
from dataclasses import dataclass
from functools import wraps

from src.services.redis_service import redis_service

logger = logging.getLogger(__name__)


@dataclass
class BatchConfig:
    """Configuration for batch size limits."""
    # Embedding batch sizes (Ollama)
    MIN_EMBED_BATCH: int = 5
    MAX_EMBED_BATCH: int = 50
    DEFAULT_EMBED_BATCH: int = 10

    # Upsert batch sizes (Qdrant)
    MIN_UPSERT_BATCH: int = 10
    MAX_UPSERT_BATCH: int = 100
    DEFAULT_UPSERT_BATCH: int = 20

    # Tuning parameters
    TARGET_LATENCY_MS: float = 500.0      # Target per-operation latency
    MAX_LATENCY_MS: float = 2000.0        # Maximum acceptable latency
    MAX_ERROR_RATE: float = 0.05          # 5% error threshold
    INCREASE_FACTOR: float = 1.2          # Increase batch by 20%
    DECREASE_FACTOR: float = 0.7          # Decrease batch by 30%
    MIN_SAMPLES_FOR_TUNING: int = 10      # Min samples before adjusting
    TUNING_INTERVAL_SEC: int = 30         # Minimum time between adjustments


class BatchOptimizer:
    """
    Adaptive batch size optimizer.

    Monitors latency and error rates for Ollama (embedding) and Qdrant (upsert)
    operations, automatically adjusting batch sizes to maximize throughput
    while staying within acceptable latency bounds.
    """

    def __init__(self, config: BatchConfig = None):
        self.config = config or BatchConfig()
        self.redis = redis_service
        self._last_tuning_time = 0
        self._embed_batch_size = self.config.DEFAULT_EMBED_BATCH
        self._upsert_batch_size = self.config.DEFAULT_UPSERT_BATCH
        self._load_from_redis()

    def _load_from_redis(self):
        """Load optimal batch sizes from Redis if available."""
        try:
            sizes = self.redis.get_optimal_batch_sizes()
            if sizes:
                self._embed_batch_size = sizes.get("embed", self.config.DEFAULT_EMBED_BATCH)
                self._upsert_batch_size = sizes.get("upsert", self.config.DEFAULT_UPSERT_BATCH)
                logger.info(f"Loaded batch sizes from Redis: embed={self._embed_batch_size}, upsert={self._upsert_batch_size}")
        except Exception as e:
            logger.warning(f"Could not load batch sizes from Redis: {e}")

    def _save_to_redis(self):
        """Persist optimal batch sizes to Redis."""
        try:
            self.redis.set_optimal_batch_sizes(self._embed_batch_size, self._upsert_batch_size)
        except Exception as e:
            logger.warning(f"Could not save batch sizes to Redis: {e}")

    @property
    def embed_batch_size(self) -> int:
        """Get current embedding batch size."""
        return self._embed_batch_size

    @property
    def upsert_batch_size(self) -> int:
        """Get current upsert batch size."""
        return self._upsert_batch_size

    def record_embed_latency(self, latency_ms: float, success: bool = True):
        """
        Record an embedding operation latency.

        Args:
            latency_ms: Operation latency in milliseconds
            success: Whether the operation succeeded
        """
        self.redis.record_latency("ollama", latency_ms)
        if not success:
            self.redis.increment_error_count("ollama")
        self._maybe_tune()

    def record_upsert_latency(self, latency_ms: float, success: bool = True):
        """
        Record an upsert operation latency.

        Args:
            latency_ms: Operation latency in milliseconds
            success: Whether the operation succeeded
        """
        self.redis.record_latency("qdrant", latency_ms)
        if not success:
            self.redis.increment_error_count("qdrant")
        self._maybe_tune()

    def _maybe_tune(self):
        """Check if it's time to tune batch sizes."""
        now = time.time()
        if now - self._last_tuning_time < self.config.TUNING_INTERVAL_SEC:
            return

        self._last_tuning_time = now
        self._tune_batch_sizes()

    def _tune_batch_sizes(self):
        """Adjust batch sizes based on collected metrics."""
        # Tune embedding batch size
        ollama_stats = self.redis.get_latency_stats("ollama")
        ollama_errors = self.redis.get_error_count("ollama")

        if ollama_stats["samples"] >= self.config.MIN_SAMPLES_FOR_TUNING:
            new_embed = self._calculate_optimal_size(
                current_size=self._embed_batch_size,
                avg_latency=ollama_stats["avg"],
                error_count=ollama_errors,
                total_ops=ollama_stats["samples"],
                min_size=self.config.MIN_EMBED_BATCH,
                max_size=self.config.MAX_EMBED_BATCH
            )
            if new_embed != self._embed_batch_size:
                logger.info(f"Adjusting embed batch size: {self._embed_batch_size} -> {new_embed} "
                           f"(avg_latency={ollama_stats['avg']:.1f}ms, errors={ollama_errors})")
                self._embed_batch_size = new_embed

        # Tune upsert batch size
        qdrant_stats = self.redis.get_latency_stats("qdrant")
        qdrant_errors = self.redis.get_error_count("qdrant")

        if qdrant_stats["samples"] >= self.config.MIN_SAMPLES_FOR_TUNING:
            new_upsert = self._calculate_optimal_size(
                current_size=self._upsert_batch_size,
                avg_latency=qdrant_stats["avg"],
                error_count=qdrant_errors,
                total_ops=qdrant_stats["samples"],
                min_size=self.config.MIN_UPSERT_BATCH,
                max_size=self.config.MAX_UPSERT_BATCH
            )
            if new_upsert != self._upsert_batch_size:
                logger.info(f"Adjusting upsert batch size: {self._upsert_batch_size} -> {new_upsert} "
                           f"(avg_latency={qdrant_stats['avg']:.1f}ms, errors={qdrant_errors})")
                self._upsert_batch_size = new_upsert

        # Persist to Redis
        self._save_to_redis()

    def _calculate_optimal_size(
        self,
        current_size: int,
        avg_latency: float,
        error_count: int,
        total_ops: int,
        min_size: int,
        max_size: int
    ) -> int:
        """
        Calculate optimal batch size based on metrics.

        Algorithm:
        - If error rate > threshold: decrease by 30%
        - If latency > max threshold: decrease by 30%
        - If latency > target * 1.5: decrease by 20%
        - If latency < target and errors low: increase by 20%
        - Otherwise: keep stable

        Args:
            current_size: Current batch size
            avg_latency: Average latency in milliseconds
            error_count: Number of errors in the window
            total_ops: Total operations in the window
            min_size: Minimum allowed batch size
            max_size: Maximum allowed batch size

        Returns:
            Optimal batch size
        """
        error_rate = error_count / max(total_ops, 1)

        # High error rate: decrease aggressively
        if error_rate > self.config.MAX_ERROR_RATE:
            new_size = int(current_size * self.config.DECREASE_FACTOR)
            logger.debug(f"High error rate ({error_rate:.2%}), decreasing batch size")
            return max(min_size, new_size)

        # Latency way too high: decrease aggressively
        if avg_latency > self.config.MAX_LATENCY_MS:
            new_size = int(current_size * self.config.DECREASE_FACTOR)
            logger.debug(f"Latency too high ({avg_latency:.0f}ms), decreasing batch size")
            return max(min_size, new_size)

        # Latency above target but acceptable: slight decrease
        if avg_latency > self.config.TARGET_LATENCY_MS * 1.5:
            new_size = int(current_size * 0.9)  # 10% decrease
            return max(min_size, new_size)

        # Latency within target and low errors: increase
        if avg_latency < self.config.TARGET_LATENCY_MS and error_rate < 0.01:
            new_size = int(current_size * self.config.INCREASE_FACTOR)
            logger.debug(f"Good performance, increasing batch size")
            return min(max_size, new_size)

        # Stable: keep current
        return current_size

    def get_stats(self) -> Dict:
        """
        Get current optimizer statistics.

        Returns:
            Dictionary with current batch sizes and metrics
        """
        ollama_stats = self.redis.get_latency_stats("ollama")
        qdrant_stats = self.redis.get_latency_stats("qdrant")

        return {
            "embed_batch_size": self._embed_batch_size,
            "upsert_batch_size": self._upsert_batch_size,
            "ollama": {
                "avg_latency_ms": round(ollama_stats["avg"], 2),
                "min_latency_ms": round(ollama_stats["min"], 2),
                "max_latency_ms": round(ollama_stats["max"], 2),
                "samples": ollama_stats["samples"],
                "error_count": self.redis.get_error_count("ollama")
            },
            "qdrant": {
                "avg_latency_ms": round(qdrant_stats["avg"], 2),
                "min_latency_ms": round(qdrant_stats["min"], 2),
                "max_latency_ms": round(qdrant_stats["max"], 2),
                "samples": qdrant_stats["samples"],
                "error_count": self.redis.get_error_count("qdrant")
            }
        }

    def reset_metrics(self):
        """Reset all collected metrics."""
        self.redis.reset_error_count("ollama")
        self.redis.reset_error_count("qdrant")
        # Note: Latency lists will age out naturally
        logger.info("Reset optimizer metrics")


def timed_operation(service: str, optimizer: BatchOptimizer):
    """
    Decorator to automatically time operations and record metrics.

    Args:
        service: Service name ("ollama" or "qdrant")
        optimizer: BatchOptimizer instance

    Usage:
        @timed_operation("ollama", optimizer)
        def embed_text(text):
            return ollama.embed(text)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start = time.time()
            success = True
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise
            finally:
                latency_ms = (time.time() - start) * 1000
                if service == "ollama":
                    optimizer.record_embed_latency(latency_ms, success)
                elif service == "qdrant":
                    optimizer.record_upsert_latency(latency_ms, success)
        return wrapper
    return decorator


# Singleton instance
batch_optimizer = BatchOptimizer()
