#!/usr/bin/env python3
"""Batch Embedding and Upserting Pipeline: BigQuery Logs → Qdrant

This script:
1. Queries BigQuery for logs across all tables and services
2. Constructs full trace elements from structured log data
3. Batches logs for efficient embedding via Ollama
4. Embeds log content using local Ollama models
5. Upserts embeddings to Qdrant with rich metadata

Features:
- Multi-table querying across datasets
- Configurable batch sizes for memory efficiency
- Full trace reconstruction (structured + metadata)
- Checkpointing for resumable processing
- Parallel batching with progress tracking
- Error handling with retry logic
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Generator
from collections import defaultdict

import httpx
from dotenv import load_dotenv
from google.cloud import bigquery
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Setup paths and environment
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("batch_embed_logs")

# Configuration
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_BATCH_SIZE = 100
DEFAULT_EMBED_BATCH_SIZE = 10
DEFAULT_COLLECTION = "logs_embedded"
DEFAULT_VECTOR_SIZE = 768

# Rate limiting and safety
OLLAMA_RATE_LIMIT = 2   # req/sec
QDRANT_RATE_LIMIT = 5   # req/sec
MAX_TEXT_LENGTH = 8000  # chars (conservative)
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds

# Checkpoint file for resumable processing
CHECKPOINT_FILE = REPO_ROOT / ".checkpoint_batch_embed.json"


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
    
    # Content fields
    text_payload: Optional[str] = None
    json_payload: Optional[Dict[str, Any]] = None
    proto_payload: Optional[Dict[str, Any]] = None
    
    # Trace fields
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    trace_sampled: Optional[bool] = None
    
    # HTTP request context
    http_request: Optional[Dict[str, Any]] = None
    
    # Labels and metadata
    labels: Dict[str, Any] = field(default_factory=dict)
    resource_labels: Dict[str, Any] = field(default_factory=dict)
    
    # Source location
    source_location: Optional[Dict[str, Any]] = None
    
    # Operation metadata
    operation: Optional[Dict[str, Any]] = None
    
    def get_full_trace_text(self) -> str:
        """Construct full trace element text for embedding with conservative truncation."""
        parts = []
        
        # 1. Timestamp and severity context
        ts_str = self.timestamp.isoformat() if self.timestamp else "unknown_time"
        parts.append(f"[{ts_str}] [{self.severity}] [{self.service_name}]")
        
        # 2. Main content (truncate big bodies)
        if self.text_payload:
            text = self.text_payload
            if len(text) > 4000:
                text = text[:4000] + "... [truncated]"
            parts.append(f"Message: {text}")
        
        if self.json_payload:
            # Flatten JSON payload into readable text
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
        
        # 3. Trace context
        if self.trace_id:
            parts.append(f"Trace: {self.trace_id}")
            if self.span_id:
                parts.append(f"Span: {self.span_id}")
        
        # 4. HTTP request context
        if self.http_request:
            req_method = self.http_request.get('requestMethod', '')
            req_url = self.http_request.get('requestUrl', '')
            status = self.http_request.get('status', '')
            if req_method and req_url:
                parts.append(f"HTTP: {req_method} {req_url} {status}")
        
        # 5. Source location
        if self.source_location:
            file = self.source_location.get('file', '')
            line = self.source_location.get('line', '')
            if file:
                parts.append(f"Source: {file}:{line}")
        
        # 6. Labels (selective)
        if self.labels:
            label_str = " ".join([f"{k}={v}" for k, v in list(self.labels.items())[:5]])
            parts.append(f"Labels: {label_str}")
        
        # 7. Resource context
        parts.append(f"Resource: {self.resource_type}")
        if self.resource_labels:
            res_str = " ".join([f"{k}={v}" for k, v in list(self.resource_labels.items())[:3]])
            parts.append(f"ResourceLabels: {res_str}")
        
        # Final cap for model stability
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
            "text_payload": self.text_payload[:500] if self.text_payload else None,  # Truncate for storage
            "has_json": bool(self.json_payload),
            "has_http_request": bool(self.http_request),
            "source_file": self.source_location.get('file') if self.source_location else None,
        }


class OllamaEmbedder:
    """Ollama embedding client with rate limiting and retries."""
    
    def __init__(self, model: str = DEFAULT_EMBED_MODEL, host: Optional[str] = None):
        self.model = model
        self.host = (host or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        self.embed_url = f"{self.host}/api/embed"
        self._last_req = 0.0
        self._delay = 1.0 / OLLAMA_RATE_LIMIT
        logger.info(f"Initialized Ollama embedder: {self.model} @ {self.host} (rate {OLLAMA_RATE_LIMIT}/s)")
    
    def _rate_limit(self):
        dt = time.time() - self._last_req
        if dt < self._delay:
            time.sleep(self._delay - dt)
        self._last_req = time.time()
    
    def _embed_once(self, text: str) -> List[float]:
        payload = {"model": self.model, "input": text}
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(self.embed_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        emb = data.get("embeddings")
        if not emb or not isinstance(emb, list) or not emb[0]:
            return [0.0] * DEFAULT_VECTOR_SIZE
        return emb[0]
    
    def embed_single(self, text: str) -> List[float]:
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "... [truncated]"
        for attempt in range(MAX_RETRIES):
            try:
                self._rate_limit()
                return self._embed_once(text)
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                    backoff = RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Ollama {e.response.status_code} — retrying in {backoff}s")
                    time.sleep(backoff)
                    continue
                logger.error(f"HTTP error from Ollama: {e}")
                return [0.0] * DEFAULT_VECTOR_SIZE
            except Exception as e:
                logger.error(f"Embed error: {e}")
                return [0.0] * DEFAULT_VECTOR_SIZE
        return [0.0] * DEFAULT_VECTOR_SIZE
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        out = []
        for i, t in enumerate(texts):
            if i and i % 10 == 0:
                logger.info(f"Embedded {i}/{len(texts)} texts...")
            out.append(self.embed_single(t))
        return out


class BigQueryLogFetcher:
    """Fetch logs from BigQuery across multiple datasets and tables."""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.client = bigquery.Client(project=project_id)
        logger.info(f"Initialized BigQuery client for project: {project_id}")
    
    def discover_log_tables(self, datasets: Optional[List[str]] = None) -> List[Dict[str, str]]:
        """Discover all log tables across datasets."""
        tables = []
        
        target_datasets = datasets or [ds.dataset_id for ds in self.client.list_datasets()]
        
        for dataset_id in target_datasets:
            try:
                dataset_ref = self.client.dataset(dataset_id)
                for table in self.client.list_tables(dataset_ref):
                    table_ref = dataset_ref.table(table.table_id)
                    table_obj = self.client.get_table(table_ref)
                    
                    # Skip empty tables and non-log tables
                    if table_obj.num_rows == 0:
                        continue
                    
                    # Check if table has log-like schema
                    schema_fields = {f.name for f in table_obj.schema}
                    if not any(field in schema_fields for field in ['timestamp', 'severity', 'logName']):
                        logger.debug(f"Skipping non-log table: {dataset_id}.{table.table_id}")
                        continue
                    
                    tables.append({
                        "dataset": dataset_id,
                        "table": table.table_id,
                        "full_name": f"{self.project_id}.{dataset_id}.{table.table_id}",
                        "row_count": table_obj.num_rows
                    })
                    logger.info(f"Discovered log table: {dataset_id}.{table.table_id} ({table_obj.num_rows} rows)")
            
            except Exception as e:
                logger.warning(f"Failed to list tables in dataset {dataset_id}: {e}")
        
        return tables
    
    def fetch_logs_from_table(
        self,
        dataset: str,
        table: str,
        hours: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Generator[LogEntry, None, None]:
        """Fetch logs from a specific table with optional time window."""
        
        full_table = f"`{self.project_id}.{dataset}.{table}`"
        
        # Build WHERE clause
        where_clauses = []
        if hours:
            where_clauses.append(f"timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)")
        
        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        # First, check table schema to determine available fields
        try:
            table_ref = self.client.get_table(f"{self.project_id}.{dataset}.{table}")
            schema_fields = {f.name for f in table_ref.schema}
        except Exception as e:
            logger.error(f"Failed to get table schema: {e}")
            return
        
        # Build SELECT clause based on available fields
        select_fields = []
        
        # Handle insertId (some tables don't have it)
        if "insertId" in schema_fields:
            select_fields.append("insertId as log_id")
        else:
            select_fields.append("GENERATE_UUID() as log_id")
        
        select_fields.extend([
            "timestamp",
            "severity",
            "resource.type as resource_type",
            "resource.labels as resource_labels",
        ])
        
        # Add optional fields only if they exist in schema
        if "logName" in schema_fields:
            select_fields.append("logName")
        if "textPayload" in schema_fields:
            select_fields.append("textPayload")
        else:
            select_fields.append("CAST(NULL AS STRING) as textPayload")
        
        if "jsonPayload" in schema_fields:
            select_fields.append("jsonPayload")
        else:
            select_fields.append("CAST(NULL AS STRING) as jsonPayload")
        
        if "protoPayload" in schema_fields:
            select_fields.append("protoPayload")
        else:
            select_fields.append("CAST(NULL AS STRING) as protoPayload")
        
        if "labels" in schema_fields:
            select_fields.append("labels")
        if "trace" in schema_fields:
            select_fields.append("trace")
        if "spanId" in schema_fields:
            select_fields.append("spanId")
        if "traceSampled" in schema_fields:
            select_fields.append("traceSampled")
        if "httpRequest" in schema_fields:
            select_fields.append("httpRequest")
        if "sourceLocation" in schema_fields:
            select_fields.append("sourceLocation")
        if "operation" in schema_fields:
            select_fields.append("operation")
        
        # Build query
        query = f"""
            SELECT
                {', '.join(select_fields)}
            FROM {full_table}
            {where_clause}
            ORDER BY timestamp DESC
            {"LIMIT " + str(limit) if limit else ""}
            {"OFFSET " + str(offset) if offset else ""}
        """
        
        logger.info(f"Querying {full_table} (offset={offset}, limit={limit})...")
        
        try:
            query_job = self.client.query(query)
            
            for row in query_job:
                # Extract service name from resource labels or logName
                service_name = "unknown"
                resource_labels = dict(row.resource_labels) if hasattr(row, 'resource_labels') and row.resource_labels else {}
                if resource_labels:
                    service_name = (
                        resource_labels.get("service_name") or
                        resource_labels.get("function_name") or
                        resource_labels.get("job") or
                        "unknown"
                    )
                
                # Safely get optional fields
                text_payload = getattr(row, 'textPayload', None)
                json_payload = dict(row.jsonPayload) if hasattr(row, 'jsonPayload') and row.jsonPayload else None
                proto_payload = dict(row.protoPayload) if hasattr(row, 'protoPayload') and row.protoPayload else None
                trace_id = getattr(row, 'trace', None)
                span_id = getattr(row, 'spanId', None)
                trace_sampled = getattr(row, 'traceSampled', None)
                http_request = dict(row.httpRequest) if hasattr(row, 'httpRequest') and row.httpRequest else None
                labels = dict(row.labels) if hasattr(row, 'labels') and row.labels else {}
                source_location = dict(row.sourceLocation) if hasattr(row, 'sourceLocation') and row.sourceLocation else None
                operation = dict(row.operation) if hasattr(row, 'operation') and row.operation else None
                
                yield LogEntry(
                    log_id=row.log_id or str(uuid.uuid4()),
                    timestamp=row.timestamp,
                    severity=row.severity or "DEFAULT",
                    service_name=service_name,
                    resource_type=row.resource_type or "unknown",
                    table_name=table,
                    dataset=dataset,
                    text_payload=text_payload,
                    json_payload=json_payload,
                    proto_payload=proto_payload,
                    trace_id=trace_id,
                    span_id=span_id,
                    trace_sampled=trace_sampled,
                    http_request=http_request,
                    labels=labels,
                    resource_labels=resource_labels,
                    source_location=source_location,
                    operation=operation,
                )
        
        except Exception as e:
            logger.error(f"Failed to fetch logs from {full_table}: {e}")

    def fetch_logs_from_master(
        self,
        hours: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        stream_id: Optional[str] = None
    ) -> Generator[LogEntry, None, None]:
        """Fetch logs from the centralized master_logs table.

        This is more efficient than querying individual tables since all logs
        are already normalized and centralized.
        """
        from datetime import datetime, timedelta

        master_table = f"`{self.project_id}.central_logging_v1.master_logs`"

        # Build WHERE clause with partition filter for performance
        where_clauses = []
        if hours:
            start_date = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d")
            end_date = datetime.utcnow().strftime("%Y-%m-%d")
            where_clauses.append(f"log_date BETWEEN '{start_date}' AND '{end_date}'")
            where_clauses.append(f"event_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)")

        if stream_id:
            where_clauses.append(f"stream_id = '{stream_id}'")

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Select fields from master_logs schema
        query = f"""
            SELECT
                log_id,
                event_timestamp,
                severity,
                service_name,
                resource_type,
                source_table,
                stream_id,
                text_payload,
                json_payload,
                proto_payload,
                trace_id,
                span_id,
                trace_sampled,
                http_method,
                http_url,
                http_status,
                http_latency_ms,
                http_user_agent,
                http_remote_ip,
                http_request_size,
                http_response_size,
                labels,
                resource_labels,
                source_file,
                source_line,
                source_function,
                operation_id,
                operation_producer,
                message
            FROM {master_table}
            {where_clause}
            ORDER BY event_timestamp DESC
            {"LIMIT " + str(limit) if limit else ""}
            {"OFFSET " + str(offset) if offset else ""}
        """

        logger.info(f"Querying master_logs (offset={offset}, limit={limit}, stream={stream_id})...")

        try:
            query_job = self.client.query(query)

            for row in query_job:
                # Parse JSON fields
                json_payload = None
                if row.json_payload:
                    try:
                        json_payload = json.loads(row.json_payload) if isinstance(row.json_payload, str) else row.json_payload
                    except:
                        pass

                proto_payload = None
                if row.proto_payload:
                    try:
                        proto_payload = json.loads(row.proto_payload) if isinstance(row.proto_payload, str) else row.proto_payload
                    except:
                        pass

                labels = {}
                if row.labels:
                    try:
                        labels = json.loads(row.labels) if isinstance(row.labels, str) else row.labels
                    except:
                        pass

                resource_labels = {}
                if row.resource_labels:
                    try:
                        resource_labels = json.loads(row.resource_labels) if isinstance(row.resource_labels, str) else row.resource_labels
                    except:
                        pass

                # Build HTTP request dict if available
                http_request = None
                if row.http_method or row.http_url or row.http_status:
                    http_request = {
                        "requestMethod": row.http_method,
                        "requestUrl": row.http_url,
                        "status": row.http_status,
                        "latency": f"{row.http_latency_ms / 1000}s" if row.http_latency_ms else None,
                        "userAgent": row.http_user_agent,
                        "remoteIp": row.http_remote_ip,
                        "requestSize": row.http_request_size,
                        "responseSize": row.http_response_size,
                    }

                # Build source location if available
                source_location = None
                if row.source_file or row.source_line or row.source_function:
                    source_location = {
                        "file": row.source_file,
                        "line": row.source_line,
                        "function": row.source_function,
                    }

                # Build operation if available
                operation = None
                if row.operation_id or row.operation_producer:
                    operation = {
                        "id": row.operation_id,
                        "producer": row.operation_producer,
                    }

                # Extract dataset and table from stream_id
                stream_parts = (row.stream_id or "unknown.unknown").split(".")
                dataset = stream_parts[0] if len(stream_parts) > 0 else "unknown"
                table_name = stream_parts[1] if len(stream_parts) > 1 else "unknown"

                yield LogEntry(
                    log_id=row.log_id or str(uuid.uuid4()),
                    timestamp=row.event_timestamp,
                    severity=row.severity or "DEFAULT",
                    service_name=row.service_name or "unknown",
                    resource_type=row.resource_type or "unknown",
                    table_name=table_name,
                    dataset=dataset,
                    text_payload=row.text_payload or row.message,
                    json_payload=json_payload,
                    proto_payload=proto_payload,
                    trace_id=row.trace_id,
                    span_id=row.span_id,
                    trace_sampled=row.trace_sampled,
                    http_request=http_request,
                    labels=labels,
                    resource_labels=resource_labels,
                    source_location=source_location,
                    operation=operation,
                )

        except Exception as e:
            logger.error(f"Failed to fetch logs from master_logs: {e}")

    def get_master_logs_count(self, hours: Optional[int] = None, stream_id: Optional[str] = None) -> int:
        """Get count of logs in master_logs table."""
        from datetime import datetime, timedelta

        master_table = f"`{self.project_id}.central_logging_v1.master_logs`"

        where_clauses = []
        if hours:
            start_date = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d")
            end_date = datetime.utcnow().strftime("%Y-%m-%d")
            where_clauses.append(f"log_date BETWEEN '{start_date}' AND '{end_date}'")

        if stream_id:
            where_clauses.append(f"stream_id = '{stream_id}'")

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"SELECT COUNT(*) as cnt FROM {master_table} {where_clause}"

        try:
            result = list(self.client.query(query).result())
            return result[0].cnt if result else 0
        except Exception as e:
            logger.error(f"Failed to count master_logs: {e}")
            return 0


class QdrantUpserter:
    """Upsert embeddings to Qdrant with collection management and rate limiting."""
    
    def __init__(
        self,
        collection_name: str = DEFAULT_COLLECTION,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        url: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        self._last_req = 0.0
        self._delay = 1.0 / QDRANT_RATE_LIMIT
        
        self.client = QdrantClient(url=self.url, api_key=self.api_key, timeout=60.0)
        logger.info(f"Initialized Qdrant client: {self.url} (rate {QDRANT_RATE_LIMIT}/s)")
        
        self._ensure_collection()
        self._log_collection_stats()
    
    def _ensure_collection(self):
        """Create collection if it doesn't exist. If exists with different dimension, use a suffixed name."""
        collections = self.client.get_collections()
        names = [c.name for c in collections.collections]
        exists = self.collection_name in names
        
        if exists:
            try:
                info = self.client.get_collection(self.collection_name)
                current_size = info.config.params.vectors.size
                if int(current_size) != int(self.vector_size):
                    # Auto-switch collection name to avoid dimension mismatch
                    if self.collection_name == DEFAULT_COLLECTION and self.vector_size == 1024:
                        new_name = "logs_embedded_qwen3"
                    else:
                        new_name = f"{self.collection_name}_v{self.vector_size}"
                    logger.warning(
                        f"Collection '{self.collection_name}' exists with dim {current_size} != {self.vector_size}. "
                        f"Switching to '{new_name}'."
                    )
                    self.collection_name = new_name
                    exists = self.collection_name in names
            except Exception as e:
                logger.warning(f"Could not inspect existing collection: {e}")
                
        if not exists:
            logger.info(f"Creating Qdrant collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE
                )
            )
            
            # Create indexes for common filter fields
            index_fields = [
                ("severity", models.PayloadSchemaType.KEYWORD),
                ("service_name", models.PayloadSchemaType.KEYWORD),
                ("resource_type", models.PayloadSchemaType.KEYWORD),
                ("dataset", models.PayloadSchemaType.KEYWORD),
                ("table_name", models.PayloadSchemaType.KEYWORD),
                ("timestamp.year", models.PayloadSchemaType.INTEGER),
                ("timestamp.month", models.PayloadSchemaType.INTEGER),
                ("timestamp.day", models.PayloadSchemaType.INTEGER),
                ("timestamp.hour", models.PayloadSchemaType.INTEGER),
            ]
            
            for field_name, field_type in index_fields:
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field_name,
                        field_schema=field_type
                    )
                except Exception as e:
                    logger.warning(f"Failed to create index for {field_name}: {e}")
            
            logger.info(f"Created collection {self.collection_name} with indexes")
        else:
            logger.info(f"Collection {self.collection_name} already exists and is compatible")
    
    def _rate_limit(self):
        dt = time.time() - self._last_req
        if dt < self._delay:
            time.sleep(self._delay - dt)
        self._last_req = time.time()
    
    def _log_collection_stats(self):
        try:
            info = self.client.get_collection(self.collection_name)
            logger.info(f"📊 Collection '{self.collection_name}': {info.points_count:,} vectors, dim={info.config.params.vectors.size}")
        except Exception as e:
            logger.warning(f"Could not read collection stats: {e}")
    
    def upsert_batch(self, log_entries: List[LogEntry], embeddings: List[List[float]]):
        """Upsert a batch of log embeddings to Qdrant with rate limiting and retry."""
        if len(log_entries) != len(embeddings):
            raise ValueError("Mismatch between log entries and embeddings count")
        
        points = []
        for log_entry, embedding in zip(log_entries, embeddings):
            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload=log_entry.to_qdrant_payload(),
                )
            )
        
        for attempt in range(MAX_RETRIES):
            try:
                self._rate_limit()
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                    wait=True,
                )
                logger.info(f"✅ Upserted {len(points)} points to {self.collection_name}")
                return
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    backoff = RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Qdrant upsert error, retrying in {backoff}s: {e}")
                    time.sleep(backoff)
                    continue
                logger.error(f"Failed to upsert batch after {MAX_RETRIES} retries: {e}")
                raise


