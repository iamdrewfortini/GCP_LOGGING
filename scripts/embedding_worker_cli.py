#!/usr/bin/env python3
"""
Embedding Worker CLI

Command-line interface for managing the embedding worker pipeline.

Usage:
    python -m scripts.embedding_worker_cli start       # Start worker
    python -m scripts.embedding_worker_cli status      # Check status
    python -m scripts.embedding_worker_cli enqueue     # Enqueue tables
    python -m scripts.embedding_worker_cli progress    # View progress
    python -m scripts.embedding_worker_cli reset       # Reset checkpoints
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.live import Live

# Setup paths
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from src.services.redis_service import redis_service
from src.services.embedding_queue import embedding_queue, EmbeddingJob, QUEUE_BACKLOG, QUEUE_PRIORITY
from src.services.batch_optimizer import batch_optimizer
from src.workers.embedding_worker import EmbeddingWorker, BigQueryLogFetcher

console = Console()
logger = logging.getLogger(__name__)


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def cli(verbose: bool):
    """Embedding Worker CLI - Manage the BigQuery to Qdrant embedding pipeline."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


@cli.command()
@click.option('--project-id', default=None, help='GCP project ID')
@click.option('--embed-model', default='qwen3-embedding:0.6b', help='Ollama embedding model')
@click.option('--collection', default='logs_embedded_qwen3', help='Qdrant collection name')
@click.option('--vector-size', default=1024, help='Vector dimension size')
def start(project_id: str, embed_model: str, collection: str, vector_size: int):
    """Start the embedding worker daemon."""
    console.print(Panel.fit(
        "[bold green]Starting Embedding Worker[/bold green]\n"
        f"Project: {project_id or os.getenv('PROJECT_ID', 'diatonic-ai-gcp')}\n"
        f"Model: {embed_model}\n"
        f"Collection: {collection}\n"
        f"Vector Size: {vector_size}",
        title="Worker Configuration"
    ))

    worker = EmbeddingWorker(
        project_id=project_id,
        embed_model=embed_model,
        collection=collection,
        vector_size=vector_size
    )

    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker stopped by user[/yellow]")


@cli.command()
def status():
    """Check the status of queues and worker."""
    # Check Redis connection
    redis_ok = redis_service.ping()
    console.print(f"Redis Connection: {'[green]OK[/green]' if redis_ok else '[red]FAILED[/red]'}")

    if not redis_ok:
        console.print("[red]Cannot connect to Redis. Check your configuration.[/red]")
        return

    # Queue stats
    queue_stats = embedding_queue.get_queue_stats()

    table = Table(title="Queue Status")
    table.add_column("Queue", style="cyan")
    table.add_column("Count", justify="right", style="magenta")

    table.add_row("Priority", str(queue_stats["priority"]))
    table.add_row("Backlog", str(queue_stats["backlog"]))
    table.add_row("Failed", str(queue_stats["failed"]))
    table.add_row("[bold]Total Pending[/bold]", f"[bold]{queue_stats['total_pending']}[/bold]")

    console.print(table)

    # Optimizer stats
    opt_stats = batch_optimizer.get_stats()

    console.print("\n[bold]Batch Optimizer:[/bold]")
    console.print(f"  Embed batch size: {opt_stats['embed_batch_size']}")
    console.print(f"  Upsert batch size: {opt_stats['upsert_batch_size']}")

    console.print("\n[bold]Ollama Metrics:[/bold]")
    console.print(f"  Avg latency: {opt_stats['ollama']['avg_latency_ms']:.1f}ms")
    console.print(f"  Samples: {opt_stats['ollama']['samples']}")
    console.print(f"  Errors: {opt_stats['ollama']['error_count']}")

    console.print("\n[bold]Qdrant Metrics:[/bold]")
    console.print(f"  Avg latency: {opt_stats['qdrant']['avg_latency_ms']:.1f}ms")
    console.print(f"  Samples: {opt_stats['qdrant']['samples']}")
    console.print(f"  Errors: {opt_stats['qdrant']['error_count']}")


@cli.command()
@click.option('--all', 'enqueue_all', is_flag=True, help='Enqueue all discovered tables')
@click.option('--table', 'table_name', default=None, help='Specific table to enqueue (dataset.table)')
@click.option('--hours', default=24, help='Time window for log discovery (hours)')
@click.option('--batch-size', default=50, help='Batch size for jobs')
@click.option('--priority', is_flag=True, help='Use priority queue')
@click.option('--project-id', default=None, help='GCP project ID')
def enqueue(enqueue_all: bool, table_name: str, hours: int, batch_size: int, priority: bool, project_id: str):
    """Enqueue tables for embedding processing."""
    project = project_id or os.getenv("PROJECT_ID", "diatonic-ai-gcp")

    if not enqueue_all and not table_name:
        console.print("[red]Please specify --all or --table[/red]")
        return

    if table_name:
        # Enqueue specific table
        checkpoint = redis_service.get_checkpoint(table_name)
        offset = checkpoint.get("offset", 0) if checkpoint else 0

        job_id = embedding_queue.enqueue_table(
            table=table_name,
            offset=offset,
            batch_size=batch_size,
            priority=priority
        )

        if job_id:
            console.print(f"[green]Enqueued {table_name} from offset {offset}[/green]")
            console.print(f"Job ID: {job_id}")
        else:
            console.print(f"[red]Failed to enqueue {table_name}[/red]")
        return

    # Discover and enqueue all tables
    console.print(f"[cyan]Discovering log tables (last {hours} hours)...[/cyan]")

    fetcher = BigQueryLogFetcher(project)
    tables = fetcher.discover_log_tables(hours=hours)

    if not tables:
        console.print("[yellow]No log tables found[/yellow]")
        return

    console.print(f"Found {len(tables)} tables with recent data")

    table_view = Table(title="Tables to Enqueue")
    table_view.add_column("Table", style="cyan")
    table_view.add_column("Rows", justify="right")
    table_view.add_column("Current Offset", justify="right")
    table_view.add_column("Status")

    enqueued = 0
    for t in tables:
        full_name = t["full_name"]
        row_count = t["row_count"]

        checkpoint = redis_service.get_checkpoint(full_name)
        offset = checkpoint.get("offset", 0) if checkpoint else 0

        if offset >= row_count:
            table_view.add_row(full_name, str(row_count), str(offset), "[green]Complete[/green]")
            continue

        job_id = embedding_queue.enqueue_table(
            table=full_name,
            offset=offset,
            batch_size=batch_size,
            priority=priority
        )

        if job_id:
            enqueued += 1
            table_view.add_row(full_name, str(row_count), str(offset), "[yellow]Enqueued[/yellow]")
        else:
            table_view.add_row(full_name, str(row_count), str(offset), "[red]Failed[/red]")

    console.print(table_view)
    console.print(f"\n[green]Enqueued {enqueued} tables for processing[/green]")


