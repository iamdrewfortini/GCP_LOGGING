"""BigQuery provisioning for chat_analytics dataset.

This module provides idempotent creation of the chat_analytics dataset
and its tables for storing AI chat events and analytics.

Usage:
    python -m src.cli provision-bq --dataset chat_analytics
    python -m src.cli provision-bq --dataset chat_analytics --dry-run
"""

import argparse
import os
import sys
from typing import Optional
from google.cloud import bigquery
from google.api_core.exceptions import Conflict, NotFound

# Default configuration
DEFAULT_PROJECT = os.getenv("PROJECT_ID", "diatonic-ai-gcp")
DEFAULT_LOCATION = os.getenv("BQ_LOCATION", "US")
DEFAULT_DATASET = "chat_analytics"
PARTITION_EXPIRATION_DAYS = 2555  # ~7 years


def get_chat_events_schema() -> list[bigquery.SchemaField]:
    """Get schema for chat_events table.

    This is the primary append-only log for all chat activity.
    """
    return [
        bigquery.SchemaField("event_id", "STRING", mode="REQUIRED",
                            description="UUIDv4 unique event identifier"),
        bigquery.SchemaField("event_timestamp", "TIMESTAMP", mode="REQUIRED",
                            description="Event timestamp (partition key)"),
        bigquery.SchemaField("session_id", "STRING", mode="REQUIRED",
                            description="Chat session identifier"),
        bigquery.SchemaField("user_id", "STRING", mode="REQUIRED",
                            description="User identifier"),
        bigquery.SchemaField("event_type", "STRING", mode="REQUIRED",
                            description="Event type: message_sent, tool_start, tool_end, error"),
        bigquery.SchemaField("role", "STRING", mode="NULLABLE",
                            description="Message role: user, assistant, system, tool"),
        bigquery.SchemaField("content", "JSON", mode="NULLABLE",
                            description="Event payload (message text, tool args)"),
        bigquery.SchemaField("metadata", "JSON", mode="NULLABLE",
                            description="Event metadata (latency, tokens, cost)"),
        bigquery.SchemaField("token_usage", "RECORD", mode="NULLABLE",
                            description="Token usage for this event",
                            fields=[
                                bigquery.SchemaField("prompt_tokens", "INT64"),
                                bigquery.SchemaField("completion_tokens", "INT64"),
                                bigquery.SchemaField("total_tokens", "INT64"),
                            ]),
        bigquery.SchemaField("client_info", "JSON", mode="NULLABLE",
                            description="Client metadata (user-agent, locale)"),
    ]


def get_tool_invocations_schema() -> list[bigquery.SchemaField]:
    """Get schema for tool_invocations table.

    Detailed tracking of tool executions for analytics.
    """
    return [
        bigquery.SchemaField("invocation_id", "STRING", mode="REQUIRED",
                            description="UUIDv4 unique invocation identifier"),
        bigquery.SchemaField("session_id", "STRING", mode="REQUIRED",
                            description="Chat session identifier"),
        bigquery.SchemaField("user_id", "STRING", mode="REQUIRED",
                            description="User identifier"),
        bigquery.SchemaField("tool_name", "STRING", mode="REQUIRED",
                            description="Name of the tool invoked"),
        bigquery.SchemaField("started_at", "TIMESTAMP", mode="REQUIRED",
                            description="Tool execution start time (partition key)"),
        bigquery.SchemaField("ended_at", "TIMESTAMP", mode="NULLABLE",
                            description="Tool execution end time"),
        bigquery.SchemaField("duration_ms", "INT64", mode="NULLABLE",
                            description="Execution duration in milliseconds"),
        bigquery.SchemaField("status", "STRING", mode="REQUIRED",
                            description="Execution status: running, success, failure"),
        bigquery.SchemaField("input_args", "JSON", mode="NULLABLE",
                            description="Tool input arguments (redacted)"),
        bigquery.SchemaField("output_summary", "STRING", mode="NULLABLE",
                            description="Brief output summary"),
        bigquery.SchemaField("error_message", "STRING", mode="NULLABLE",
                            description="Error message if failed"),
        bigquery.SchemaField("bytes_billed", "INT64", mode="NULLABLE",
                            description="BigQuery bytes billed (for BQ tools)"),
        bigquery.SchemaField("tokens_used", "INT64", mode="NULLABLE",
                            description="Tokens consumed by tool output"),
    ]


