"""
Qdrant Universal Query Engine for advanced log retrieval.

Supports filters, multistage prefetch, hybrid fusion, formula rescoring, grouping, pagination.

Based on spec: query.engine.
"""

import os
import logging
from typing import List, Dict, Any, Optional, Union
from qdrant_client import QdrantClient
from qdrant_client.http import models

logger = logging.getLogger(__name__)

# Config
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "logs_v1")
QDRANT_DENSE_VECTOR = os.getenv("QDRANT_DENSE_VECTOR", "dense")
QDRANT_SPARSE_VECTOR = os.getenv("QDRANT_SPARSE_VECTOR", "sparse")  # If enabled


class QdrantQueryEngine:
    """Universal query wrapper for Qdrant /points/query."""

    def __init__(self):
        self.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
        self.collection = QDRANT_COLLECTION
        self.dense_vector = QDRANT_DENSE_VECTOR
        self.sparse_vector = QDRANT_SPARSE_VECTOR

    def query_points(
        self,
        query_vector: Optional[List[float]] = None,
        query_filter: Optional[models.Filter] = None,
        limit: int = 10,
        offset: int = 0,
        with_payload: Union[bool, List[str]] = True,
        with_vector: bool = False,
        score_threshold: Optional[float] = None,
        hnsw_ef: Optional[int] = None,
        prefetch: Optional[List[Dict[str, Any]]] = None,
        fusion: Optional[str] = None,  # "rrf" or "dbsf"
        formula: Optional[str] = None,  # Formula rescoring
        order_by: Optional[models.OrderBy] = None,
    ) -> models.QueryResponse:
        """
        Universal query using /points/query.

        Supports semantic, filtered, hybrid, formula-rescored queries.
        """
        params = {}
        if hnsw_ef:
            params["hnsw_ef"] = hnsw_ef

        # Prefetch for multistage/hybrid
        if prefetch:
            # Ensure prefetch limit >= limit + offset for pagination
            for p in prefetch:
                if "limit" in p and p["limit"] < limit + offset:
                    p["limit"] = limit + offset
                    logger.warning(f"Adjusted prefetch limit to {p['limit']}")

        query_request = models.QueryRequest(
            vector=query_vector,
            filter=query_filter,
            limit=limit,
            offset=offset,
            with_payload=with_payload,
            with_vector=with_vector,
            score_threshold=score_threshold,
            params=params,
            prefetch=prefetch,
            fusion=fusion,
            formula=formula,
            order_by=order_by,
        )

        response = self.client.query_points(
            collection_name=self.collection,
            query=query_request
        )
        return response

    def query_groups(
        self,
        query_vector: Optional[List[float]] = None,
        query_filter: Optional[models.Filter] = None,
        limit: int = 10,
        group_by: str = "trace_id",  # Field to group by
        group_size: int = 1,  # Best per group
        with_payload: Union[bool, List[str]] = True,
        with_vector: bool = False,
        hnsw_ef: Optional[int] = None,
    ) -> models.GroupsResult:
        """
        Group query for de-duplication (e.g., one best log per trace).

        Uses /points/query/groups.
        """
        params = {}
        if hnsw_ef:
            params["hnsw_ef"] = hnsw_ef

        response = self.client.query_points_groups(
            collection_name=self.collection,
            group_by=group_by,
            query=models.QueryRequest(
                vector=query_vector,
                filter=query_filter,
                limit=group_size,
                with_payload=with_payload,
                with_vector=with_vector,
                params=params,
            ),
            limit=limit,
        )
        return response

    # Helper methods for common queries

    def semantic_search(
        self,
        query_vector: List[float],
        limit: int = 10,
        hnsw_ef: int = 64,
        **kwargs
    ) -> models.QueryResponse:
        """Pure semantic search."""
        return self.query_points(
            query_vector=query_vector,
            limit=limit,
            hnsw_ef=hnsw_ef,
            **kwargs
        )

    def filtered_search(
        self,
        query_vector: List[float],
        query_filter: models.Filter,
        limit: int = 10,
        hnsw_ef: int = 32,  # Lower for filtered
        **kwargs
    ) -> models.QueryResponse:
        """Filtered vector search."""
        return self.query_points(
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            hnsw_ef=hnsw_ef,
            **kwargs
        )

    def hybrid_search(
        self,
        dense_vector: List[float],
        sparse_vector: Optional[Dict[str, Any]] = None,  # If sparse enabled
        limit: int = 10,
        fusion: str = "rrf",
        hnsw_ef: int = 64,
        **kwargs
    ) -> models.QueryResponse:
        """Hybrid search with prefetch + fusion."""
        prefetch = [
            {
                "query": dense_vector,
                "using": self.dense_vector,
                "limit": limit + 10,  # Buffer
            }
        ]
        if sparse_vector:
            prefetch.append({
                "query": sparse_vector,
                "using": self.sparse_vector,
                "limit": limit + 10,
            })

        return self.query_points(
            limit=limit,
            prefetch=prefetch,
            fusion=fusion,
            hnsw_ef=hnsw_ef,
            **kwargs
        )

    def formula_rescore(
        self,
        query_vector: List[float],
        formula: str,  # e.g., "max(0.7 * score + 0.3 * payload_severity_score)"
        limit: int = 10,
        **kwargs
    ) -> models.QueryResponse:
        """Formula rescoring for business logic."""
        return self.query_points(
            query_vector=query_vector,
            formula=formula,
            limit=limit,
            **kwargs
        )

    # Filter builders
    @staticmethod
    def build_filter(
        tenant_id: Optional[str] = None,
        service_name: Optional[str] = None,
        severity: Optional[str] = None,
        log_type: Optional[str] = None,
        timestamp_from: Optional[int] = None,  # Unix timestamp
        timestamp_to: Optional[int] = None,
        http_status: Optional[int] = None,
        trace_id: Optional[str] = None,
        **kwargs
    ) -> models.Filter:
        """Build Filter from common fields."""
        conditions = []

        if tenant_id:
            conditions.append(models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=tenant_id)
            ))
        if service_name:
            conditions.append(models.FieldCondition(
                key="service_name",
                match=models.MatchValue(value=service_name)
            ))
        if severity:
            conditions.append(models.FieldCondition(
                key="severity",
                match=models.MatchValue(value=severity)
            ))
        if log_type:
            conditions.append(models.FieldCondition(
                key="log_type",
                match=models.MatchValue(value=log_type)
            ))
        if http_status:
            conditions.append(models.FieldCondition(
                key="http_status",
                match=models.MatchValue(value=http_status)
            ))
        if trace_id:
            conditions.append(models.FieldCondition(
                key="trace_id",
                match=models.MatchValue(value=trace_id)
            ))

        # Time range
        if timestamp_from or timestamp_to:
            time_conditions = []
            if timestamp_from:
                time_conditions.append(models.FieldCondition(
                    key="timestamp",
                    range=models.DatetimeRange(gte=timestamp_from)
                ))
            if timestamp_to:
                time_conditions.append(models.FieldCondition(
                    key="timestamp",
                    range=models.DatetimeRange(lte=timestamp_to)
                ))
            if time_conditions:
                conditions.append(models.Filter(must=time_conditions))

        return models.Filter(must=conditions) if conditions else None