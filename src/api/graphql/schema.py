"""
GraphQL Schema for Glass Pane API

Version: v1
Endpoint: /graphql
"""

import strawberry
from typing import List, Optional
from strawberry.fastapi import BaseContext
from src.api.graphql.types import (
    LogEntry, LogQuery, Health, ServiceInfo, LogFilter,
    RunQueryInput, EnqueueEmbeddingJobInput, SetTagInput,
    EmbeddingJob, ChatEvent
)
from src.api.graphql.resolvers import (
    resolve_logs, resolve_log, resolve_services, resolve_health,
    resolve_jobs, resolve_chat, resolve_run_query,
    resolve_enqueue_embedding_job, resolve_mark_reviewed, resolve_set_tag,
    resolve_log_stream
)

# Queries
@strawberry.type
class Query:
    @strawberry.field
    def logs(self, filter: LogFilter, info: strawberry.Info[BaseContext]) -> LogQuery:
        return resolve_logs(filter, info.context)

    @strawberry.field
    def log(self, id: str, info: strawberry.Info[BaseContext]) -> Optional[LogEntry]:
        return resolve_log(id, info.context)

    @strawberry.field
    def services(self, info: strawberry.Info[BaseContext]) -> List[ServiceInfo]:
        return resolve_services(info.context)

    @strawberry.field
    def health(self, info: strawberry.Info[BaseContext]) -> Health:
        return resolve_health(info.context)

    @strawberry.field
    def jobs(self, filter: Optional[LogFilter] = None, info: strawberry.Info[BaseContext] = None) -> List[EmbeddingJob]:
        return resolve_jobs(filter, info.context)

    @strawberry.field
    def chat(self, session_id: str, info: strawberry.Info[BaseContext]) -> List[ChatEvent]:
        return resolve_chat(session_id, info.context)

# Mutations
@strawberry.type
class Mutation:
    @strawberry.field
    def run_query(self, input: RunQueryInput, info: strawberry.Info[BaseContext]) -> LogQuery:
        return resolve_run_query(input, info.context)

    @strawberry.field
    def enqueue_embedding_job(self, input: EnqueueEmbeddingJobInput, info: strawberry.Info[BaseContext]) -> EmbeddingJob:
        return resolve_enqueue_embedding_job(input, info.context)

    @strawberry.field
    def mark_reviewed(self, id: str, info: strawberry.Info[BaseContext]) -> bool:
        return resolve_mark_reviewed(id, info.context)

    @strawberry.field
    def set_tag(self, input: SetTagInput, info: strawberry.Info[BaseContext]) -> bool:
        return resolve_set_tag(input, info.context)

# Subscriptions (placeholder, use Firebase for now)
@strawberry.type
class Subscription:
    @strawberry.subscription
    async def log_stream(self, filter: LogFilter, info: strawberry.Info[BaseContext]) -> LogEntry:
        async for entry in resolve_log_stream(filter, info.context):
            yield entry

# Schema
schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)