def get_embeddings_metadata_schema() -> list[bigquery.SchemaField]:
    """Get schema for embeddings_metadata table (Phase 2).

    Tracks embedding generation for vector search analytics.
    """
    return [
        bigquery.SchemaField("embedding_id", "STRING", mode="REQUIRED",
                            description="UUIDv4 unique embedding identifier (matches Qdrant vector ID)"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED",
                            description="Embedding creation timestamp (partition key)"),
        bigquery.SchemaField("project_id", "STRING", mode="REQUIRED",
                            description="Project ID for tenant isolation"),
        bigquery.SchemaField("source_type", "STRING", mode="REQUIRED",
                            description="Source type: log, chat_message, document"),
        bigquery.SchemaField("text_hash", "STRING", mode="REQUIRED",
                            description="SHA-256 hash of source text (for deduplication)"),
        bigquery.SchemaField("content_preview", "STRING", mode="NULLABLE",
                            description="First 500 chars of source text"),
        bigquery.SchemaField("embedding_model", "STRING", mode="REQUIRED",
                            description="Model used for embedding generation"),
        bigquery.SchemaField("embedding_dim", "INT64", mode="REQUIRED",
                            description="Embedding vector dimension (e.g., 768)"),
        bigquery.SchemaField("collection_name", "STRING", mode="REQUIRED",
                            description="Qdrant collection name"),
        bigquery.SchemaField("metadata", "JSON", mode="NULLABLE",
                            description="Additional metadata (severity, service, etc.)"),
        bigquery.SchemaField("processing_time_ms", "INT64", mode="NULLABLE",
                            description="Time to generate embedding in milliseconds"),
        bigquery.SchemaField("status", "STRING", mode="REQUIRED",
                            description="Status: success, failure, duplicate"),
        bigquery.SchemaField("error_message", "STRING", mode="NULLABLE",
                            description="Error message if failed"),
    ]


def create_dataset(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
    location: str,
    dry_run: bool = False,
) -> bool:
    """Create dataset if it doesn't exist.

    Args:
        client: BigQuery client
        project_id: GCP project ID
        dataset_id: Dataset name
        location: BigQuery location
        dry_run: If True, only print what would be done

    Returns:
        True if created or already exists, False on error
    """
    dataset_ref = f"{project_id}.{dataset_id}"

    if dry_run:
        print(f"[DRY RUN] Would create dataset: {dataset_ref}")
        print(f"  Location: {location}")
        return True

    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = location
    dataset.description = "Chat analytics dataset for Glass Pane AI"

    try:
        client.create_dataset(dataset, exists_ok=True)
        print(f"Created dataset: {dataset_ref}")
        return True
    except Exception as e:
        print(f"Error creating dataset {dataset_ref}: {e}")
        return False


def create_table(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
    table_id: str,
    schema: list[bigquery.SchemaField],
    partition_field: str,
    clustering_fields: list[str],
    partition_expiration_days: int,
    dry_run: bool = False,
) -> bool:
    """Create table with partitioning and clustering.

    Args:
        client: BigQuery client
        project_id: GCP project ID
        dataset_id: Dataset name
        table_id: Table name
        schema: Table schema
        partition_field: Field to partition by (must be TIMESTAMP or DATE)
        clustering_fields: Fields to cluster by
        partition_expiration_days: Days before partitions expire
        dry_run: If True, only print what would be done

    Returns:
        True if created or already exists, False on error
    """
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    if dry_run:
        print(f"[DRY RUN] Would create table: {table_ref}")
        print(f"  Partition by: DATE({partition_field})")
        print(f"  Cluster by: {', '.join(clustering_fields)}")
        print(f"  Partition expiration: {partition_expiration_days} days")
        print(f"  Schema fields: {len(schema)}")
        for field in schema:
            print(f"    - {field.name}: {field.field_type} ({field.mode})")
        return True

    table = bigquery.Table(table_ref, schema=schema)

    # Set time partitioning
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field=partition_field,
        expiration_ms=partition_expiration_days * 24 * 60 * 60 * 1000,
    )

    # Set clustering
    table.clustering_fields = clustering_fields

    try:
        client.create_table(table, exists_ok=True)
        print(f"Created table: {table_ref}")
        return True
    except Exception as e:
        print(f"Error creating table {table_ref}: {e}")
        return False


