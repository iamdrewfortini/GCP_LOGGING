"""
GraphQL Context for injecting services
"""

from typing import Dict, Any
from strawberry.fastapi import BaseContext
from src.services.redis_service import redis_service
from src.services.firebase_service import firebase_service
from src.services.bigquery_service import get_bq_client
from src.services.qdrant_service import qdrant_service

class GraphQLContext(BaseContext):
    def __init__(self):
        super().__init__()
        self.redis = redis_service
        self.firebase = firebase_service
        self.bq_client = get_bq_client()
        self.qdrant = qdrant_service

def get_context() -> GraphQLContext:
    return GraphQLContext()