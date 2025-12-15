import logging
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models
from src.services.qdrant_service import qdrant_service

logger = logging.getLogger("qdrant_manager")

class QdrantManager:
    """
    Manages Qdrant schema definitions, health checks, and auto-repair.
    """
    
    # Schema Definitions
    SCHEMAS = {
        "conversation_history": {
            "vectors_config": models.VectorParams(size=768, distance=models.Distance.COSINE),
            "sparse_vectors_config": {"text": models.SparseVectorParams()},
            "payload_indexes": [
                {"field_name": "group_id", "schema": models.PayloadSchemaType.KEYWORD},
                {"field_name": "session_id", "schema": models.PayloadSchemaType.KEYWORD},
                {"field_name": "role", "schema": models.PayloadSchemaType.KEYWORD},
                {"field_name": "timestamp.year", "schema": models.PayloadSchemaType.INTEGER},
                {"field_name": "timestamp.month", "schema": models.PayloadSchemaType.INTEGER},
                {"field_name": "timestamp.day", "schema": models.PayloadSchemaType.INTEGER},
                {"field_name": "timestamp.hour", "schema": models.PayloadSchemaType.INTEGER},
            ]
        },
        "repo_index": {
            "vectors_config": models.VectorParams(size=768, distance=models.Distance.COSINE),
            "sparse_vectors_config": {"text": models.SparseVectorParams()},
            "payload_indexes": [
                {"field_name": "group_id", "schema": models.PayloadSchemaType.KEYWORD},
                {"field_name": "file_path", "schema": models.PayloadSchemaType.KEYWORD},
                {"field_name": "commit_hash", "schema": models.PayloadSchemaType.KEYWORD},
            ]
        },
        "app_logs": {
            "vectors_config": models.VectorParams(size=768, distance=models.Distance.COSINE),
            "payload_indexes": [
                {"field_name": "group_id", "schema": models.PayloadSchemaType.KEYWORD},
                {"field_name": "service", "schema": models.PayloadSchemaType.KEYWORD},
                {"field_name": "severity", "schema": models.PayloadSchemaType.KEYWORD},
                {"field_name": "timestamp_iso", "schema": models.PayloadSchemaType.KEYWORD}, 
            ]
        }
    }

    def __init__(self, client: QdrantClient = None):
        self.client = client or qdrant_service.client
        if not self.client:
             qdrant_service._connect()
             self.client = qdrant_service.client

    def run_check_and_repair(self) -> Dict[str, Any]:
        """
        Runs a comprehensive check of all defined collections and repairs them if needed.
        Returns a report of actions taken.
        """
        if not self.client:
            return {"status": "error", "message": "Could not connect to Qdrant"}

        report = {"status": "success", "repaired": [], "created": [], "checked": []}
        
        try:
            existing_collections = {c.name for c in self.client.get_collections().collections}
        except Exception as e:
            return {"status": "error", "message": f"Failed to list collections: {e}"}

        for name, schema in self.SCHEMAS.items():
            if name not in existing_collections:
                logger.info(f"Collection '{name}' missing. Creating...")
                try:
                    self.client.create_collection(
                        collection_name=name,
                        vectors_config=schema["vectors_config"],
                        sparse_vectors_config=schema.get("sparse_vectors_config")
                    )
                    report["created"].append(name)
                except Exception as e:
                    logger.error(f"Failed to create collection '{name}': {e}")
                    report["status"] = "partial_failure"
                    continue
            else:
                report["checked"].append(name)
                # TODO: In a more advanced version, check vector params match. 
                # Qdrant doesn't easily allow updating vector config on existing collections without recreation.

            # Ensure Payload Indexes
            for index_def in schema["payload_indexes"]:
                try:
                    self.client.create_payload_index(
                        collection_name=name,
                        field_name=index_def["field_name"],
                        field_schema=index_def["schema"]
                    )
                except Exception as e:
                    # Index might already exist, which is fine, but log if it's a real error
                    # Qdrant client usually is idempotent here or throws specific error
                    logger.warning(f"Index creation warning for {name}.{index_def['field_name']}: {e}")

        return report

qdrant_manager = QdrantManager()
