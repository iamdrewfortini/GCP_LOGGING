#!/usr/bin/env python3
"""
BigQuery migration runner.

Features:
 - Fetches latest origin/main (unless --skip-git-fetch).
 - Detects SQL migrations in infra/bigquery (prefix-ordered).
 - Ensures a schema_migrations tracking table exists.
 - Applies new migrations and records checksum + applied_at.
 - Warns if checksum drift is detected for already-applied versions.

Env/args:
 - BQ_PROJECT (default: client.project)
 - BQ_DATASET (default: central_logging_v1)
 - BQ_LOCATION (default: US)
 - --migrations-dir (default: infra/bigquery)
 - --skip-git-fetch to disable git fetch origin main
 - --dry-run to list pending migrations without applying
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from google.cloud import bigquery


def run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_tracking_table(client: bigquery.Client, project: str, dataset: str, location: str) -> None:
    table_fq = f"`{project}.{dataset}.schema_migrations`"
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {table_fq} (
      version STRING NOT NULL,
      filename STRING NOT NULL,
      checksum STRING NOT NULL,
      applied_at TIMESTAMP NOT NULL
    )
    OPTIONS (
      description = "Tracks applied BigQuery migrations from GCP_LOGGING repo"
    );
    """
    client.query(ddl, location=location).result()


def load_applied(client: bigquery.Client, project: str, dataset: str, location: str) -> Dict[str, Tuple[str, str]]:
    table_fq = f"`{project}.{dataset}.schema_migrations`"
    rows = client.query(
        f"SELECT version, checksum, filename FROM {table_fq}",
        location=location,
    ).result()
    return {row.version: (row.checksum, row.filename) for row in rows}


def discover_migrations(migrations_dir: Path) -> List[Tuple[str, Path]]:
    files = sorted(migrations_dir.glob("*.sql"))
    migrations: List[Tuple[str, Path]] = []
    for f in files:
        stem = f.stem
        # Expect prefix like 03_my_change -> version="03"
        version = stem.split("_", 1)[0]
        migrations.append((version, f))
    return migrations


def apply_migration(
    client: bigquery.Client,
    project: str,
    dataset: str,
    location: str,
    version: str,
    filepath: Path,
    checksum: str,
) -> None:
    sql = filepath.read_text(encoding="utf-8")
    job = client.query(sql, location=location)
    job.result()  # wait
    insert_sql = f"""
    INSERT INTO `{project}.{dataset}.schema_migrations` (version, filename, checksum, applied_at)
    VALUES (@version, @filename, @checksum, @applied_at)
    """
    params = [
        bigquery.ScalarQueryParameter("version", "STRING", version),
        bigquery.ScalarQueryParameter("filename", "STRING", filepath.name),
        bigquery.ScalarQueryParameter("checksum", "STRING", checksum),
        bigquery.ScalarQueryParameter("applied_at", "TIMESTAMP", datetime.now(timezone.utc)),
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    client.query(insert_sql, job_config=job_config, location=location).result()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BigQuery migrations from infra/bigquery")
    parser.add_argument("--migrations-dir", default="infra/bigquery", help="Path to SQL migrations")
    parser.add_argument("--dataset", default=None, help="BigQuery dataset (default: env BQ_DATASET or central_logging_v1)")
    parser.add_argument("--location", default=None, help="BigQuery location (default: env BQ_LOCATION or US)")
    parser.add_argument("--skip-git-fetch", action="store_true", help="Skip git fetch origin main")
    parser.add_argument("--dry-run", action="store_true", help="List pending migrations without applying")
    args = parser.parse_args()

    migrations_dir = Path(args.migrations_dir)
    if not migrations_dir.exists():
        raise SystemExit(f"Migrations dir not found: {migrations_dir}")

    if not args.skip_git_fetch:
        run(["git", "fetch", "origin", "main"])

    client = bigquery.Client()
    project = (args.dataset or "").split(":")[0] if args.dataset and ":" in args.dataset else client.project
    dataset = args.dataset or "central_logging_v1"
    location = args.location or "US"

    ensure_tracking_table(client, project, dataset, location)
    applied = load_applied(client, project, dataset, location)
    migrations = discover_migrations(migrations_dir)

    pending: List[Tuple[str, Path, str]] = []
    for version, path in migrations:
        content = path.read_text(encoding="utf-8")
        checksum = sha256_text(content)
        if version in applied:
            prev_checksum, prev_file = applied[version]
            if prev_checksum != checksum:
                print(f"WARNING: checksum drift for version {version}: {path.name} vs applied {prev_file}")
            continue
        pending.append((version, path, checksum))

    if not pending:
        print("No new migrations to apply.")
        return

    print("Pending migrations:")
    for version, path, _ in pending:
        print(f"  {version}: {path.name}")

    if args.dry_run:
        return

    for version, path, checksum in pending:
        print(f"Applying migration {version} ({path.name})...")
        apply_migration(client, project, dataset, location, version, path, checksum)
        print(f"Applied {version}.")

    print("All pending migrations applied.")


if __name__ == "__main__":
    main()
