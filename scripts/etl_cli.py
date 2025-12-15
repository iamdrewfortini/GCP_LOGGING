#!/usr/bin/env python3
"""
ETL Pipeline CLI

Command-line interface for managing the log ETL pipeline.

Usage:
    python -m scripts.etl_cli run --hours 24
    python -m scripts.etl_cli status
    python -m scripts.etl_cli discover
    python -m scripts.etl_cli schema --apply
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Setup paths
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from src.etl.pipeline import ETLPipeline, PipelineConfig
from src.etl.stream_manager import StreamManager
from src.etl.loader import LogLoader

console = Console()
logger = logging.getLogger(__name__)


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def cli(verbose: bool):
    """ETL Pipeline CLI - Normalize GCP logs into master_logs table."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


@cli.command()
@click.option('--hours', default=None, type=int, help='Hours lookback (None=all time)')
@click.option('--stream', 'stream_id', default=None, help='Specific stream to process')
@click.option('--enable-ai', is_flag=True, help='Enable Vertex AI enrichment')
@click.option('--batch-size', default=1000, help='Records per batch')
@click.option('--project-id', default='diatonic-ai-gcp', help='GCP project ID')
def run(hours: int, stream_id: str, enable_ai: bool, batch_size: int, project_id: str):
    """Run the ETL pipeline."""
    console.print(Panel.fit(
        f"[bold green]Running ETL Pipeline[/bold green]\n"
        f"Project: {project_id}\n"
        f"Hours: {hours or 'All time'}\n"
        f"AI Enrichment: {enable_ai}\n"
        f"Batch Size: {batch_size}",
        title="ETL Configuration"
    ))

    config = PipelineConfig(
        project_id=project_id,
        enable_ai_enrichment=enable_ai,
        batch_size=batch_size,
        hours_lookback=hours,
    )

    pipeline = ETLPipeline(config)

    # Progress callback
    def on_progress(stream_id: str, loaded: int, extracted: int):
        pct = (loaded / extracted * 100) if extracted else 0
        console.print(f"  [{stream_id}] {loaded}/{extracted} ({pct:.1f}%)")

    pipeline.on_progress = on_progress

    with console.status("[bold green]Processing streams..."):
        if stream_id:
            result = pipeline.run_single_stream(stream_id)
        elif hours:
            result = pipeline.run_incremental(hours=hours)
        else:
            result = pipeline.run()

    # Display results
    console.print("\n")
    status_color = "green" if result.status == "COMPLETED" else "yellow" if result.status == "PARTIAL" else "red"
    console.print(Panel.fit(
        f"[bold {status_color}]Status: {result.status}[/bold {status_color}]\n"
        f"Pipeline ID: {result.pipeline_id}\n"
        f"Duration: {(result.completed_at - result.started_at).total_seconds():.1f}s\n\n"
        f"[bold]Metrics:[/bold]\n"
        f"  Streams Processed: {result.streams_processed}\n"
        f"  Total Extracted: {result.total_extracted:,}\n"
        f"  Total Normalized: {result.total_normalized:,}\n"
        f"  Total Transformed: {result.total_transformed:,}\n"
        f"  Total Loaded: {result.total_loaded:,}\n"
        f"  Errors: {len(result.errors)}",
        title="Pipeline Results"
    ))

    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in result.errors[:5]:
            console.print(f"  - {error}")
        if len(result.errors) > 5:
            console.print(f"  ... and {len(result.errors) - 5} more")


@cli.command()
@click.option('--project-id', default='diatonic-ai-gcp', help='GCP project ID')
def status(project_id: str):
    """Check ETL pipeline status and stream information."""
    stream_manager = StreamManager(project_id)

    console.print("[bold]Discovering streams...[/bold]")
    streams = stream_manager.get_all_streams()

    if not streams:
        # Try to discover
        streams = stream_manager.discover_streams()

    table = Table(title=f"Log Streams ({len(streams)} found)")
    table.add_column("Stream ID", style="cyan")
    table.add_column("Direction")
    table.add_column("Flow")
    table.add_column("Last Sync Offset", justify="right")
    table.add_column("Total Synced", justify="right")

    for stream in sorted(streams, key=lambda s: s.stream_id):
        table.add_row(
            stream.stream_id,
            stream.direction.value,
            stream.flow.value,
            f"{stream.last_sync_offset:,}",
            f"{stream.total_records_synced:,}"
        )

    console.print(table)

    # Show totals
    total_synced = sum(s.total_records_synced for s in streams)
    console.print(f"\n[bold]Total records synced across all streams: {total_synced:,}[/bold]")


