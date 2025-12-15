"""
Log Loader

Loads normalized and transformed logs into the master_logs table.
Handles batch insertions, deduplication, and cleanup.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from google.cloud import bigquery

from src.etl.normalizer import NormalizedLog

logger = logging.getLogger(__name__)


class LogLoader:
    """
    Loads logs into the master_logs BigQuery table.

    Features:
    - Batch insertion for efficiency
    - Deduplication by insert_id
    - ETL metadata tracking
    - Table schema management
    """

    MASTER_TABLE = "diatonic-ai-gcp.central_logging_v1.master_logs"
    ETL_JOBS_TABLE = "diatonic-ai-gcp.central_logging_v1.etl_jobs"

    def __init__(self, project_id: str = "diatonic-ai-gcp"):
        self.project_id = project_id
        self.client = bigquery.Client(project=project_id)
        self.etl_version = "1.0.0"
        self.stats = {
            "loaded": 0,
            "failed": 0,
            "duplicates": 0,
        }

    def ensure_tables(self):
        """Ensure master_logs and etl_jobs tables exist."""
        # Read and execute schema SQL
        try:
            from pathlib import Path
            schema_path = Path(__file__).parents[2] / "schemas" / "bigquery" / "master_logs.sql"

            if schema_path.exists():
                with open(schema_path) as f:
                    sql = f.read()

                # Split into individual statements
                statements = [s.strip() for s in sql.split(";") if s.strip()]

                for stmt in statements:
                    if stmt and not stmt.startswith("--"):
                        try:
                            self.client.query(stmt).result()
                        except Exception as e:
                            # Table may already exist
                            logger.debug(f"Schema statement skipped: {e}")

                logger.info("Ensured master_logs tables exist")
            else:
                logger.warning(f"Schema file not found: {schema_path}")

        except Exception as e:
            logger.error(f"Error ensuring tables: {e}")

    def load(self, logs: List[NormalizedLog], batch_id: Optional[str] = None) -> int:
        """
        Load logs into master_logs table.

        Args:
            logs: List of NormalizedLog objects
            batch_id: Optional batch ID for tracking

        Returns:
            Number of rows loaded
        """
        if not logs:
            return 0

        batch_id = batch_id or str(uuid.uuid4())

        try:
            # Convert to BigQuery rows
            rows = []
            for log in logs:
                row = self._to_bq_row(log, batch_id)
                if row:
                    rows.append(row)

            if not rows:
                return 0

            # Insert into BigQuery
            errors = self.client.insert_rows_json(
                self.MASTER_TABLE,
                rows,
                row_ids=[r.get("log_id") for r in rows]  # For deduplication
            )

            if errors:
                logger.error(f"Errors loading logs: {errors[:5]}")  # Show first 5
                self.stats["failed"] += len(errors)
                self.stats["loaded"] += len(rows) - len(errors)
                return len(rows) - len(errors)

            self.stats["loaded"] += len(rows)
            logger.info(f"Loaded {len(rows)} logs (batch: {batch_id})")
            return len(rows)

        except Exception as e:
            logger.error(f"Error loading logs: {e}")
            self.stats["failed"] += len(logs)
            return 0

    def load_batch(
        self,
        logs: List[NormalizedLog],
        stream_id: str,
        batch_size: int = 500
    ) -> int:
        """
        Load logs in batches with progress tracking.

        Args:
            logs: List of NormalizedLog objects
            stream_id: Source stream ID
            batch_size: Rows per batch

        Returns:
            Total rows loaded
        """
        total_loaded = 0
        batch_id = str(uuid.uuid4())

        # Start ETL job tracking
        job_id = self._start_job(stream_id, batch_id, len(logs))

        try:
            for i in range(0, len(logs), batch_size):
                batch = logs[i:i + batch_size]
                loaded = self.load(batch, batch_id)
                total_loaded += loaded

                # Log progress
                progress = min((i + batch_size) / len(logs) * 100, 100)
                logger.info(f"Load progress: {progress:.1f}% ({total_loaded}/{len(logs)})")

            # Complete job
            self._complete_job(job_id, total_loaded, len(logs) - total_loaded)
            return total_loaded

        except Exception as e:
            self._fail_job(job_id, str(e))
            raise

    def _to_bq_row(self, log: NormalizedLog, batch_id: str) -> Optional[Dict]:
        """Convert NormalizedLog to BigQuery row format."""
        try:
            # Get partition date
            partition_date = None
            if log.event_timestamp:
                partition_date = log.event_timestamp.strftime("%Y-%m-%d")

            return {
                "log_id": log.log_id,
                "insert_id": log.insert_id,
                "event_timestamp": log.event_timestamp.isoformat() if log.event_timestamp else None,
                "receive_timestamp": log.receive_timestamp.isoformat() if log.receive_timestamp else None,
                "etl_timestamp": datetime.utcnow().isoformat(),
                "severity": log.severity,
                "severity_level": log.severity_level,
                "log_type": log.log_type,
                "source_dataset": log.source_dataset,
                "source_table": log.source_table,
                "source_log_name": log.source_log_name,
                "stream_id": log.stream_id,
                "stream_direction": log.stream_direction,
                "stream_flow": log.stream_flow,
                "stream_coordinates": log.stream_coordinates,
                "resource_type": log.resource_type,
                "resource_project": log.resource_project,
                "resource_name": log.resource_name,
                "resource_location": log.resource_location,
                "resource_labels": json.dumps(log.resource_labels, default=str) if log.resource_labels else None,
                "service_name": log.service_name,
                "service_version": log.service_version,
                "service_method": log.service_method,
                "message": log.message[:10000] if log.message else None,
                "message_summary": log.message_summary,
                "message_category": log.message_category,
                "text_payload": log.text_payload[:10000] if log.text_payload else None,
                "json_payload": json.dumps(log.json_payload, default=str) if log.json_payload else None,
                "proto_payload": json.dumps(log.proto_payload, default=str) if log.proto_payload else None,
                "audit_payload": json.dumps(log.audit_payload, default=str) if log.audit_payload else None,
                "http_method": log.http_method,
                "http_url": log.http_url,
                "http_status": log.http_status,
                "http_latency_ms": log.http_latency_ms,
                "http_user_agent": log.http_user_agent,
                "http_remote_ip": log.http_remote_ip,
                "http_request_size": log.http_request_size,
                "http_response_size": log.http_response_size,
                "http_full": json.dumps(log.http_full, default=str) if log.http_full else None,
                "trace_id": log.trace_id,
                "span_id": log.span_id,
                "trace_sampled": log.trace_sampled,
                "parent_span_id": log.parent_span_id,
                "operation_id": log.operation_id,
                "operation_producer": log.operation_producer,
                "operation_first": log.operation_first,
                "operation_last": log.operation_last,
                "source_file": log.source_file,
                "source_line": log.source_line,
                "source_function": log.source_function,
                "labels": json.dumps(log.labels, default=str) if log.labels else None,
                "user_labels": json.dumps(log.user_labels, default=str) if log.user_labels else None,
                "system_labels": json.dumps(log.system_labels, default=str) if log.system_labels else None,
                "principal_email": log.principal_email,
                "principal_type": log.principal_type,
                "caller_ip": log.caller_ip,
                "caller_network": log.caller_network,
                "error_message": log.error_message,
                "error_code": log.error_code,
                "error_stack_trace": log.error_stack_trace[:5000] if log.error_stack_trace else None,
                "error_group_id": log.error_group_id,
                "is_error": log.is_error,
                "is_audit": log.is_audit,
                "is_request": log.is_request,
                "has_trace": log.has_trace,
                # Universal Envelope fields
                "schema_version": log.schema_version,
                "environment": log.environment,
                "correlation_request_id": log.correlation_request_id,
                "correlation_session_id": log.correlation_session_id,
                "correlation_conversation_id": log.correlation_conversation_id,
                "privacy_pii_risk": log.privacy_pii_risk,
                "privacy_redaction_state": log.privacy_redaction_state,
                "privacy_retention_class": log.privacy_retention_class,
                # ETL metadata
                "etl_version": self.etl_version,
                "etl_batch_id": batch_id,
                "etl_status": "SUCCESS",
                "etl_enrichments": ["normalized", "classified", "envelope"] if log.schema_version else ["normalized"],
                "log_date": partition_date,
                "cluster_key": f"{log.severity}:{log.service_name or 'unknown'}",
            }
        except Exception as e:
            logger.error(f"Error converting log to BQ row: {e}")
            return None

    def _start_job(self, stream_id: str, batch_id: str, total_records: int) -> str:
        """Start tracking an ETL job."""
        job_id = str(uuid.uuid4())

        try:
            self.client.insert_rows_json(
                self.ETL_JOBS_TABLE,
                [{
                    "job_id": job_id,
                    "job_type": "FULL_ETL",
                    "batch_id": batch_id,
                    "stream_id": stream_id,
                    "status": "RUNNING",
                    "started_at": datetime.utcnow().isoformat(),
                    "records_processed": 0,
                    "records_failed": 0,
                    "config": json.dumps({"total_records": total_records}),
                }]
            )
        except Exception as e:
            logger.warning(f"Could not track ETL job: {e}")

        return job_id

    def _complete_job(self, job_id: str, processed: int, failed: int):
        """Mark ETL job as complete."""
        try:
            query = f"""
            UPDATE `{self.ETL_JOBS_TABLE}`
            SET
                status = 'SUCCESS',
                completed_at = CURRENT_TIMESTAMP(),
                records_processed = {processed},
                records_failed = {failed}
            WHERE job_id = '{job_id}'
            """
            self.client.query(query).result()
        except Exception as e:
            logger.warning(f"Could not update ETL job: {e}")

    def _fail_job(self, job_id: str, error: str):
        """Mark ETL job as failed."""
        try:
            query = f"""
            UPDATE `{self.ETL_JOBS_TABLE}`
            SET
                status = 'FAILED',
                completed_at = CURRENT_TIMESTAMP(),
                error_message = '{error[:1000]}'
            WHERE job_id = '{job_id}'
            """
            self.client.query(query).result()
        except Exception as e:
            logger.warning(f"Could not update ETL job: {e}")

    def get_stats(self) -> Dict:
        """Get loader statistics."""
        return self.stats.copy()

    def cleanup_source_table(
        self,
        dataset: str,
        table: str,
        before_timestamp: datetime,
        dry_run: bool = True
    ) -> int:
        """
        Clean up source table after ETL (archive/delete old records).

        Args:
            dataset: Source dataset
            table: Source table
            before_timestamp: Delete records before this time
            dry_run: If True, only count records without deleting

        Returns:
            Number of records affected
        """
        table_ref = f"`{self.project_id}.{dataset}.{table}`"
        ts = before_timestamp.isoformat()

        if dry_run:
            query = f"""
            SELECT COUNT(*) as cnt
            FROM {table_ref}
            WHERE timestamp < '{ts}'
            """
            result = list(self.client.query(query).result())
            count = result[0].cnt if result else 0
            logger.info(f"Dry run: would delete {count} records from {dataset}.{table}")
            return count
        else:
            query = f"""
            DELETE FROM {table_ref}
            WHERE timestamp < '{ts}'
            """
            result = self.client.query(query).result()
            logger.info(f"Deleted records from {dataset}.{table}")
            return result.num_dml_affected_rows or 0
