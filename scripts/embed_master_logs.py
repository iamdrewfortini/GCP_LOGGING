#!/usr/bin/env python3
"""Embed logs from master_logs table to Qdrant Cloud.

This script fetches logs from the centralized master_logs table,
embeds them using Ollama qwen3-embedding, and upserts to Qdrant Cloud.
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google.cloud import bigquery
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Setup
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

# Configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
EMBED_MODEL = "qwen3-embedding:0.6b"
VECTOR_DIM = 1024
COLLECTION_NAME = "logs_embedded_qwen3"
BATCH_SIZE = 100  # Logs per batch
EMBED_BATCH_SIZE = 10  # Embeddings per Ollama call
MAX_TEXT_LENGTH = 6000

# Rate limiting
OLLAMA_DELAY = 0.3  # seconds between embedding calls


def embed_text(text: str) -> list[float]:
    """Embed a single text using Ollama."""
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "... [truncated]"

    payload = {"model": EMBED_MODEL, "input": text}
    try:
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(f"{OLLAMA_HOST}/api/embed", json=payload)
            resp.raise_for_status()
            data = resp.json()
        emb = data.get("embeddings", [])
        if emb and isinstance(emb, list) and len(emb[0]) == VECTOR_DIM:
            return emb[0]
    except Exception as e:
        print(f"Embed error: {e}")
    return [0.0] * VECTOR_DIM


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in a single Ollama call (batch API)."""
    # Truncate texts
    processed = []
    for text in texts:
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "... [truncated]"
        processed.append(text)

    payload = {"model": EMBED_MODEL, "input": processed}
    try:
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(f"{OLLAMA_HOST}/api/embed", json=payload)
            resp.raise_for_status()
            data = resp.json()
        embeddings = data.get("embeddings", [])
        if embeddings and len(embeddings) == len(texts):
            return embeddings
    except Exception as e:
        print(f"\nBatch embed error ({len(texts)} texts): {e}")
        # Fallback to individual embedding
        return [embed_text(t) for t in texts]

    # Return zeros if failed
    return [[0.0] * VECTOR_DIM for _ in texts]


def build_log_text(row) -> str:
    """Build embeddable text from a log row."""
    parts = []

    # Timestamp and severity
    ts = row.event_timestamp.isoformat() if row.event_timestamp else "unknown"
    parts.append(f"[{ts}] [{row.severity}]")

    # Service context
    if row.service_name:
        parts.append(f"[{row.service_name}]")
    if row.resource_type:
        parts.append(f"[{row.resource_type}]")

    # Main message
    if row.message:
        msg = row.message[:4000] if len(row.message) > 4000 else row.message
        parts.append(f"Message: {msg}")

    # Text payload
    if row.text_payload and row.text_payload != row.message:
        text = row.text_payload[:2000] if len(row.text_payload) > 2000 else row.text_payload
        parts.append(f"Text: {text}")

    # JSON payload
    if row.json_payload:
        try:
            if isinstance(row.json_payload, str):
                jp = row.json_payload[:1500]
            else:
                jp = json.dumps(row.json_payload, default=str)[:1500]
            parts.append(f"JSON: {jp}")
        except:
            pass

    # HTTP context
    if row.http_method or row.http_url:
        http_parts = []
        if row.http_method:
            http_parts.append(row.http_method)
        if row.http_url:
            http_parts.append(row.http_url[:200])
        if row.http_status:
            http_parts.append(f"status={row.http_status}")
        parts.append(f"HTTP: {' '.join(http_parts)}")

    # Trace context
    if row.trace_id:
        parts.append(f"Trace: {row.trace_id}")

    return " ".join(parts)


def build_payload(row) -> dict:
    """Build Qdrant payload from log row."""
    ts = row.event_timestamp
    return {
        "log_id": row.log_id,
        "severity": row.severity,
        "service_name": row.service_name or "unknown",
        "resource_type": row.resource_type or "unknown",
        "stream_id": row.stream_id,
        "source_table": row.source_table,
        "log_type": row.log_type,
        "message": (row.message or "")[:500],
        "http_method": row.http_method,
        "http_url": row.http_url,
        "http_status": row.http_status,
        "trace_id": row.trace_id,
        "timestamp": {
            "iso": ts.isoformat() if ts else None,
            "year": ts.year if ts else None,
            "month": ts.month if ts else None,
            "day": ts.day if ts else None,
            "hour": ts.hour if ts else None,
        }
    }


