"""
Embedding Queue Service

Manages Redis-based job queues for the embedding worker pipeline.
Handles job creation, prioritization, and dead letter queue management.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict

from src.services.redis_service import redis_service

logger = logging.getLogger(__name__)

# Queue names
QUEUE_PRIORITY = "q:embed:priority"    # High priority (manual triggers)
QUEUE_BACKLOG = "q:embed:backlog"      # Normal priority (batch processing)
QUEUE_FAILED = "q:embed:failed"        # Dead letter queue


@dataclass
class EmbeddingJob:
    """Represents an embedding job to be processed."""
    job_id: str
    table: str
    offset: int
    batch_size: int
    created_at: str
    retry_count: int = 0
    priority: bool = False

    @classmethod
    def create(cls, table: str, offset: int, batch_size: int = 50, priority: bool = False) -> "EmbeddingJob":
        """Factory method to create a new job."""
        return cls(
            job_id=str(uuid.uuid4()),
            table=table,
            offset=offset,
            batch_size=batch_size,
            created_at=datetime.utcnow().isoformat(),
            retry_count=0,
            priority=priority
        )

    @classmethod
    def from_dict(cls, data: Dict) -> "EmbeddingJob":
        """Create job from dictionary."""
        return cls(
            job_id=data.get("job_id", str(uuid.uuid4())),
            table=data["table"],
            offset=data["offset"],
            batch_size=data.get("batch_size", 50),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            retry_count=data.get("retry_count", 0),
            priority=data.get("priority", False)
        )

    def to_dict(self) -> Dict:
        """Convert job to dictionary for serialization."""
        return asdict(self)


class EmbeddingQueueService:
    """
    Service for managing embedding job queues.

    Implements a priority-based queue system:
    - Priority queue: For manual/urgent embedding requests
    - Backlog queue: For batch processing of BigQuery logs
    - Failed queue: Dead letter queue for failed jobs
    """

    def __init__(self):
        self.redis = redis_service

    def enqueue(self, job: EmbeddingJob) -> bool:
        """
        Add a job to the appropriate queue based on priority.

        Args:
            job: The embedding job to enqueue

        Returns:
            True if successfully enqueued, False otherwise
        """
        queue = QUEUE_PRIORITY if job.priority else QUEUE_BACKLOG
        success = self.redis.enqueue(queue, job.to_dict())
        if success:
            logger.debug(f"Enqueued job {job.job_id} for {job.table} at offset {job.offset}")
        return success

    def enqueue_table(self, table: str, offset: int = 0, batch_size: int = 50, priority: bool = False) -> Optional[str]:
        """
        Convenience method to enqueue a table for embedding.

        Args:
            table: Full table name (dataset.table)
            offset: Starting offset
            batch_size: Number of logs per batch
            priority: If True, use priority queue

        Returns:
            Job ID if successful, None otherwise
        """
        job = EmbeddingJob.create(table, offset, batch_size, priority)
        if self.enqueue(job):
            return job.job_id
        return None

    def dequeue(self, timeout: int = 1) -> Optional[EmbeddingJob]:
        """
        Dequeue the next job, prioritizing the priority queue.

        Args:
            timeout: Blocking timeout in seconds

        Returns:
            EmbeddingJob if available, None otherwise
        """
        # Try priority queue first (non-blocking)
        job_data = self.redis.dequeue(QUEUE_PRIORITY, timeout=0)
        if job_data:
            logger.debug(f"Dequeued priority job: {job_data.get('job_id')}")
            return EmbeddingJob.from_dict(job_data)

        # Fall back to backlog queue (blocking)
        job_data = self.redis.dequeue(QUEUE_BACKLOG, timeout=timeout)
        if job_data:
            logger.debug(f"Dequeued backlog job: {job_data.get('job_id')}")
            return EmbeddingJob.from_dict(job_data)

        return None

    def mark_failed(self, job: EmbeddingJob, error: str) -> bool:
        """
        Move a job to the failed queue.

        Args:
            job: The failed job
            error: Error message

        Returns:
            True if successfully moved, False otherwise
        """
        queue = QUEUE_PRIORITY if job.priority else QUEUE_BACKLOG
        return self.redis.move_to_failed(queue, job.to_dict(), error)

    def retry_failed(self, count: int = 10, to_priority: bool = False) -> int:
        """
        Move failed jobs back to a processing queue.

        Args:
            count: Maximum number of jobs to retry
            to_priority: If True, move to priority queue

        Returns:
            Number of jobs moved
        """
        target_queue = QUEUE_PRIORITY if to_priority else QUEUE_BACKLOG
        return self.redis.retry_failed_jobs(target_queue, count)

    def get_queue_stats(self) -> Dict[str, int]:
        """
        Get statistics about all queues.

        Returns:
            Dictionary with queue lengths
        """
        return {
            "priority": self.redis.queue_length(QUEUE_PRIORITY),
            "backlog": self.redis.queue_length(QUEUE_BACKLOG),
            "failed": self.redis.queue_length(QUEUE_FAILED),
            "total_pending": (
                self.redis.queue_length(QUEUE_PRIORITY) +
                self.redis.queue_length(QUEUE_BACKLOG)
            )
        }

    def peek_queues(self, count: int = 5) -> Dict[str, List[Dict]]:
        """
        Peek at jobs in all queues without removing them.

        Args:
            count: Number of jobs to peek per queue

        Returns:
            Dictionary with queue previews
        """
        return {
            "priority": self.redis.peek_queue(QUEUE_PRIORITY, count),
            "backlog": self.redis.peek_queue(QUEUE_BACKLOG, count),
            "failed": self.redis.peek_queue(QUEUE_FAILED, count)
        }

    def clear_all_queues(self) -> Dict[str, int]:
        """
        Clear all embedding queues.

        Returns:
            Dictionary with counts of cleared items per queue
        """
        return {
            "priority": self.redis.clear_queue(QUEUE_PRIORITY),
            "backlog": self.redis.clear_queue(QUEUE_BACKLOG),
            "failed": self.redis.clear_queue(QUEUE_FAILED)
        }

    def enqueue_next_batch(self, completed_job: EmbeddingJob, rows_processed: int) -> Optional[str]:
        """
        Enqueue the next batch for a table after processing.

        Args:
            completed_job: The job that was just completed
            rows_processed: Number of rows actually processed

        Returns:
            New job ID if enqueued, None if no more batches needed
        """
        # Only enqueue next if we processed a full batch (more rows likely exist)
        if rows_processed >= completed_job.batch_size:
            new_offset = completed_job.offset + rows_processed
            return self.enqueue_table(
                table=completed_job.table,
                offset=new_offset,
                batch_size=completed_job.batch_size,
                priority=completed_job.priority
            )
        return None


# Singleton instance
embedding_queue = EmbeddingQueueService()
