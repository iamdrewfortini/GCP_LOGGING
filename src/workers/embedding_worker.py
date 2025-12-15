"""
Embedding Worker

Continuous worker that processes embedding jobs from Redis queues.
Fetches logs from BigQuery, embeds them using Ollama, and upserts to Qdrant.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Generator

import httpx
from google.cloud import bigquery
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Ensure project root is in path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.services.redis_service import redis_service
from src.services.embedding_queue import embedding_queue, EmbeddingJob, QUEUE_BACKLOG
from src.services.batch_optimizer import batch_optimizer

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_EMBED_MODEL = "qwen3-embedding:0.6b"
DEFAULT_COLLECTION = "logs_embedded_qwen3"
DEFAULT_VECTOR_SIZE = 1024  # qwen3 dimension

MAX_TEXT_LENGTH = 8000
MAX_RETRIES = 3
RETRY_DELAY = 2.0


@dataclass
class LogEntry:
    """Structured log entry with trace elements."""
    log_id: str
    timestamp: datetime
    severity: str
    service_name: str
    resource_type: str
    table_name: str
    dataset: str

    text_payload: Optional[str] = None
    json_payload: Optional[Dict[str, Any]] = None
    proto_payload: Optional[Dict[str, Any]] = None

    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    trace_sampled: Optional[bool] = None

    http_request: Optional[Dict[str, Any]] = None
    labels: Dict[str, Any] = field(default_factory=dict)
    resource_labels: Dict[str, Any] = field(default_factory=dict)
    source_location: Optional[Dict[str, Any]] = None
    operation: Optional[Dict[str, Any]] = None

    def get_full_trace_text(self) -> str:
        """Construct full trace element text for embedding."""
        parts = []

        ts_str = self.timestamp.isoformat() if self.timestamp else "unknown_time"
        parts.append(f"[{ts_str}] [{self.severity}] [{self.service_name}]")

        if self.text_payload:
            text = self.text_payload
            if len(text) > 4000:
                text = text[:4000] + "... [truncated]"
            parts.append(f"Message: {text}")

        if self.json_payload:
            try:
                json_str = json.dumps(self.json_payload, indent=None, default=str)
                if len(json_str) > 2000:
                    json_str = json_str[:2000] + "... [truncated]"
                parts.append(f"JSON: {json_str}")
            except Exception:
                j = str(self.json_payload)
                if len(j) > 2000:
                    j = j[:2000] + "... [truncated]"
                parts.append(f"JSON: {j}")

        if self.proto_payload:
            p = str(self.proto_payload)
            if len(p) > 1000:
                p = p[:1000] + "... [truncated]"
            parts.append(f"Proto: {p}")

        if self.trace_id:
            parts.append(f"Trace: {self.trace_id}")
            if self.span_id:
                parts.append(f"Span: {self.span_id}")

        if self.http_request:
            req_method = self.http_request.get('requestMethod', '')
            req_url = self.http_request.get('requestUrl', '')
            status = self.http_request.get('status', '')
            if req_method and req_url:
                parts.append(f"HTTP: {req_method} {req_url} {status}")

        if self.source_location:
            file = self.source_location.get('file', '')
            line = self.source_location.get('line', '')
            if file:
                parts.append(f"Source: {file}:{line}")

        if self.labels:
            label_str = " ".join([f"{k}={v}" for k, v in list(self.labels.items())[:5]])
            parts.append(f"Labels: {label_str}")

        parts.append(f"Resource: {self.resource_type}")
        if self.resource_labels:
            res_str = " ".join([f"{k}={v}" for k, v in list(self.resource_labels.items())[:3]])
            parts.append(f"ResourceLabels: {res_str}")

        out = " | ".join(parts)
        if len(out) > MAX_TEXT_LENGTH:
            out = out[:MAX_TEXT_LENGTH] + "... [truncated]"
        return out

    def to_qdrant_payload(self) -> Dict[str, Any]:
        """Convert to Qdrant payload with hierarchical metadata."""
        return {
            "log_id": self.log_id,
            "timestamp": {
                "iso": self.timestamp.isoformat() if self.timestamp else None,
                "year": self.timestamp.year if self.timestamp else None,
                "month": self.timestamp.month if self.timestamp else None,
                "day": self.timestamp.day if self.timestamp else None,
                "hour": self.timestamp.hour if self.timestamp else None,
            },
            "severity": self.severity,
            "service_name": self.service_name,
            "resource_type": self.resource_type,
            "table_name": self.table_name,
            "dataset": self.dataset,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "labels": self.labels,
            "resource_labels": self.resource_labels,
            "text_payload": self.text_payload[:500] if self.text_payload else None,
            "has_json": bool(self.json_payload),
            "has_http_request": bool(self.http_request),
            "source_file": self.source_location.get('file') if self.source_location else None,
        }


class OllamaEmbedder:
    """Ollama embedding client with metrics recording."""

    def __init__(self, model: str = DEFAULT_EMBED_MODEL, host: Optional[str] = None):
        self.model = model
        self.host = (host or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        self.embed_url = f"{self.host}/api/embed"
        self.vector_size = DEFAULT_VECTOR_SIZE
        logger.info(f"Initialized Ollama embedder: {self.model} @ {self.host}")

    def embed_single(self, text: str) -> List[float]:
        """Embed a single text with metrics recording."""
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "... [truncated]"

        start = time.time()
        success = True

        for attempt in range(MAX_RETRIES):
            try:
                payload = {"model": self.model, "input": text}
                with httpx.Client(timeout=90.0) as client:
                    resp = client.post(self.embed_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                emb = data.get("embeddings")
                if not emb or not isinstance(emb, list) or not emb[0]:
                    success = False
                    return [0.0] * self.vector_size

                # Update vector size from actual response
                if emb[0]:
                    self.vector_size = len(emb[0])

                return emb[0]

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                    backoff = RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Ollama {e.response.status_code} — retrying in {backoff}s")
                    time.sleep(backoff)
                    continue
                logger.error(f"HTTP error from Ollama: {e}")
                success = False
                return [0.0] * self.vector_size
            except Exception as e:
                logger.error(f"Embed error: {e}")
                success = False
                return [0.0] * self.vector_size
            finally:
                latency_ms = (time.time() - start) * 1000
                batch_optimizer.record_embed_latency(latency_ms, success)

        return [0.0] * self.vector_size

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts."""
        return [self.embed_single(t) for t in texts]


