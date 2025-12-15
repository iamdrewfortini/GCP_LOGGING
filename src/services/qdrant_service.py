import os
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.http import models

class QdrantService:
    def __init__(self):
        self.url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.api_key = os.getenv("QDRANT_API_KEY", None)
        self.client: Optional[QdrantClient] = None
        self.collection_name = "conversation_history"
        self._connect()

    def _connect(self):
        try:
            self.client = QdrantClient(url=self.url, api_key=self.api_key)
        except Exception as e:
            print(f"Failed to connect to Qdrant: {e}")
            self.client = None

    def ensure_collections(self):
        """Creates collections with hybrid search and tenant isolation support."""
        if not self.client:
            return

        # Check if collection exists
        collections = self.client.get_collections()
        exists = any(c.name == self.collection_name for c in collections.collections)

        if not exists:
            # Create collection with Dense + Sparse support
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=768, 
                    distance=models.Distance.COSINE
                ),
                sparse_vectors_config={
                    "text": models.SparseVectorParams()
                }
            )
            
            # Create Tenant Index (Multitenancy)
            # using 'group_id' as the standard tenant identifier key
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="group_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            # Create Payload Indexes for Time Hierarchy
            fields = ["session_id", "role", "timestamp.year", "timestamp.month", "timestamp.day", "timestamp.hour"]
            for field in fields:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD if "id" in field or "role" in field else models.PayloadSchemaType.INTEGER
                )
            print(f"Created Qdrant collection: {self.collection_name}")

    def upsert_memory(self, session_id: str, project_id: str, role: str, content: str, embedding: List[float], sparse_indices: List[int] = None, sparse_values: List[float] = None):
        """
        Stores a memory with strict hierarchical timestamping and tenant isolation.
        """
        if not self.client:
            return

        now = datetime.utcnow()
        point_id = str(uuid.uuid4()) # In prod, use UUIDv7 for time-sorting

        payload = {
            "group_id": project_id, # Tenant ID
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": {
                "iso": now.isoformat(),
                "year": now.year,
                "month": now.month,
                "day": now.day,
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second
            }
        }
        
        # Prepare vector(s)
        # For now, we mainly use dense. Sparse can be added if we integrate a SPLADE/BM25 encoder.
        vectors = {"": embedding}
        if sparse_indices and sparse_values:
            vectors["text"] = models.SparseVector(indices=sparse_indices, values=sparse_values)

        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vectors, # Supports named vectors for hybrid
                    payload=payload
                )
            ]
        )

    def search_memory(self, query_vector: List[float], project_id: str, limit: int = 5, filters: Dict[str, Any] = None, collection_name: str = None):
        """
        Performs a search filtered by tenant (project_id).
        """
        if not self.client:
            return []

        target_collection = collection_name or self.collection_name

        # Base filter: Tenant Isolation via group_id
        must_conditions = [
            models.FieldCondition(key="group_id", match=models.MatchValue(value=project_id))
        ]

        if filters:
            for key, val in filters.items():
                must_conditions.append(
                    models.FieldCondition(key=key, match=models.MatchValue(value=val))
                )

        return self.client.search(
            collection_name=target_collection,
            query_vector=query_vector,
            query_filter=models.Filter(must=must_conditions),
            limit=limit
        )

    def get_collections(self):
        if not self.client:
            return []
        return self.client.get_collections().collections

qdrant_service = QdrantService()