@cli.command()
def progress():
    """View embedding progress for all tables."""
    checkpoints = redis_service.get_all_checkpoints()
    global_checkpoint = redis_service.get_global_checkpoint()

    if global_checkpoint:
        console.print(Panel.fit(
            f"[bold]Total Embedded:[/bold] {global_checkpoint.get('total_embedded', 0):,}\n"
            f"[bold]Tables Completed:[/bold] {global_checkpoint.get('tables_completed', 0)}\n"
            f"[bold]Last Update:[/bold] {global_checkpoint.get('updated_at', 'N/A')}",
            title="Global Progress"
        ))

    if not checkpoints:
        console.print("[yellow]No table checkpoints found[/yellow]")
        return

    table = Table(title="Table Progress")
    table.add_column("Table", style="cyan")
    table.add_column("Offset", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Progress", justify="right")
    table.add_column("Last Update")

    for table_name, data in sorted(checkpoints.items()):
        offset = data.get("offset", 0)
        total = data.get("total", 0)
        updated = data.get("updated_at", "N/A")

        if total > 0:
            pct = (offset / total) * 100
            progress_str = f"{pct:.1f}%"
        else:
            progress_str = "N/A"

        table.add_row(table_name, str(offset), str(total), progress_str, updated[:19] if updated != "N/A" else updated)

    console.print(table)


@cli.command()
@click.option('--confirm', is_flag=True, help='Confirm reset')
@click.option('--queues', is_flag=True, help='Also clear queues')
def reset(confirm: bool, queues: bool):
    """Reset checkpoints and optionally clear queues."""
    if not confirm:
        console.print("[yellow]Please add --confirm to reset checkpoints[/yellow]")
        return

    # Reset checkpoints
    deleted = redis_service.reset_all_checkpoints()
    console.print(f"[green]Deleted {deleted} checkpoint keys[/green]")

    # Reset metrics
    batch_optimizer.reset_metrics()
    console.print("[green]Reset optimizer metrics[/green]")

    if queues:
        cleared = embedding_queue.clear_all_queues()
        console.print(f"[green]Cleared queues: priority={cleared['priority']}, backlog={cleared['backlog']}, failed={cleared['failed']}[/green]")


@cli.command()
@click.option('--count', default=10, help='Number of jobs to retry')
@click.option('--priority', is_flag=True, help='Move to priority queue')
def retry(count: int, priority: bool):
    """Retry failed jobs."""
    retried = embedding_queue.retry_failed(count=count, to_priority=priority)
    target = "priority" if priority else "backlog"
    console.print(f"[green]Moved {retried} jobs from failed to {target} queue[/green]")


@cli.command()
@click.option('--count', default=5, help='Number of jobs to show per queue')
def peek(count: int):
    """Peek at jobs in queues."""
    queues = embedding_queue.peek_queues(count=count)

    for queue_name, jobs in queues.items():
        if not jobs:
            console.print(f"\n[dim]{queue_name}: empty[/dim]")
            continue

        console.print(f"\n[bold]{queue_name}:[/bold] ({len(jobs)} shown)")
        for job in jobs:
            console.print(f"  - {job.get('table', 'N/A')} @ offset {job.get('offset', 0)} (retry: {job.get('retry_count', 0)})")


@cli.command()
@click.option('--project-id', default=None, help='GCP project ID')
@click.option('--hours', default=24, help='Time window (hours)')
def discover(project_id: str, hours: int):
    """Discover available log tables in BigQuery."""
    project = project_id or os.getenv("PROJECT_ID", "diatonic-ai-gcp")

    console.print(f"[cyan]Discovering log tables in {project} (last {hours} hours)...[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Scanning datasets...", total=None)

        fetcher = BigQueryLogFetcher(project)
        tables = fetcher.discover_log_tables(hours=hours)

        progress.update(task, completed=True)

    if not tables:
        console.print("[yellow]No log tables found[/yellow]")
        return

    table_view = Table(title=f"Discovered Log Tables ({len(tables)} found)")
    table_view.add_column("Dataset", style="cyan")
    table_view.add_column("Table")
    table_view.add_column("Rows", justify="right", style="magenta")

    total_rows = 0
    for t in sorted(tables, key=lambda x: x["row_count"], reverse=True):
        table_view.add_row(t["dataset"], t["table"], f"{t['row_count']:,}")
        total_rows += t["row_count"]

    console.print(table_view)
    console.print(f"\n[bold]Total rows: {total_rows:,}[/bold]")


if __name__ == "__main__":
    cli()
