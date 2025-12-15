"""
Log Extractor

Extracts logs from BigQuery source tables with stream tracking.
Handles different table schemas and payload types.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Generator

from google.cloud import bigquery

from src.etl.stream_manager import LogStream, StreamCoordinates

logger = logging.getLogger(__name__)


@dataclass
class RawLogRecord:
    """Raw log record extracted from BigQuery."""
    # Core fields
    log_id: str
    insert_id: Optional[str]
    timestamp: datetime
    receive_timestamp: Optional[datetime]
    severity: str
    log_name: Optional[str]

    # Source tracking
    source_dataset: str
    source_table: str
    stream_id: str
    stream_direction: str
    stream_flow: str
    stream_coordinates: StreamCoordinates

    # Resource
    resource_type: Optional[str] = None
    resource_labels: Dict[str, Any] = field(default_factory=dict)

    # Payloads (raw)
    text_payload: Optional[str] = None
    json_payload: Optional[Dict] = None
    proto_payload: Optional[Dict] = None
    audit_payload: Optional[Dict] = None

    # HTTP context
    http_request: Optional[Dict] = None

    # Trace context
    trace: Optional[str] = None
    span_id: Optional[str] = None
    trace_sampled: Optional[bool] = None

    # Operation
    operation: Optional[Dict] = None

    # Source location
    source_location: Optional[Dict] = None

    # Labels
    labels: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "log_id": self.log_id,
            "insert_id": self.insert_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "receive_timestamp": self.receive_timestamp.isoformat() if self.receive_timestamp else None,
            "severity": self.severity,
            "log_name": self.log_name,
            "source_dataset": self.source_dataset,
            "source_table": self.source_table,
            "stream_id": self.stream_id,
            "stream_direction": self.stream_direction,
            "stream_flow": self.stream_flow,
            "stream_coordinates": self.stream_coordinates.to_dict(),
            "resource_type": self.resource_type,
            "resource_labels": self.resource_labels,
            "text_payload": self.text_payload,
            "json_payload": self.json_payload,
            "proto_payload": self.proto_payload,
            "audit_payload": self.audit_payload,
            "http_request": self.http_request,
            "trace": self.trace,
            "span_id": self.span_id,
            "trace_sampled": self.trace_sampled,
            "operation": self.operation,
            "source_location": self.source_location,
            "labels": self.labels,
        }


class LogExtractor:
    """
    Extracts logs from BigQuery source tables.

    Handles:
    - Multiple table schemas
    - All payload types (text, JSON, proto)
    - Stream tracking metadata
    - Offset-based pagination for large tables
    """

    # Common fields across all log tables
    CORE_FIELDS = [
        "timestamp", "severity", "insertId", "logName",
        "receiveTimestamp", "trace", "spanId", "traceSampled"
    ]

    # Payload fields
    PAYLOAD_FIELDS = [
        "textPayload", "jsonPayload", "protoPayload",
        "protopayload_auditlog"  # Audit log specific
    ]

    # Context fields
    CONTEXT_FIELDS = [
        "resource", "httpRequest", "operation",
        "sourceLocation", "labels"
    ]

    def __init__(self, project_id: str = "diatonic-ai-gcp"):
        self.project_id = project_id
        self.client = bigquery.Client(project=project_id)

    def get_table_schema(self, dataset: str, table: str) -> Dict[str, str]:
        """Get the schema of a table as field name -> type mapping."""
        try:
            table_ref = self.client.get_table(f"{self.project_id}.{dataset}.{table}")
            return {f.name: f.field_type for f in table_ref.schema}
        except Exception as e:
            logger.error(f"Error getting schema for {dataset}.{table}: {e}")
            return {}

    def build_select_fields(self, schema: Dict[str, str]) -> List[str]:
        """Build list of SELECT fields based on available schema."""
        fields = []

        # Always include core fields if available
        for field in self.CORE_FIELDS:
            if field in schema:
                fields.append(field)

        # Include payload fields
        for field in self.PAYLOAD_FIELDS:
            if field in schema:
                fields.append(field)

        # Include context fields
        for field in self.CONTEXT_FIELDS:
            if field in schema:
                fields.append(field)

        return fields

    def extract_from_stream(
        self,
        stream: LogStream,
        offset: int = 0,
        limit: int = 1000,
        hours: Optional[int] = None
    ) -> Generator[RawLogRecord, None, None]:
        """
        Extract logs from a stream.

        Args:
            stream: LogStream to extract from
            offset: Starting offset
            limit: Maximum records to extract
            hours: Only extract logs from last N hours

        Yields:
            RawLogRecord objects
        """
        schema = self.get_table_schema(stream.source_dataset, stream.source_table)
        if not schema:
            logger.error(f"Could not get schema for stream {stream.stream_id}")
            return

        fields = self.build_select_fields(schema)
        if not fields:
            logger.error(f"No valid fields found for stream {stream.stream_id}")
            return

        # Build query
        table_ref = f"`{self.project_id}.{stream.source_dataset}.{stream.source_table}`"
        field_list = ", ".join(fields)

        query = f"SELECT {field_list} FROM {table_ref}"

        # Add time filter if specified
        if hours and "timestamp" in schema:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            query += f" WHERE timestamp >= '{cutoff.isoformat()}'"

        # Add ordering and pagination
        if "timestamp" in schema:
            query += " ORDER BY timestamp DESC"
        query += f" LIMIT {limit} OFFSET {offset}"

        logger.info(f"Extracting from {stream.stream_id}: offset={offset}, limit={limit}")

        try:
            results = self.client.query(query).result()
            count = 0

            for row in results:
                count += 1
                record = self._row_to_record(row, stream, schema)
                if record:
                    yield record

            logger.info(f"Extracted {count} records from {stream.stream_id}")

        except Exception as e:
            logger.error(f"Error extracting from {stream.stream_id}: {e}")

    def _row_to_record(
        self,
        row: bigquery.Row,
        stream: LogStream,
        schema: Dict[str, str]
    ) -> Optional[RawLogRecord]:
        """Convert a BigQuery row to a RawLogRecord."""
        try:
            # Extract resource info
            resource = dict(row.get("resource", {}) or {})
            resource_type = resource.get("type", "unknown")
            resource_labels = dict(resource.get("labels", {}) or {})

            # Extract payloads
            text_payload = row.get("textPayload")
            json_payload = self._to_dict(row.get("jsonPayload"))
            proto_payload = self._to_dict(row.get("protoPayload"))

            # Handle audit log specific payload
            audit_payload = None
            if "protopayload_auditlog" in schema:
                audit_payload = self._to_dict(row.get("protopayload_auditlog"))

            return RawLogRecord(
                log_id=str(uuid.uuid4()),
                insert_id=row.get("insertId"),
                timestamp=row.get("timestamp"),
                receive_timestamp=row.get("receiveTimestamp"),
                severity=row.get("severity", "DEFAULT"),
                log_name=row.get("logName"),
                source_dataset=stream.source_dataset,
                source_table=stream.source_table,
                stream_id=stream.stream_id,
                stream_direction=stream.direction.value,
                stream_flow=stream.flow.value,
                stream_coordinates=stream.coordinates,
                resource_type=resource_type,
                resource_labels=resource_labels,
                text_payload=text_payload,
                json_payload=json_payload,
                proto_payload=proto_payload,
                audit_payload=audit_payload,
                http_request=self._to_dict(row.get("httpRequest")),
                trace=row.get("trace"),
                span_id=row.get("spanId"),
                trace_sampled=row.get("traceSampled"),
                operation=self._to_dict(row.get("operation")),
                source_location=self._to_dict(row.get("sourceLocation")),
                labels=self._to_dict(row.get("labels")) or {},
            )

        except Exception as e:
            logger.error(f"Error converting row to record: {e}")
            return None

    def _to_dict(self, value: Any) -> Optional[Dict]:
        """Convert BigQuery struct/record to dict."""
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        try:
            return dict(value)
        except:
            return None

    def extract_batch(
        self,
        stream: LogStream,
        batch_size: int = 1000,
        max_batches: Optional[int] = None,
        start_offset: int = 0
    ) -> Generator[List[RawLogRecord], None, None]:
        """
        Extract logs in batches.

        Args:
            stream: LogStream to extract from
            batch_size: Records per batch
            max_batches: Maximum number of batches (None for unlimited)
            start_offset: Starting offset

        Yields:
            List of RawLogRecord objects per batch
        """
        offset = start_offset
        batch_count = 0

        while True:
            batch = list(self.extract_from_stream(stream, offset=offset, limit=batch_size))

            if not batch:
                break

            yield batch

            offset += len(batch)
            batch_count += 1

            if max_batches and batch_count >= max_batches:
                break

            if len(batch) < batch_size:
                # No more records
                break

        logger.info(f"Completed extraction: {batch_count} batches, {offset - start_offset} total records")

    def count_records(self, stream: LogStream, hours: Optional[int] = None) -> int:
        """Count records in a stream."""
        table_ref = f"`{self.project_id}.{stream.source_dataset}.{stream.source_table}`"
        query = f"SELECT COUNT(*) as cnt FROM {table_ref}"

        if hours:
            schema = self.get_table_schema(stream.source_dataset, stream.source_table)
            if "timestamp" in schema:
                cutoff = datetime.utcnow() - timedelta(hours=hours)
                query += f" WHERE timestamp >= '{cutoff.isoformat()}'"

        try:
            result = list(self.client.query(query).result())
            return result[0].cnt if result else 0
        except Exception as e:
            logger.error(f"Error counting records in {stream.stream_id}: {e}")
            return 0