@cli.command()
@click.option('--hours', default=168, help='Hours to look back for discovery')
@click.option('--project-id', default='diatonic-ai-gcp', help='GCP project ID')
def discover(hours: int, project_id: str):
    """Discover log streams from BigQuery."""
    console.print(f"[cyan]Discovering log streams (last {hours} hours)...[/cyan]")

    stream_manager = StreamManager(project_id)
    streams = stream_manager.discover_streams()

    table = Table(title=f"Discovered Streams ({len(streams)} found)")
    table.add_column("Stream ID", style="cyan")
    table.add_column("Direction")
    table.add_column("Flow")
    table.add_column("Row Count", justify="right")

    total_rows = 0
    for stream in sorted(streams, key=lambda s: s.config.get("row_count", 0), reverse=True):
        row_count = stream.config.get("row_count", 0)
        total_rows += row_count
        table.add_row(
            stream.stream_id,
            stream.direction.value,
            stream.flow.value,
            f"{row_count:,}"
        )

    console.print(table)
    console.print(f"\n[bold]Total rows available: {total_rows:,}[/bold]")

    # Ask to register
    if click.confirm("\nRegister these streams?"):
        for stream in streams:
            stream_manager.register_stream(stream)
        console.print(f"[green]Registered {len(streams)} streams[/green]")


@cli.command()
@click.option('--apply', is_flag=True, help='Apply schema to BigQuery')
@click.option('--project-id', default='diatonic-ai-gcp', help='GCP project ID')
def schema(apply: bool, project_id: str):
    """View or apply the master_logs schema."""
    schema_path = REPO_ROOT / "schemas" / "bigquery" / "master_logs.sql"

    if not schema_path.exists():
        console.print(f"[red]Schema file not found: {schema_path}[/red]")
        return

    with open(schema_path) as f:
        schema_sql = f.read()

    console.print(Panel(schema_sql[:2000] + "...", title="master_logs Schema (truncated)"))

    if apply:
        console.print("\n[yellow]Applying schema to BigQuery...[/yellow]")
        loader = LogLoader(project_id)
        loader.ensure_tables()
        console.print("[green]Schema applied successfully[/green]")
    else:
        console.print("\n[dim]Use --apply to create tables in BigQuery[/dim]")


@cli.command()
@click.option('--stream', 'stream_id', required=True, help='Stream to check')
@click.option('--limit', default=10, help='Number of records to show')
@click.option('--project-id', default='diatonic-ai-gcp', help='GCP project ID')
def preview(stream_id: str, limit: int, project_id: str):
    """Preview raw logs from a stream."""
    from src.etl.extractor import LogExtractor
    from src.etl.stream_manager import LogStream

    console.print(f"[cyan]Previewing {stream_id}...[/cyan]")

    # Parse stream ID
    parts = stream_id.split(".")
    if len(parts) != 2:
        console.print("[red]Invalid stream ID format. Use: dataset.table[/red]")
        return

    dataset, table = parts
    stream = LogStream.from_table(dataset, table, project_id)

    extractor = LogExtractor(project_id)
    records = list(extractor.extract_from_stream(stream, limit=limit))

    if not records:
        console.print("[yellow]No records found[/yellow]")
        return

    for i, record in enumerate(records[:limit]):
        console.print(f"\n[bold]Record {i+1}:[/bold]")
        console.print(f"  Timestamp: {record.timestamp}")
        console.print(f"  Severity: {record.severity}")
        console.print(f"  Resource: {record.resource_type}")

        if record.text_payload:
            console.print(f"  Text: {record.text_payload[:200]}...")
        if record.json_payload:
            console.print(f"  JSON: {json.dumps(record.json_payload, default=str)[:200]}...")
        if record.proto_payload:
            console.print(f"  Proto: {json.dumps(record.proto_payload, default=str)[:200]}...")


@cli.command()
@click.option('--project-id', default='diatonic-ai-gcp', help='GCP project ID')
def query(project_id: str):
    """Query the master_logs table."""
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)

    # Check if table exists
    try:
        table = client.get_table(f"{project_id}.central_logging_v1.master_logs")
        console.print(f"[green]master_logs table exists: {table.num_rows:,} rows[/green]")
    except Exception as e:
        console.print(f"[red]master_logs table not found: {e}[/red]")
        return

    # Show sample query
    console.print("\n[bold]Sample queries:[/bold]")
    console.print("""
    -- Count by severity
    SELECT severity, COUNT(*) as cnt
    FROM `diatonic-ai-gcp.central_logging_v1.master_logs`
    WHERE _partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
    GROUP BY severity
    ORDER BY cnt DESC;

    -- Errors by service
    SELECT service_name, COUNT(*) as errors
    FROM `diatonic-ai-gcp.central_logging_v1.master_logs`
    WHERE is_error = TRUE
      AND _partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
    GROUP BY service_name
    ORDER BY errors DESC
    LIMIT 10;

    -- Stream statistics
    SELECT stream_id, stream_direction, stream_flow, COUNT(*) as cnt
    FROM `diatonic-ai-gcp.central_logging_v1.master_logs`
    WHERE _partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
    GROUP BY stream_id, stream_direction, stream_flow
    ORDER BY cnt DESC;
    """)


if __name__ == "__main__":
    cli()