class CheckpointManager:
    """Manage processing checkpoints for resumability."""
    
    def __init__(self, checkpoint_file: Path = CHECKPOINT_FILE):
        self.checkpoint_file = checkpoint_file
        self.checkpoint = self._load()
    
    def _load(self) -> Dict[str, Any]:
        """Load checkpoint from disk."""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")
        return {"processed_tables": {}, "total_processed": 0}
    
    def save(self):
        """Save checkpoint to disk."""
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump(self.checkpoint, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
    
    def mark_table_progress(self, table_name: str, rows_processed: int):
        """Mark progress for a specific table."""
        self.checkpoint["processed_tables"][table_name] = rows_processed
        self.checkpoint["total_processed"] = sum(self.checkpoint["processed_tables"].values())
        self.save()
    
    def get_table_offset(self, table_name: str) -> int:
        """Get the offset for a table (for resuming)."""
        return self.checkpoint["processed_tables"].get(table_name, 0)
    
    def reset(self):
        """Reset checkpoint."""
        self.checkpoint = {"processed_tables": {}, "total_processed": 0}
        self.save()


def run_pipeline(
    project_id: str,
    datasets: Optional[List[str]] = None,
    hours: Optional[int] = None,
    limit_per_table: Optional[int] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    embed_batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
    embed_model: str = DEFAULT_EMBED_MODEL,
    collection_name: str = DEFAULT_COLLECTION,
    vector_size: int = DEFAULT_VECTOR_SIZE,
    resume: bool = False,
    reset_checkpoint: bool = False
):
    """Run the full batch embedding pipeline."""
    
    # Derive safe defaults for qwen3 embeddings: separate collection + correct dim
    if "qwen3-embedding" in (embed_model or ""):
        if collection_name == DEFAULT_COLLECTION:
            collection_name = "logs_embedded_qwen3"
        if vector_size == DEFAULT_VECTOR_SIZE:
            vector_size = 1024
    
    # Initialize components
    bq_fetcher = BigQueryLogFetcher(project_id)
    embedder = OllamaEmbedder(model=embed_model)
    upserter = QdrantUpserter(collection_name=collection_name, vector_size=vector_size)
    checkpoint_mgr = CheckpointManager()
    
    if reset_checkpoint:
        logger.info("Resetting checkpoint...")
        checkpoint_mgr.reset()
    
    # Discover tables
    logger.info("Discovering log tables...")
    log_tables = bq_fetcher.discover_log_tables(datasets)
    
    if not log_tables:
        logger.warning("No log tables found!")
        return
    
    logger.info(f"Found {len(log_tables)} log tables to process")
    
    # Process each table
    total_processed = checkpoint_mgr.checkpoint["total_processed"]
    
    for table_info in log_tables:
        table_full_name = f"{table_info['dataset']}.{table_info['table']}"
        
        # Resume from checkpoint
        offset = checkpoint_mgr.get_table_offset(table_full_name) if resume else 0
        
        if offset > 0:
            logger.info(f"Resuming {table_full_name} from offset {offset}")
        
        logger.info(f"Processing table: {table_full_name} ({table_info['row_count']} rows)")
        
        # Fetch logs in batches
        batch_buffer: List[LogEntry] = []
        table_processed = offset
        
        for log_entry in bq_fetcher.fetch_logs_from_table(
            dataset=table_info['dataset'],
            table=table_info['table'],
            hours=hours,
            limit=limit_per_table,
            offset=offset
        ):
            batch_buffer.append(log_entry)
            
            # Process batch when buffer is full
            if len(batch_buffer) >= batch_size:
                process_batch(batch_buffer, embedder, upserter, embed_batch_size)
                
                table_processed += len(batch_buffer)
                total_processed += len(batch_buffer)
                
                checkpoint_mgr.mark_table_progress(table_full_name, table_processed)
                
                logger.info(
                    f"Progress: {table_full_name} = {table_processed} rows | "
                    f"Total = {total_processed} logs"
                )
                
                batch_buffer = []
        
        # Process remaining logs in buffer
        if batch_buffer:
            process_batch(batch_buffer, embedder, upserter, embed_batch_size)
            table_processed += len(batch_buffer)
            total_processed += len(batch_buffer)
            checkpoint_mgr.mark_table_progress(table_full_name, table_processed)
        
        logger.info(f"Completed table: {table_full_name} ({table_processed} logs processed)")
    
    logger.info(f"✅ Pipeline complete! Total logs processed: {total_processed}")


def process_batch(
    log_entries: List[LogEntry],
    embedder: OllamaEmbedder,
    upserter: QdrantUpserter,
    embed_batch_size: int
):
    """Process a batch of logs: construct trace text, embed, upsert."""
    
    # 1. Construct full trace text for each log
    trace_texts = [log.get_full_trace_text() for log in log_entries]
    
    # 2. Embed in sub-batches (Ollama may have limits)
    all_embeddings = []
    for i in range(0, len(trace_texts), embed_batch_size):
        sub_batch = trace_texts[i:i + embed_batch_size]
        embeddings = embedder.embed_batch(sub_batch)
        all_embeddings.extend(embeddings)
    
    # 3. Upsert to Qdrant
    upserter.upsert_batch(log_entries, all_embeddings)


def main():
    parser = argparse.ArgumentParser(
        description="Batch embed BigQuery logs and upsert to Qdrant"
    )
    
    parser.add_argument(
        "--project-id",
        default=os.getenv("PROJECT_ID_LOGS", "diatonic-ai-gcp"),
        help="GCP project ID for BigQuery"
    )
    
    parser.add_argument(
        "--datasets",
        nargs="+",
        help="Specific datasets to process (default: all datasets)"
    )
    
    parser.add_argument(
        "--hours",
        type=int,
        help="Only process logs from the last N hours"
    )
    
    parser.add_argument(
        "--limit-per-table",
        type=int,
        help="Max logs to process per table"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of logs to process per batch (default: {DEFAULT_BATCH_SIZE})"
    )
    
    parser.add_argument(
        "--embed-batch-size",
        type=int,
        default=DEFAULT_EMBED_BATCH_SIZE,
        help=f"Embedding batch size (default: {DEFAULT_EMBED_BATCH_SIZE})"
    )
    
    parser.add_argument(
        "--embed-model",
        default=DEFAULT_EMBED_MODEL,
        help=f"Ollama embedding model (default: {DEFAULT_EMBED_MODEL})"
    )
    
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help=f"Qdrant collection name (default: {DEFAULT_COLLECTION})"
    )
    
    parser.add_argument(
        "--vector-size",
        type=int,
        default=DEFAULT_VECTOR_SIZE,
        help=f"Vector dimension (default: {DEFAULT_VECTOR_SIZE})"
    )
    
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint"
    )
    
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Reset checkpoint before starting"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("BATCH EMBEDDING PIPELINE: BigQuery → Qdrant")
    logger.info("=" * 60)
    logger.info(f"Project: {args.project_id}")
    logger.info(f"Datasets: {args.datasets or 'ALL'}")
    logger.info(f"Time window: {args.hours or 'ALL'} hours")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Embed model: {args.embed_model}")
    logger.info(f"Collection: {args.collection}")
    logger.info(f"Resume: {args.resume}")
    logger.info("=" * 60)
    
    run_pipeline(
        project_id=args.project_id,
        datasets=args.datasets,
        hours=args.hours,
        limit_per_table=args.limit_per_table,
        batch_size=args.batch_size,
        embed_batch_size=args.embed_batch_size,
        embed_model=args.embed_model,
        collection_name=args.collection,
        vector_size=args.vector_size,
        resume=args.resume,
        reset_checkpoint=args.reset_checkpoint
    )


if __name__ == "__main__":
    main()