class QdrantUpserter:
    """Qdrant upserter with metrics recording."""

    def __init__(self, collection: str = DEFAULT_COLLECTION, vector_size: int = DEFAULT_VECTOR_SIZE):
        self.collection = collection
        self.vector_size = vector_size
        self.url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.api_key = os.getenv("QDRANT_API_KEY")
        self.client = QdrantClient(url=self.url, api_key=self.api_key, timeout=60.0)
        self._ensure_collection()
        logger.info(f"Initialized Qdrant upserter: {self.url} -> {self.collection}")

    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        try:
            collections = [c.name for c in self.client.get_collections().collections]
            if self.collection not in collections:
                logger.info(f"Creating Qdrant collection: {self.collection}")
                self.client.create_collection(
                    collection_name=self.collection,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE
                    )
                )
                # Create payload indexes
                for field in ["severity", "service_name", "resource_type", "dataset", "table_name"]:
                    self.client.create_payload_index(
                        collection_name=self.collection,
                        field_name=field,
                        field_schema=models.PayloadSchemaType.KEYWORD
                    )
                for field in ["timestamp.year", "timestamp.month", "timestamp.day", "timestamp.hour"]:
                    self.client.create_payload_index(
                        collection_name=self.collection,
                        field_name=field,
                        field_schema=models.PayloadSchemaType.INTEGER
                    )
                logger.info(f"Created collection {self.collection} with indexes")
        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")

    def upsert_batch(self, logs: List[LogEntry], embeddings: List[List[float]]) -> int:
        """Upsert a batch of log embeddings with metrics recording."""
        if not logs or not embeddings:
            return 0

        start = time.time()
        success = True

        try:
            points = [
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload=log.to_qdrant_payload()
                )
                for log, emb in zip(logs, embeddings)
                if emb and any(v != 0.0 for v in emb)  # Skip zero vectors
            ]

            if not points:
                return 0

            for attempt in range(MAX_RETRIES):
                try:
                    self.client.upsert(
                        collection_name=self.collection,
                        points=points,
                        wait=True
                    )
                    logger.info(f"Upserted {len(points)} points to {self.collection}")
                    return len(points)
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        backoff = RETRY_DELAY * (2 ** attempt)
                        logger.warning(f"Qdrant upsert error, retrying in {backoff}s: {e}")
                        time.sleep(backoff)
                        continue
                    raise

        except Exception as e:
            logger.error(f"Upsert error: {e}")
            success = False
            return 0
        finally:
            latency_ms = (time.time() - start) * 1000
            batch_optimizer.record_upsert_latency(latency_ms, success)

        return 0


