"""GraphQL Context for injecting services."""

from typing import Any, Dict

from strawberry.fastapi import BaseContext

from src.services.firebase_service import firebase_service
from src.services.qdrant_service import qdrant_service
from src.services.redis_service import redis_service


class GraphQLContext(BaseContext):
    def __init__(self):
        super().__init__()
        self.redis = redis_service
        self.firebase = firebase_service
        # BigQuery client creation requires ADC; keep it lazy in resolvers.
        self.bq_client = None
        self.qdrant = qdrant_service


def get_context() -> GraphQLContext:
    return GraphQLContext()
