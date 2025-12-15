import sys
import os
import logging
import argparse
from typing import Dict, Any, Generator
from google.cloud import bigquery

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.glass_pane.config import glass_config
from src.services.redis_service import redis_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bq_log_backfill")

QUEUE_NAME = "q:embeddings:logs"

def fetch_logs_from_bq(hours: int, limit: int) -> Generator[Dict[str, Any], None, None]:
    """
    Generates log entries from BigQuery.
    """
    client = bigquery.Client(project=glass_config.logs_project_id)
    
    # Construct Query
    # We assume the canonical view has standard fields: timestamp, severity, service, message/json_payload
    # Adjust fields based on actual schema if needed.
    query = f"""
        SELECT
            timestamp,
            severity,
            resource.type as resource_type,
            resource.labels.service_name as service_name,
            textPayload,
            jsonPayload,
            protoPayload,
            logName,
            insertId
        FROM `{glass_config.full_view}`
        WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
        ORDER BY timestamp ASC
        LIMIT @limit
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("hours", "INT64", hours),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
    )

    logger.info(f"Executing query against {glass_config.full_view}...")
    try:
        query_job = client.query(query, job_config=job_config)
        
        for row in query_job:
            # Normalize content
            content = row.get("textPayload")
            if not content and row.get("jsonPayload"):
                content = str(row.get("jsonPayload"))
            if not content and row.get("protoPayload"):
                content = str(row.get("protoPayload"))
            
            if not content:
                continue

            service = row.get("service_name") or "unknown-service"
            
            yield {
                "type": "log_entry",
                "project_id": glass_config.logs_project_id,
                "service": service,
                "severity": row.get("severity", "DEFAULT"),
                "timestamp": row["timestamp"].isoformat() if row.get("timestamp") else None,
                "content": content,
                "log_id": row.get("insertId")
            }
            
    except Exception as e:
        logger.error(f"BigQuery Query Failed: {e}")

def run_backfill(hours: int, limit: int, dry_run: bool = False):
    count = 0
    logger.info(f"Starting backfill for last {hours} hours (Limit: {limit})")
    
    for log_entry in fetch_logs_from_bq(hours, limit):
        if dry_run:
            logger.info(f"[Dry Run] Would enqueue: {log_entry['timestamp']} - {log_entry['service']}")
        else:
            redis_service.enqueue(QUEUE_NAME, log_entry)
        
        count += 1
        if count % 100 == 0:
            logger.info(f"Enqueued {count} logs...")

    logger.info(f"Backfill complete. Total logs enqueued: {count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill logs from BigQuery to Qdrant via Redis.")
    parser.add_argument("--hours", type=int, default=24, help="Hours of logs to fetch.")
    parser.add_argument("--limit", type=int, default=1000, help="Max logs to fetch.")
    parser.add_argument("--dry-run", action="store_true", help="Print logs instead of enqueueing.")
    
    args = parser.parse_args()
    
    from dotenv import load_dotenv
    load_dotenv()
    
    # Ensure Redis connection
    if not args.dry_run:
        if not redis_service.ping():
            logger.error("Could not connect to Redis. Exiting.")
            sys.exit(1)

    run_backfill(args.hours, args.limit, args.dry_run)