class BigQueryLogFetcher:
    """Fetch logs from BigQuery."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.client = bigquery.Client(project=project_id)
        logger.info(f"Initialized BigQuery client for project: {project_id}")

    def fetch_logs(self, table: str, offset: int, limit: int) -> List[LogEntry]:
        """Fetch logs from a specific table."""
        # Parse table name
        parts = table.split(".")
        if len(parts) == 2:
            dataset, table_name = parts
            full_table = f"{self.project_id}.{dataset}.{table_name}"
        else:
            full_table = table
            parts = table.split(".")
            dataset = parts[-2] if len(parts) >= 2 else "unknown"
            table_name = parts[-1]

        # Get schema to determine available fields
        try:
            table_ref = self.client.get_table(full_table)
            schema_fields = {f.name for f in table_ref.schema}
        except Exception as e:
            logger.error(f"Error getting table schema: {e}")
            return []

        # Build query based on available fields
        select_fields = ["timestamp", "severity"]

        # Optional fields
        optional_fields = [
            "textPayload", "jsonPayload", "protoPayload",
            "trace", "spanId", "traceSampled",
            "httpRequest", "labels", "resource", "sourceLocation", "operation"
        ]

        for field in optional_fields:
            if field in schema_fields:
                select_fields.append(field)

        query = f"""
            SELECT {", ".join(select_fields)}
            FROM `{full_table}`
            ORDER BY timestamp DESC
            LIMIT {limit}
            OFFSET {offset}
        """

        try:
            results = self.client.query(query).result()
            logs = []

            for row in results:
                # Extract resource labels
                resource = dict(row.get("resource", {}) or {})
                resource_type = resource.get("type", "unknown")
                resource_labels = dict(resource.get("labels", {}) or {})

                # Extract service name
                service_name = (
                    resource_labels.get("service_name") or
                    resource_labels.get("service") or
                    resource_labels.get("function_name") or
                    resource_type
                )

                log = LogEntry(
                    log_id=str(uuid.uuid4()),
                    timestamp=row.get("timestamp"),
                    severity=row.get("severity", "DEFAULT"),
                    service_name=service_name,
                    resource_type=resource_type,
                    table_name=table_name,
                    dataset=dataset,
                    text_payload=row.get("textPayload"),
                    json_payload=dict(row.get("jsonPayload", {}) or {}),
                    proto_payload=dict(row.get("protoPayload", {}) or {}),
                    trace_id=row.get("trace"),
                    span_id=row.get("spanId"),
                    trace_sampled=row.get("traceSampled"),
                    http_request=dict(row.get("httpRequest", {}) or {}),
                    labels=dict(row.get("labels", {}) or {}),
                    resource_labels=resource_labels,
                    source_location=dict(row.get("sourceLocation", {}) or {}),
                    operation=dict(row.get("operation", {}) or {}),
                )
                logs.append(log)

            return logs

        except Exception as e:
            logger.error(f"Error fetching logs from {full_table}: {e}")
            return []

    def discover_log_tables(self, datasets: Optional[List[str]] = None, hours: int = 24) -> List[Dict]:
        """Discover all log tables with recent data."""
        tables = []
        target_datasets = datasets or [ds.dataset_id for ds in self.client.list_datasets()]

        for dataset_id in target_datasets:
            try:
                dataset_ref = self.client.dataset(dataset_id)
                for table in self.client.list_tables(dataset_ref):
                    table_ref = dataset_ref.table(table.table_id)
                    table_obj = self.client.get_table(table_ref)

                    if table_obj.num_rows == 0:
                        continue

                    schema_fields = {f.name for f in table_obj.schema}
                    if not any(field in schema_fields for field in ['timestamp', 'severity', 'logName']):
                        continue

                    # Check for recent data
                    cutoff = datetime.utcnow() - timedelta(hours=hours)
                    count_query = f"""
                        SELECT COUNT(*) as cnt
                        FROM `{self.project_id}.{dataset_id}.{table.table_id}`
                        WHERE timestamp >= '{cutoff.isoformat()}'
                    """
                    try:
                        result = list(self.client.query(count_query).result())
                        recent_count = result[0].cnt if result else 0
                    except:
                        recent_count = table_obj.num_rows

                    if recent_count > 0:
                        tables.append({
                            "dataset": dataset_id,
                            "table": table.table_id,
                            "full_name": f"{dataset_id}.{table.table_id}",
                            "row_count": recent_count
                        })
                        logger.info(f"Discovered: {dataset_id}.{table.table_id} ({recent_count} rows)")

            except Exception as e:
                logger.warning(f"Error scanning dataset {dataset_id}: {e}")

        return tables


class EmbeddingWorker:
    """
    Main embedding worker that processes jobs from Redis queues.

    Implements a continuous polling loop that:
    1. Dequeues jobs from priority/backlog queues
    2. Fetches logs from BigQuery
    3. Embeds logs using Ollama
    4. Upserts embeddings to Qdrant
    5. Updates checkpoints and enqueues next batch
    """

    def __init__(
        self,
        project_id: str = None,
        embed_model: str = DEFAULT_EMBED_MODEL,
        collection: str = DEFAULT_COLLECTION,
        vector_size: int = DEFAULT_VECTOR_SIZE,
    ):
        self.project_id = project_id or os.getenv("PROJECT_ID", "diatonic-ai-gcp")
        self.running = False
        self.jobs_processed = 0
        self.logs_embedded = 0

        # Initialize components
        self.bq_fetcher = BigQueryLogFetcher(self.project_id)
        self.embedder = OllamaEmbedder(model=embed_model)
        self.upserter = QdrantUpserter(collection=collection, vector_size=vector_size)

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)

        logger.info(f"Initialized EmbeddingWorker for project {self.project_id}")

    def _shutdown_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False

    async def run(self, poll_interval: float = 1.0):
        """
        Main worker loop.

        Args:
            poll_interval: Seconds to wait when no jobs available
        """
        self.running = True
        logger.info("Starting embedding worker loop...")

        while self.running:
            try:
                # Dequeue next job (priority first, then backlog)
                job = embedding_queue.dequeue(timeout=1)

                if job:
                    await self.process_job(job)
                else:
                    # No jobs, wait before next poll
                    await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying

        logger.info(f"Worker stopped. Processed {self.jobs_processed} jobs, {self.logs_embedded} logs")

    async def process_job(self, job: EmbeddingJob):
        """Process a single embedding job."""
        logger.info(f"Processing job {job.job_id}: {job.table} @ offset {job.offset}")

        try:
            # 1. Fetch logs from BigQuery
            logs = self.bq_fetcher.fetch_logs(job.table, job.offset, job.batch_size)

            if not logs:
                logger.info(f"No logs found for {job.table} at offset {job.offset}")
                return

            # 2. Generate trace texts
            texts = [log.get_full_trace_text() for log in logs]

            # 3. Embed in optimal batch sizes
            embed_batch_size = batch_optimizer.embed_batch_size
            embeddings = []

            for i in range(0, len(texts), embed_batch_size):
                batch_texts = texts[i:i + embed_batch_size]
                batch_embeddings = self.embedder.embed_batch(batch_texts)
                embeddings.extend(batch_embeddings)

                # Yield to event loop
                await asyncio.sleep(0)

            # 4. Upsert to Qdrant in optimal batch sizes
            upsert_batch_size = batch_optimizer.upsert_batch_size
            total_upserted = 0

            for i in range(0, len(logs), upsert_batch_size):
                batch_logs = logs[i:i + upsert_batch_size]
                batch_embeddings = embeddings[i:i + upsert_batch_size]
                upserted = self.upserter.upsert_batch(batch_logs, batch_embeddings)
                total_upserted += upserted

                # Yield to event loop
                await asyncio.sleep(0)

            # 5. Update checkpoint
            new_offset = job.offset + len(logs)
            redis_service.set_checkpoint(job.table, new_offset)

            # 6. Enqueue next batch if more rows exist
            if len(logs) >= job.batch_size:
                embedding_queue.enqueue_next_batch(job, len(logs))

            # 7. Update global progress
            self.jobs_processed += 1
            self.logs_embedded += total_upserted

            global_checkpoint = redis_service.get_global_checkpoint() or {}
            redis_service.set_global_checkpoint(
                tables_completed=global_checkpoint.get("tables_completed", 0),
                total_embedded=global_checkpoint.get("total_embedded", 0) + total_upserted
            )

            logger.info(f"Completed job {job.job_id}: {total_upserted} logs embedded")

        except Exception as e:
            logger.error(f"Error processing job {job.job_id}: {e}")
            job.retry_count += 1

            if job.retry_count < MAX_RETRIES:
                # Re-enqueue for retry
                embedding_queue.enqueue(job)
                logger.info(f"Re-enqueued job {job.job_id} (retry {job.retry_count})")
            else:
                # Move to failed queue
                embedding_queue.mark_failed(job, str(e))
                logger.error(f"Job {job.job_id} failed after {MAX_RETRIES} retries")

    def get_status(self) -> Dict:
        """Get current worker status."""
        queue_stats = embedding_queue.get_queue_stats()
        optimizer_stats = batch_optimizer.get_stats()
        global_checkpoint = redis_service.get_global_checkpoint() or {}

        return {
            "running": self.running,
            "jobs_processed": self.jobs_processed,
            "logs_embedded": self.logs_embedded,
            "queues": queue_stats,
            "optimizer": optimizer_stats,
            "global_progress": global_checkpoint
        }


def run_worker():
    """Entry point for running the worker."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    worker = EmbeddingWorker()

    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")


if __name__ == "__main__":
    run_worker()
