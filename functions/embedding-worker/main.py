"""Embedding Worker Cloud Function.

Processes embedding jobs from Pub/Sub and stores vectors in Qdrant.
Triggered by messages on the 'embedding-jobs' topic.

Message format:
{
    "action": "embed_log" | "embed_batch" | "delete_project",
    "project_id": "diatonic-ai-gcp",
    "text": "Log message to embed",  # for embed_log
    "texts": ["msg1", "msg2", ...],   # for embed_batch
    "metadata": {                      # optional
        "severity": "ERROR",
        "service": "my-service",
        "log_id": "abc123"
    }
}
"""

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import functions_framework
from google.cloud import aiplatform

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.getenv("PROJECT_ID", "diatonic-ai-gcp")
REGION = os.getenv("REGION", "us-central1")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
LOG_EMBEDDINGS_COLLECTION = "log_embeddings"

# Feature flags
ENABLE_EMBEDDINGS = os.getenv("ENABLE_EMBEDDINGS", "true").lower() == "true"

# Lazy-loaded clients
_embedding_model = None
_qdrant_client = None


def get_embedding_model():
    """Get or create Vertex AI embedding model."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from vertexai.language_models import TextEmbeddingModel
            aiplatform.init(project=PROJECT_ID, location=REGION)
            _embedding_model = TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL)
            logger.info(f"Initialized embedding model: {EMBEDDING_MODEL}")
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            raise
    return _embedding_model


def get_qdrant_client():
    """Get or create Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        try:
            from qdrant_client import QdrantClient
            if QDRANT_API_KEY:
                _qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            else:
                _qdrant_client = QdrantClient(url=QDRANT_URL)
            logger.info(f"Connected to Qdrant at {QDRANT_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise
    return _qdrant_client


def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for text using Vertex AI.

    Args:
        text: Text to embed

    Returns:
        Embedding vector or None on failure
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for embedding")
        return None

    try:
        model = get_embedding_model()
        embeddings = model.get_embeddings([text])
        if embeddings and len(embeddings) > 0:
            return embeddings[0].values
        return None
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return None


def generate_batch_embeddings(texts: List[str]) -> List[Optional[List[float]]]:
    """Generate embeddings for multiple texts.

    Args:
        texts: List of texts to embed

    Returns:
        List of embedding vectors (None for failed embeddings)
    """
    if not texts:
        return []

    try:
        model = get_embedding_model()
        # Filter out empty texts
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return [None] * len(texts)

        embeddings = model.get_embeddings(valid_texts)
        results = []
        valid_idx = 0
        for text in texts:
            if text and text.strip():
                if valid_idx < len(embeddings):
                    results.append(embeddings[valid_idx].values)
                else:
                    results.append(None)
                valid_idx += 1
            else:
                results.append(None)
        return results
    except Exception as e:
        logger.error(f"Failed to generate batch embeddings: {e}")
        return [None] * len(texts)


def compute_text_hash(text: str) -> str:
    """Compute SHA-256 hash for deduplication."""
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def store_embedding(
    text: str,
    embedding: List[float],
    project_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Store embedding in Qdrant.

    Args:
        text: Original text
        embedding: Embedding vector
        project_id: Project ID for tenant isolation
        metadata: Additional metadata

    Returns:
        Vector ID or None on failure
    """
    import uuid
    from qdrant_client.http import models

    try:
        client = get_qdrant_client()

        # Ensure collection exists
        ensure_collection(client)

        # Prepare metadata
        now = datetime.now(timezone.utc)
        text_hash = compute_text_hash(text)
        full_metadata = {
            "project_id": project_id,
            "source_type": metadata.get("source_type", "log") if metadata else "log",
            "text_hash": text_hash,
            "content_preview": text[:500] if len(text) > 500 else text,
            "timestamp": {
                "iso": now.isoformat(),
                "year": now.year,
                "month": now.month,
                "day": now.day,
                "hour": now.hour,
            },
        }

        if metadata:
            # Add severity, service, and other fields
            for key in ["severity", "service", "log_id", "trace_id", "span_id"]:
                if key in metadata:
                    full_metadata[key] = metadata[key]

        # Store in Qdrant
        vector_id = str(uuid.uuid4())
        client.upsert(
            collection_name=LOG_EMBEDDINGS_COLLECTION,
            points=[
                models.PointStruct(
                    id=vector_id,
                    vector=embedding,
                    payload=full_metadata,
                )
            ],
        )

        logger.info(f"Stored embedding: {vector_id[:8]}... for project {project_id}")
        return vector_id

    except Exception as e:
        logger.error(f"Failed to store embedding: {e}")
        return None


def ensure_collection(client) -> bool:
    """Ensure log_embeddings collection exists."""
    from qdrant_client.http import models

    try:
        collections = client.get_collections()
        exists = any(c.name == LOG_EMBEDDINGS_COLLECTION for c in collections.collections)

        if not exists:
            client.create_collection(
                collection_name=LOG_EMBEDDINGS_COLLECTION,
                vectors_config=models.VectorParams(
                    size=768,  # text-embedding-004 dimension
                    distance=models.Distance.COSINE
                ),
            )

            # Create indexes
            indexes = [
                ("project_id", models.PayloadSchemaType.KEYWORD),
                ("severity", models.PayloadSchemaType.KEYWORD),
                ("service", models.PayloadSchemaType.KEYWORD),
            ]

            for field_name, field_type in indexes:
                try:
                    client.create_payload_index(
                        collection_name=LOG_EMBEDDINGS_COLLECTION,
                        field_name=field_name,
                        field_schema=field_type,
                    )
                except Exception as e:
                    logger.warning(f"Failed to create index for {field_name}: {e}")

            logger.info(f"Created collection: {LOG_EMBEDDINGS_COLLECTION}")

        return True

    except Exception as e:
        logger.error(f"Failed to ensure collection: {e}")
        return False


def delete_project_embeddings(project_id: str) -> bool:
    """Delete all embeddings for a project.

    Args:
        project_id: Project ID

    Returns:
        True if successful
    """
    from qdrant_client.http import models

    try:
        client = get_qdrant_client()
        client.delete(
            collection_name=LOG_EMBEDDINGS_COLLECTION,
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
        return True
    except Exception as e:
        logger.error(f"Failed to delete project embeddings: {e}")
        return False


def process_embed_log(message: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single log embedding request.

    Args:
        message: Message with text and metadata

    Returns:
        Result dictionary
    """
    text = message.get("text", "")
    project_id = message.get("project_id", PROJECT_ID)
    metadata = message.get("metadata", {})

    if not text:
        return {"success": False, "error": "No text provided"}

    embedding = generate_embedding(text)
    if not embedding:
        return {"success": False, "error": "Failed to generate embedding"}

    vector_id = store_embedding(text, embedding, project_id, metadata)
    if not vector_id:
        return {"success": False, "error": "Failed to store embedding"}

    return {
        "success": True,
        "vector_id": vector_id,
        "text_hash": compute_text_hash(text),
    }


def process_embed_batch(message: Dict[str, Any]) -> Dict[str, Any]:
    """Process a batch embedding request.

    Args:
        message: Message with texts list and metadata

    Returns:
        Result dictionary with success count
    """
    texts = message.get("texts", [])
    project_id = message.get("project_id", PROJECT_ID)
    metadata = message.get("metadata", {})

    if not texts:
        return {"success": False, "error": "No texts provided"}

    embeddings = generate_batch_embeddings(texts)
    success_count = 0
    failed_count = 0
    vector_ids = []

    for i, (text, embedding) in enumerate(zip(texts, embeddings)):
        if embedding:
            item_metadata = {**metadata}
            if isinstance(metadata, list) and i < len(metadata):
                item_metadata = metadata[i]

            vector_id = store_embedding(text, embedding, project_id, item_metadata)
            if vector_id:
                success_count += 1
                vector_ids.append(vector_id)
            else:
                failed_count += 1
        else:
            failed_count += 1

    return {
        "success": True,
        "success_count": success_count,
        "failed_count": failed_count,
        "vector_ids": vector_ids,
    }


@functions_framework.cloud_event
def process_embedding_job(cloud_event):
    """Cloud Function entry point for Pub/Sub trigger.

    Processes embedding jobs from the 'embedding-jobs' topic.

    Args:
        cloud_event: CloudEvent containing Pub/Sub message
    """
    if not ENABLE_EMBEDDINGS:
        logger.info("Embeddings disabled via feature flag")
        return

    # Decode message
    try:
        message_data = base64.b64decode(cloud_event.data["message"]["data"]).decode()
        message = json.loads(message_data)
    except Exception as e:
        logger.error(f"Failed to decode message: {e}")
        return

    action = message.get("action", "embed_log")
    logger.info(f"Processing embedding job: action={action}")

    result = {}
    try:
        if action == "embed_log":
            result = process_embed_log(message)
        elif action == "embed_batch":
            result = process_embed_batch(message)
        elif action == "delete_project":
            project_id = message.get("project_id")
            if project_id:
                success = delete_project_embeddings(project_id)
                result = {"success": success}
            else:
                result = {"success": False, "error": "No project_id provided"}
        else:
            logger.warning(f"Unknown action: {action}")
            result = {"success": False, "error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"Error processing embedding job: {e}")
        result = {"success": False, "error": str(e)}

    logger.info(f"Embedding job result: {result}")
    return result