def create_views(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
    dry_run: bool = False,
) -> bool:
    """Create helpful views for analytics.

    Args:
        client: BigQuery client
        project_id: GCP project ID
        dataset_id: Dataset name
        dry_run: If True, only print what would be done

    Returns:
        True if created, False on error
    """
    views = [
        {
            "name": "v_chat_sessions_summary",
            "description": "Summary of chat sessions with message counts and token usage",
            "query": f"""
                SELECT
                    session_id,
                    user_id,
                    MIN(event_timestamp) AS started_at,
                    MAX(event_timestamp) AS ended_at,
                    COUNT(*) AS event_count,
                    COUNTIF(event_type = 'message_sent') AS message_count,
                    COUNTIF(event_type = 'tool_start') AS tool_count,
                    SUM(IFNULL(token_usage.total_tokens, 0)) AS total_tokens
                FROM `{project_id}.{dataset_id}.chat_events`
                GROUP BY session_id, user_id
            """,
        },
        {
            "name": "v_tool_usage_summary",
            "description": "Tool usage analytics by tool name",
            "query": f"""
                SELECT
                    tool_name,
                    COUNT(*) AS invocation_count,
                    COUNTIF(status = 'success') AS success_count,
                    COUNTIF(status = 'failure') AS failure_count,
                    AVG(duration_ms) AS avg_duration_ms,
                    SUM(IFNULL(bytes_billed, 0)) AS total_bytes_billed,
                    SUM(IFNULL(tokens_used, 0)) AS total_tokens
                FROM `{project_id}.{dataset_id}.tool_invocations`
                GROUP BY tool_name
            """,
        },
        {
            "name": "v_embeddings_summary",
            "description": "Embedding generation analytics by source type (Phase 2)",
            "query": f"""
                SELECT
                    project_id,
                    source_type,
                    DATE(created_at) AS created_date,
                    COUNT(*) AS total_embeddings,
                    COUNTIF(status = 'success') AS success_count,
                    COUNTIF(status = 'failure') AS failure_count,
                    COUNTIF(status = 'duplicate') AS duplicate_count,
                    AVG(processing_time_ms) AS avg_processing_time_ms,
                    AVG(embedding_dim) AS embedding_dim
                FROM `{project_id}.{dataset_id}.embeddings_metadata`
                GROUP BY project_id, source_type, DATE(created_at)
            """,
        },
    ]

    success = True
    for view_def in views:
        view_ref = f"{project_id}.{dataset_id}.{view_def['name']}"

        if dry_run:
            print(f"[DRY RUN] Would create view: {view_ref}")
            print(f"  Description: {view_def['description']}")
            continue

        view = bigquery.Table(view_ref)
        view.view_query = view_def["query"]
        view.description = view_def["description"]

        try:
            # Delete existing view first (views can't be updated in place easily)
            try:
                client.delete_table(view_ref)
            except NotFound:
                pass

            client.create_table(view)
            print(f"Created view: {view_ref}")
        except Exception as e:
            print(f"Error creating view {view_ref}: {e}")
            success = False

    return success


def provision_chat_analytics(
    project_id: str = DEFAULT_PROJECT,
    dataset_id: str = DEFAULT_DATASET,
    location: str = DEFAULT_LOCATION,
    dry_run: bool = False,
) -> bool:
    """Provision the chat_analytics dataset with all tables and views.

    This is idempotent - safe to run multiple times.

    Args:
        project_id: GCP project ID
        dataset_id: Dataset name (default: chat_analytics)
        location: BigQuery location (default: US)
        dry_run: If True, only print what would be done

    Returns:
        True if all operations succeeded
    """
    print(f"Provisioning BigQuery dataset: {project_id}.{dataset_id}")
    print(f"Location: {location}")
    print(f"Dry run: {dry_run}")
    print("-" * 50)

    if dry_run:
        client = None
    else:
        client = bigquery.Client(project=project_id)

    success = True

    # Create dataset
    if client or dry_run:
        if not create_dataset(client, project_id, dataset_id, location, dry_run):
            success = False

    # Create chat_events table
    if client or dry_run:
        if not create_table(
            client,
            project_id,
            dataset_id,
            "chat_events",
            get_chat_events_schema(),
            partition_field="event_timestamp",
            clustering_fields=["session_id", "user_id", "event_type"],
            partition_expiration_days=PARTITION_EXPIRATION_DAYS,
            dry_run=dry_run,
        ):
            success = False

    # Create tool_invocations table
    if client or dry_run:
        if not create_table(
            client,
            project_id,
            dataset_id,
            "tool_invocations",
            get_tool_invocations_schema(),
            partition_field="started_at",
            clustering_fields=["tool_name", "status", "session_id"],
            partition_expiration_days=PARTITION_EXPIRATION_DAYS,
            dry_run=dry_run,
        ):
            success = False

    # Create embeddings_metadata table (Phase 2)
    if client or dry_run:
        if not create_table(
            client,
            project_id,
            dataset_id,
            "embeddings_metadata",
            get_embeddings_metadata_schema(),
            partition_field="created_at",
            clustering_fields=["project_id", "source_type", "status"],
            partition_expiration_days=PARTITION_EXPIRATION_DAYS,
            dry_run=dry_run,
        ):
            success = False

    # Create views
    if client or dry_run:
        if not create_views(client, project_id, dataset_id, dry_run):
            success = False

    print("-" * 50)
    if success:
        print("Provisioning completed successfully!")
    else:
        print("Provisioning completed with errors.")

    return success


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Provision BigQuery datasets for Glass Pane AI"
    )
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=f"Dataset name (default: {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"GCP project ID (default: {DEFAULT_PROJECT})",
    )
    parser.add_argument(
        "--location",
        default=DEFAULT_LOCATION,
        help=f"BigQuery location (default: {DEFAULT_LOCATION})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making changes",
    )

    args = parser.parse_args()

    success = provision_chat_analytics(
        project_id=args.project,
        dataset_id=args.dataset,
        location=args.location,
        dry_run=args.dry_run,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