def main():
    print("=" * 60)
    print("Master Logs Embedding Pipeline")
    print("=" * 60)

    # Initialize clients
    print("\nInitializing clients...")
    bq_client = bigquery.Client(project="diatonic-ai-gcp")
    qdrant_client = QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY"),
        timeout=120
    )

    # Get total count
    count_query = "SELECT COUNT(*) as cnt FROM `diatonic-ai-gcp.central_logging_v1.master_logs`"
    total_count = list(bq_client.query(count_query).result())[0].cnt
    print(f"Total logs to embed: {total_count:,}")

    # Query logs from master_logs
    query = """
    SELECT
        log_id,
        event_timestamp,
        severity,
        service_name,
        resource_type,
        source_table,
        stream_id,
        log_type,
        message,
        text_payload,
        json_payload,
        http_method,
        http_url,
        http_status,
        trace_id
    FROM `diatonic-ai-gcp.central_logging_v1.master_logs`
    ORDER BY event_timestamp DESC
    """

    print(f"\nFetching logs from BigQuery...")
    start_time = time.time()

    query_job = bq_client.query(query)
    rows = list(query_job.result())

    fetch_time = time.time() - start_time
    print(f"Fetched {len(rows):,} logs in {fetch_time:.1f}s")

    # Process in batches - use larger batches for efficiency
    BATCH_SIZE = 200  # Logs per Qdrant upsert
    EMBED_BATCH = 50  # Texts per Ollama batch call

    total_embedded = 0
    total_upserted = 0
    batch_count = 0

    print(f"\nEmbedding with {EMBED_MODEL} and upserting to Qdrant...")
    print(f"Batch size: {BATCH_SIZE}, Embed batch: {EMBED_BATCH}")

    embed_start = time.time()

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        batch_count += 1

        # Build texts for this batch
        texts = [build_log_text(row) for row in batch]
        payloads = [build_payload(row) for row in batch]

        # Embed texts using batch API
        embeddings = []
        for j in range(0, len(texts), EMBED_BATCH):
            sub_texts = texts[j:j + EMBED_BATCH]
            batch_embeddings = embed_batch(sub_texts)
            embeddings.extend(batch_embeddings)

        total_embedded += len(embeddings)

        # Build points
        points = [
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload=payload
            )
            for emb, payload in zip(embeddings, payloads)
        ]

        # Upsert to Qdrant
        try:
            qdrant_client.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
                wait=True
            )
            total_upserted += len(points)
        except Exception as e:
            print(f"\nError upserting batch {batch_count}: {e}")

        # Progress
        elapsed = time.time() - embed_start
        rate = total_embedded / elapsed if elapsed > 0 else 0
        eta = (len(rows) - total_embedded) / rate if rate > 0 else 0

        pct = total_embedded / len(rows) * 100
        print(f"\rProgress: {total_embedded:,}/{len(rows):,} ({pct:.1f}%) | "
              f"Rate: {rate:.1f}/s | ETA: {eta/60:.1f}m | "
              f"Upserted: {total_upserted:,}", end="", flush=True)

    total_time = time.time() - start_time

    print(f"\n\n{'=' * 60}")
    print("COMPLETE!")
    print(f"{'=' * 60}")
    print(f"Total embedded: {total_embedded:,}")
    print(f"Total upserted: {total_upserted:,}")
    print(f"Total time: {total_time/60:.1f} minutes")

    # Verify in Qdrant
    print(f"\nVerifying Qdrant collection...")
    info = qdrant_client.get_collection(COLLECTION_NAME)
    print(f"Collection '{COLLECTION_NAME}': {info.points_count:,} points")

    # Sample search
    print(f"\nTesting semantic search...")
    test_query = "authentication error"
    test_emb = embed_text(test_query)
    results = qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=test_emb,
        limit=3
    )
    print(f"Query: '{test_query}'")
    for r in results:
        print(f"  [{r.score:.3f}] {r.payload.get('severity')} - {r.payload.get('message', '')[:80]}")


if __name__ == "__main__":
    main()
