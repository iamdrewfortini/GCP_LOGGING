"""
Ingestion pipeline: Normalize -> Chunk -> Embed -> Upsert

Takes raw log payloads, normalizes to schema, chunks long text, embeds via Ollama, upserts to Qdrant.

Idempotent by log_id/chunk_id, supports bulk modes.

Based on spec: ingest.normalizer, embed.ollama, store.qdrant_writer.
"""

import os
import uuid
import logging
from typing import List, Dict, Any, Iterator
from datetime import datetime
from src.schemas.log_payload_schema import normalize_log_payload, LogPayloadV1
from src.services.ollama_embed import OllamaEmbedService
from src.services.redis_service import RedisService
from qdrant_client import QdrantClient
from qdrant_client.http import models

logger = logging.getLogger(__name__)

# Config
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "logs_v1")
INGEST_BATCH_SIZE = int(os.getenv("INGEST_BATCH_SIZE", "256"))
UPSERT_WAIT = os.getenv("UPSERT_WAIT", "false").lower() == "true"
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
MAX_CHUNK_SIZE = 4000  # For chunking long text
CHUNK_OVERLAP = 200

class LogChunker:
    """Chunk long log text into smaller pieces with stable IDs, using tokenization."""

    @staticmethod
    def sentence_tokenize(text: str) -> List[str]:
        """Simple sentence tokenizer: split on . ! ? followed by space or end."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    @staticmethod
    def word_tokenize(text: str) -> List[str]:
        """Simple word tokenizer: split on whitespace."""
        return text.split()

    @staticmethod
    def chunk_text(text: str, max_size: int = MAX_CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
        """Split text into chunks, preferring sentence boundaries."""
        if len(text) <= max_size:
            return [text]
        sentences = LogChunker.sentence_tokenize(text)
        chunks = []
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_size:
                current_chunk += sentence + " "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + " "
                if len(current_chunk) > max_size:
                    # Sentence too long, chunk by words
                    words = LogChunker.word_tokenize(sentence)
                    word_chunk = ""
                    for word in words:
                        if len(word_chunk) + len(word) + 1 <= max_size:
                            word_chunk += word + " "
                        else:
                            if word_chunk:
                                chunks.append(word_chunk.strip())
                            word_chunk = word + " "
                    if word_chunk:
                        current_chunk = word_chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks

    @staticmethod
    def generate_chunk_id(log_id: str, chunk_idx: int) -> str:
        """Stable chunk ID."""
        return f"{log_id}_chunk_{chunk_idx}"


class QdrantLogWriter:
    """Qdrant writer for log points with vectors."""

    def __init__(self):
        self.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
        self.collection = QDRANT_COLLECTION
        self._ensure_collection()

    def _ensure_collection(self):
        """Create/update collection for logs_v1."""
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection for c in collections)

        if not exists:
            logger.info(f"Creating collection {self.collection}")
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=EMBED_DIM,
                    distance=models.Distance.COSINE
                ),
                # Sparse optional, enable if needed
                # sparse_vectors_config={"sparse": models.SparseVectorParams()}
            )
            # Add payload indexes for fast filtering
            indexes = [
                "tenant_id", "service_name", "severity", "log_type",
                "timestamp_year", "timestamp_month", "timestamp_day", "timestamp_hour",
                "http_status", "http_method", "source_table", "trace_id", "log_id"
            ]
            for field in indexes:
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection,
                        field_name=field,
                        field_schema=models.PayloadSchemaType.KEYWORD
                    )
                except Exception as e:
                    logger.warning(f"Index {field} already exists or error: {e}")
        else:
            logger.info(f"Collection {self.collection} exists")

    def upsert_points(self, points: List[models.PointStruct], batch_size: int = INGEST_BATCH_SIZE, wait: bool = UPSERT_WAIT):
        """Upsert points in batches."""
        for i in range(0, len(points), batch_size):
            batch = points[i:i+batch_size]
            self.client.upsert(
                collection_name=self.collection,
                points=batch,
                wait=wait
            )
            logger.info(f"Upserted batch {i//batch_size + 1} of {len(batch)} points")


class LogIngestionPipeline:
    """Full pipeline: normalize -> chunk -> embed -> upsert."""

    def __init__(self):
        self.chunker = LogChunker()
        self.embed_service = OllamaEmbedService()
        self.writer = QdrantLogWriter()
        self.redis = RedisService()

    def process_raw_logs(self, raw_logs: List[Dict[str, Any]]) -> int:
        """
        Process list of raw log dicts.

        Returns number of points upserted.
        """
        normalized_logs = []
        for raw in raw_logs:
            log_id = raw.get('log_id')
            if log_id:
                cached_norm = self.redis.get_cached_normalized_log(log_id)
                if cached_norm:
                    normalized_logs.append(LogPayloadV1(**cached_norm))
                    continue
            try:
                norm = normalize_log_payload(raw)
                normalized_logs.append(norm)
                if log_id:
                    self.redis.cache_normalized_log(log_id, norm.dict())
            except Exception as e:
                logger.error(f"Failed to normalize log: {e}")
                continue

        # Chunk and prepare for embedding
        log_entries = []
        for log in normalized_logs:
            log_id = log.log_id
            cached_chunks = self.redis.get_cached_chunks(log_id)
            if cached_chunks:
                # Use cached chunks
                for idx, chunk in enumerate(cached_chunks):
                    entry_id = self.chunker.generate_chunk_id(log_id, idx) if len(cached_chunks) > 1 else log_id
                    payload = log.dict()
                    payload['chunk_idx'] = idx
                    payload['total_chunks'] = len(cached_chunks)
                    payload['chunk_text'] = chunk
                    log_entries.append({
                        'id': entry_id,
                        'text': chunk,
                        'payload': payload
                    })
            else:
                entries = self._prepare_log_entries(log)
                log_entries.extend(entries)
                # Cache chunks
                chunks = [e['text'] for e in entries]
                self.redis.cache_chunks(log_id, chunks)

        if not log_entries:
            return 0

        # Embed
        texts = [e['text'] for e in log_entries]
        embeddings = self.embed_service.embed_batch(texts)

        # Create points
        points = []
        for (entry, emb) in zip(log_entries, embeddings):
            point = models.PointStruct(
                id=entry['id'],
                vector=emb,
                payload=entry['payload']
            )
            points.append(point)

        # Upsert
        self.writer.upsert_points(points)
        return len(points)

    def _prepare_log_entries(self, log: LogPayloadV1) -> List[Dict[str, Any]]:
        """Prepare log entries: chunk text, assign IDs, build payload."""
        entries = []

        # Build full text for embedding
        text_parts = []
        if log.message:
            text_parts.append(f"Message: {log.message}")
        if log.body:
            text_parts.append(f"Body: {log.body}")
        full_text = " | ".join(text_parts) or "empty log"

        # Chunk if needed
        chunks = self.chunker.chunk_text(full_text)
        for idx, chunk in enumerate(chunks):
            entry_id = self.chunker.generate_chunk_id(log.log_id, idx) if len(chunks) > 1 else log.log_id

            payload = log.dict()  # Full payload
            payload['chunk_idx'] = idx
            payload['total_chunks'] = len(chunks)
            payload['chunk_text'] = chunk

            entries.append({
                'id': entry_id,
                'text': chunk,
                'payload': payload
            })

        return entries