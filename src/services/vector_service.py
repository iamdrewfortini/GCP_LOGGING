"""Vector service for embedding and semantic search operations.

This module provides a unified interface for:
- Generating embeddings via Vertex AI
- Storing embeddings in Qdrant
- Performing semantic search with time filtering
- Managing log embeddings collection
"""

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from qdrant_client.http import models

from src.services.embedding_service import embedding_service
from src.services.qdrant_service import qdrant_service

logger = logging.getLogger(__name__)

# Collection names
LOG_EMBEDDINGS_COLLECTION = "log_embeddings"
CONVERSATION_HISTORY_COLLECTION = "conversation_history"

# Feature flags
# Default to disabled so CI/tests never depend on external services.
ENABLE_VECTOR_SEARCH = os.getenv("ENABLE_VECTOR_SEARCH", "false").lower() == "true"
ENABLE_LOG_EMBEDDINGS = os.getenv("ENABLE_LOG_EMBEDDINGS", "false").lower() == "true"


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""
    vector_id: str
    text_hash: str
    embedding_dim: int
    created_at: str
    collection: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Result of a semantic search."""
    id: str
    score: float
    content: str
    metadata: Dict[str, Any]
    timestamp: Optional[str] = None


class VectorService:
    """Unified service for vector operations.

    Combines embedding generation (Vertex AI) with vector storage (Qdrant)
    for semantic search capabilities.
    """

    _instance: Optional["VectorService"] = None
    _log_collection_initialized: bool = False

    def __new__(cls) -> "VectorService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        pass

    @property
    def enabled(self) -> bool:
        """Check if vector search is enabled."""
        return ENABLE_VECTOR_SEARCH and qdrant_service.client is not None

    def ensure_log_embeddings_collection(self) -> bool:
        """Ensure the log_embeddings collection exists in Qdrant.

        Returns:
            True if collection exists or was created successfully
        """
        if self._log_collection_initialized:
            return True

        if not qdrant_service.client:
            logger.warning("Qdrant client not available")
            return False

        try:
            collections = qdrant_service.client.get_collections()
            exists = any(c.name == LOG_EMBEDDINGS_COLLECTION for c in collections.collections)

            if not exists:
                qdrant_service.client.create_collection(
                    collection_name=LOG_EMBEDDINGS_COLLECTION,
                    vectors_config=models.VectorParams(
                        size=768,  # text-embedding-004 dimension
                        distance=models.Distance.COSINE
                    ),
                )

                # Create indexes for efficient filtering
                indexes = [
                    ("project_id", models.PayloadSchemaType.KEYWORD),
                    ("severity", models.PayloadSchemaType.KEYWORD),
                    ("service", models.PayloadSchemaType.KEYWORD),
                    ("source_type", models.PayloadSchemaType.KEYWORD),
                    ("timestamp.year", models.PayloadSchemaType.INTEGER),
                    ("timestamp.month", models.PayloadSchemaType.INTEGER),
                    ("timestamp.day", models.PayloadSchemaType.INTEGER),
                ]

                for field_name, field_type in indexes:
                    try:
                        qdrant_service.client.create_payload_index(
                            collection_name=LOG_EMBEDDINGS_COLLECTION,
                            field_name=field_name,
                            field_schema=field_type,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to create index for {field_name}: {e}")

                logger.info(f"Created Qdrant collection: {LOG_EMBEDDINGS_COLLECTION}")

            self._log_collection_initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to ensure log_embeddings collection: {e}")
            return False

    def compute_text_hash(self, text: str) -> str:
        """Compute SHA-256 hash of text for deduplication.

        Args:
            text: Text to hash

        Returns:
            Hex digest of SHA-256 hash
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed_and_store(
        self,
        text: str,
        project_id: str,
        source_type: str = "log",
        metadata: Optional[Dict[str, Any]] = None,
        collection: str = LOG_EMBEDDINGS_COLLECTION,
        deduplicate: bool = True,
    ) -> Optional[EmbeddingResult]:
        """Generate embedding and store in Qdrant.

        Args:
            text: Text to embed
            project_id: Project/tenant ID for filtering
            source_type: Type of source (log, conversation, etc.)
            metadata: Additional metadata to store
            collection: Qdrant collection name
            deduplicate: Skip if same text hash exists

        Returns:
            EmbeddingResult if successful, None otherwise
        """
        if not self.enabled:
            logger.debug("Vector search disabled")
            return None

        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return None

        # Ensure collection exists
        if collection == LOG_EMBEDDINGS_COLLECTION:
            self.ensure_log_embeddings_collection()

        text_hash = self.compute_text_hash(text)

        # Check for duplicate
        if deduplicate:
            existing = self._find_by_hash(text_hash, project_id, collection)
            if existing:
                logger.debug(f"Duplicate embedding found: {text_hash[:16]}...")
                return existing

        # Generate embedding
        embedding = embedding_service.get_embedding(text)
        if not embedding or all(v == 0.0 for v in embedding):
            logger.error("Failed to generate embedding")
            return None

        # Prepare metadata with timestamp hierarchy
        now = datetime.now(timezone.utc)
        full_metadata = {
            "project_id": project_id,
            "source_type": source_type,
            "text_hash": text_hash,
            "content_preview": text[:500] if len(text) > 500 else text,
            "timestamp": {
                "iso": now.isoformat(),
                "year": now.year,
                "month": now.month,
                "day": now.day,
                "hour": now.hour,
            },
            **(metadata or {}),
        }

        # Store in Qdrant
        vector_id = str(uuid.uuid4())
        try:
            qdrant_service.client.upsert(
                collection_name=collection,
                points=[
                    models.PointStruct(
                        id=vector_id,
                        vector=embedding,
                        payload=full_metadata,
                    )
                ],
            )

            return EmbeddingResult(
                vector_id=vector_id,
                text_hash=text_hash,
                embedding_dim=len(embedding),
                created_at=now.isoformat(),
                collection=collection,
                metadata=full_metadata,
            )

        except Exception as e:
            logger.error(f"Failed to store embedding: {e}")
            return None

    def _find_by_hash(
        self,
        text_hash: str,
        project_id: str,
        collection: str,
    ) -> Optional[EmbeddingResult]:
        """Find existing embedding by text hash.

        Args:
            text_hash: SHA-256 hash of text
            project_id: Project ID for filtering
            collection: Collection to search

        Returns:
            EmbeddingResult if found, None otherwise
        """
        try:
            results = qdrant_service.client.scroll(
                collection_name=collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="project_id",
                            match=models.MatchValue(value=project_id),
                        ),
                        models.FieldCondition(
                            key="text_hash",
                            match=models.MatchValue(value=text_hash),
                        ),
                    ]
                ),
                limit=1,
            )

            if results and results[0]:
                point = results[0][0]
                return EmbeddingResult(
                    vector_id=str(point.id),
                    text_hash=text_hash,
                    embedding_dim=768,
                    created_at=point.payload.get("timestamp", {}).get("iso", ""),
                    collection=collection,
                    metadata=point.payload,
                )

        except Exception as e:
            logger.debug(f"Hash lookup failed: {e}")

        return None

    def semantic_search(
        self,
        query: str,
        project_id: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        collection: str = LOG_EMBEDDINGS_COLLECTION,
        score_threshold: float = 0.5,
    ) -> List[SearchResult]:
        """Perform semantic search with filtering.

        Args:
            query: Search query text
            project_id: Project ID for tenant isolation
            top_k: Number of results to return
            filters: Additional filters (severity, service, time range, etc.)
            collection: Collection to search
            score_threshold: Minimum similarity score (0-1)

        Returns:
            List of SearchResult objects
        """
        if not self.enabled:
            return []

        if not query or not query.strip():
            return []

        # Generate query embedding
        query_embedding = embedding_service.get_embedding(query)
        if not query_embedding or all(v == 0.0 for v in query_embedding):
            logger.error("Failed to generate query embedding")
            return []

        # Build filter conditions
        must_conditions = [
            models.FieldCondition(
                key="project_id",
                match=models.MatchValue(value=project_id),
            )
        ]

        if filters:
            # Severity filter
            if "severity" in filters:
                must_conditions.append(
                    models.FieldCondition(
                        key="severity",
                        match=models.MatchValue(value=filters["severity"]),
                    )
                )

            # Service filter
            if "service" in filters:
                must_conditions.append(
                    models.FieldCondition(
                        key="service",
                        match=models.MatchValue(value=filters["service"]),
                    )
                )

            # Time filters
            if "year" in filters:
                must_conditions.append(
                    models.FieldCondition(
                        key="timestamp.year",
                        match=models.MatchValue(value=filters["year"]),
                    )
                )
            if "month" in filters:
                must_conditions.append(
                    models.FieldCondition(
                        key="timestamp.month",
                        match=models.MatchValue(value=filters["month"]),
                    )
                )
            if "day" in filters:
                must_conditions.append(
                    models.FieldCondition(
                        key="timestamp.day",
                        match=models.MatchValue(value=filters["day"]),
                    )
                )

        try:
            results = qdrant_service.client.search(
                collection_name=collection,
                query_vector=query_embedding,
                query_filter=models.Filter(must=must_conditions),
                limit=top_k,
                score_threshold=score_threshold,
            )

            return [
                SearchResult(
                    id=str(r.id),
                    score=r.score,
                    content=r.payload.get("content_preview", ""),
                    metadata=r.payload,
                    timestamp=r.payload.get("timestamp", {}).get("iso"),
                )
                for r in results
            ]

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    def semantic_search_logs(
        self,
        query: str,
        project_id: str,
        top_k: int = 10,
        severity: Optional[str] = None,
        service: Optional[str] = None,
        hours: Optional[int] = None,
    ) -> List[SearchResult]:
        """Convenience method for searching logs semantically.

        Args:
            query: Search query
            project_id: Project ID
            top_k: Number of results
            severity: Filter by severity (ERROR, WARNING, etc.)
            service: Filter by service name
            hours: Limit to last N hours (not implemented yet)

        Returns:
            List of SearchResult objects
        """
        filters = {}
        if severity:
            filters["severity"] = severity
        if service:
            filters["service"] = service

        return self.semantic_search(
            query=query,
            project_id=project_id,
            top_k=top_k,
            filters=filters if filters else None,
            collection=LOG_EMBEDDINGS_COLLECTION,
        )

    def get_similar_logs(
        self,
        log_text: str,
        project_id: str,
        top_k: int = 5,
        exclude_self: bool = True,
    ) -> List[SearchResult]:
        """Find logs similar to a given log entry.

        Useful for finding related errors or patterns.

        Args:
            log_text: Log entry text
            project_id: Project ID
            top_k: Number of results
            exclude_self: Exclude exact matches

        Returns:
            List of similar logs
        """
        results = self.semantic_search(
            query=log_text,
            project_id=project_id,
            top_k=top_k + (1 if exclude_self else 0),
            collection=LOG_EMBEDDINGS_COLLECTION,
        )

        if exclude_self:
            text_hash = self.compute_text_hash(log_text)
            results = [r for r in results if r.metadata.get("text_hash") != text_hash]
            results = results[:top_k]

        return results

    def delete_by_project(self, project_id: str, collection: str = LOG_EMBEDDINGS_COLLECTION) -> int:
        """Delete all embeddings for a project.

        Args:
            project_id: Project ID
            collection: Collection name

        Returns:
            Number of points deleted (approximate)
        """
        if not qdrant_service.client:
            return 0

        try:
            qdrant_service.client.delete(
                collection_name=collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="project_id",
                                match=models.MatchValue(value=project_id),
                            )
                        ]
                    )
                ),
            )
            logger.info(f"Deleted embeddings for project: {project_id}")
            return -1  # Qdrant doesn't return count

        except Exception as e:
            logger.error(f"Failed to delete embeddings: {e}")
            return 0


# Singleton instance
vector_service = VectorService()
