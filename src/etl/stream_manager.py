"""
Stream Manager

Manages data stream tracking, coordinates, and source labeling.
Each log source is treated as a data stream with direction, flow, and coordinates.
"""

import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

from google.cloud import bigquery

logger = logging.getLogger(__name__)


class StreamDirection(Enum):
    """Direction of data flow."""
    INBOUND = "INBOUND"      # External data coming into GCP
    OUTBOUND = "OUTBOUND"    # Data going to external systems
    INTERNAL = "INTERNAL"    # Internal GCP service logs


class StreamFlow(Enum):
    """Type of data flow."""
    REALTIME = "REALTIME"    # Streaming/real-time ingestion
    BATCH = "BATCH"          # Batch processing
    SCHEDULED = "SCHEDULED"  # Scheduled ETL jobs


@dataclass
class StreamCoordinates:
    """Geographic and organizational coordinates for a stream."""
    region: str = "us-central1"
    zone: Optional[str] = None
    project: str = "diatonic-ai-gcp"
    organization: str = "93534264368"

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class LogStream:
    """Represents a data stream from a log source."""
    stream_id: str
    stream_name: str
    source_dataset: str
    source_table: str
    direction: StreamDirection = StreamDirection.INTERNAL
    flow: StreamFlow = StreamFlow.BATCH
    coordinates: StreamCoordinates = field(default_factory=StreamCoordinates)
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    last_sync_offset: int = 0
    total_records_synced: int = 0
    config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_table(cls, dataset: str, table: str, project: str = "diatonic-ai-gcp") -> "LogStream":
        """Create a stream from a BigQuery table."""
        stream_id = f"{dataset}.{table}"
        stream_name = table.replace("_googleapis_com_", ":").replace("_", "-")

        # Determine direction based on log type
        direction = StreamDirection.INTERNAL
        if "audit" in table.lower():
            direction = StreamDirection.INTERNAL
        elif "request" in table.lower():
            direction = StreamDirection.INBOUND
        elif "sink_error" in table.lower():
            direction = StreamDirection.OUTBOUND

        # Determine flow based on table pattern
        flow = StreamFlow.BATCH
        if "stdout" in table.lower() or "stderr" in table.lower():
            flow = StreamFlow.REALTIME

        return cls(
            stream_id=stream_id,
            stream_name=stream_name,
            source_dataset=dataset,
            source_table=table,
            direction=direction,
            flow=flow,
            coordinates=StreamCoordinates(project=project)
        )

    def to_dict(self) -> Dict:
        return {
            "stream_id": self.stream_id,
            "stream_name": self.stream_name,
            "source_dataset": self.source_dataset,
            "source_table": self.source_table,
            "direction": self.direction.value,
            "flow": self.flow.value,
            "coordinates": self.coordinates.to_dict(),
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_offset": self.last_sync_offset,
            "total_records_synced": self.total_records_synced,
            "config": self.config
        }


class StreamManager:
    """
    Manages log data streams - tracking sources, coordinates, and sync state.
    """

    def __init__(self, project_id: str = "diatonic-ai-gcp"):
        self.project_id = project_id
        self.client = bigquery.Client(project=project_id)
        self.streams: Dict[str, LogStream] = {}
        self._init_streams_table()

    def _init_streams_table(self):
        """Ensure the log_streams table exists."""
        query = """
        CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.central_logging_v1.log_streams` (
            stream_id STRING NOT NULL,
            stream_name STRING NOT NULL,
            source_dataset STRING NOT NULL,
            source_table STRING NOT NULL,
            stream_direction STRING,
            stream_flow STRING,
            coordinates JSON,
            is_active BOOL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
            updated_at TIMESTAMP,
            last_sync_at TIMESTAMP,
            last_sync_offset INT64 DEFAULT 0,
            total_records_synced INT64 DEFAULT 0,
            config JSON
        )
        """
        try:
            self.client.query(query).result()
            logger.info("Ensured log_streams table exists")
        except Exception as e:
            logger.warning(f"Could not create log_streams table: {e}")

    def discover_streams(self, datasets: Optional[List[str]] = None) -> List[LogStream]:
        """
        Discover all log streams from BigQuery tables.

        Args:
            datasets: List of datasets to scan (defaults to logging datasets)

        Returns:
            List of discovered LogStream objects
        """
        target_datasets = datasets or ["central_logging_v1", "org_logs"]
        discovered = []

        for dataset_id in target_datasets:
            try:
                dataset_ref = self.client.dataset(dataset_id)
                for table in self.client.list_tables(dataset_ref):
                    table_obj = self.client.get_table(f"{dataset_id}.{table.table_id}")

                    # Skip empty tables and views
                    if table_obj.num_rows == 0 or table_obj.table_type == "VIEW":
                        continue

                    # Check for log-like schema
                    schema_fields = {f.name for f in table_obj.schema}
                    if not any(f in schema_fields for f in ['timestamp', 'severity', 'logName']):
                        continue

                    # Create stream
                    stream = LogStream.from_table(
                        dataset=dataset_id,
                        table=table.table_id,
                        project=self.project_id
                    )
                    stream.config["row_count"] = table_obj.num_rows
                    stream.config["schema_fields"] = list(schema_fields)

                    discovered.append(stream)
                    self.streams[stream.stream_id] = stream

                    logger.info(f"Discovered stream: {stream.stream_id} "
                               f"({stream.direction.value}, {stream.flow.value})")

            except Exception as e:
                logger.error(f"Error scanning dataset {dataset_id}: {e}")

        return discovered

    def register_stream(self, stream: LogStream) -> bool:
        """
        Register a stream in the database.

        Args:
            stream: LogStream to register

        Returns:
            True if successful
        """
        try:
            import json
            coords = stream.coordinates
            query = f"""
            MERGE INTO `diatonic-ai-gcp.central_logging_v1.log_streams` AS target
            USING (SELECT @stream_id AS stream_id) AS source
            ON target.stream_id = source.stream_id
            WHEN MATCHED THEN
                UPDATE SET
                    stream_name = @stream_name,
                    stream_direction = @direction,
                    stream_flow = @flow,
                    stream_coordinates = STRUCT(
                        '{coords.region or ""}' AS region,
                        '{coords.zone or ""}' AS zone,
                        '{coords.project or ""}' AS project,
                        '{coords.organization or ""}' AS organization
                    ),
                    updated_at = CURRENT_TIMESTAMP(),
                    config = PARSE_JSON(@config)
            WHEN NOT MATCHED THEN
                INSERT (stream_id, stream_name, source_dataset, source_table,
                        stream_direction, stream_flow, stream_coordinates, config)
                VALUES (@stream_id, @stream_name, @source_dataset, @source_table,
                        @direction, @flow,
                        STRUCT(
                            '{coords.region or ""}' AS region,
                            '{coords.zone or ""}' AS zone,
                            '{coords.project or ""}' AS project,
                            '{coords.organization or ""}' AS organization
                        ),
                        PARSE_JSON(@config))
            """

            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("stream_id", "STRING", stream.stream_id),
                    bigquery.ScalarQueryParameter("stream_name", "STRING", stream.stream_name),
                    bigquery.ScalarQueryParameter("source_dataset", "STRING", stream.source_dataset),
                    bigquery.ScalarQueryParameter("source_table", "STRING", stream.source_table),
                    bigquery.ScalarQueryParameter("direction", "STRING", stream.direction.value),
                    bigquery.ScalarQueryParameter("flow", "STRING", stream.flow.value),
                    bigquery.ScalarQueryParameter("config", "STRING", json.dumps(stream.config)),
                ]
            )

            self.client.query(query, job_config=job_config).result()
            self.streams[stream.stream_id] = stream
            logger.info(f"Registered stream: {stream.stream_id}")
            return True

        except Exception as e:
            logger.error(f"Error registering stream {stream.stream_id}: {e}")
            return False

    def update_sync_state(self, stream_id: str, offset: int, records_synced: int) -> bool:
        """
        Update the sync state for a stream.

        Args:
            stream_id: Stream identifier
            offset: Current sync offset
            records_synced: Number of records synced in this batch

        Returns:
            True if successful
        """
        try:
            query = """
            UPDATE `diatonic-ai-gcp.central_logging_v1.log_streams`
            SET
                last_sync_at = CURRENT_TIMESTAMP(),
                last_sync_offset = @offset,
                total_records_synced = total_records_synced + @records_synced,
                updated_at = CURRENT_TIMESTAMP()
            WHERE stream_id = @stream_id
            """

            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("stream_id", "STRING", stream_id),
                    bigquery.ScalarQueryParameter("offset", "INT64", offset),
                    bigquery.ScalarQueryParameter("records_synced", "INT64", records_synced),
                ]
            )

            self.client.query(query, job_config=job_config).result()

            # Update in-memory state
            if stream_id in self.streams:
                self.streams[stream_id].last_sync_at = datetime.utcnow()
                self.streams[stream_id].last_sync_offset = offset
                self.streams[stream_id].total_records_synced += records_synced

            return True

        except Exception as e:
            logger.error(f"Error updating sync state for {stream_id}: {e}")
            return False

    def get_stream(self, stream_id: str) -> Optional[LogStream]:
        """Get a stream by ID."""
        if stream_id in self.streams:
            return self.streams[stream_id]

        # Try to load from database
        try:
            query = f"""
            SELECT * FROM `diatonic-ai-gcp.central_logging_v1.log_streams`
            WHERE stream_id = '{stream_id}'
            """
            result = list(self.client.query(query).result())
            if result:
                row = result[0]
                import json
                stream = LogStream(
                    stream_id=row.stream_id,
                    stream_name=row.stream_name,
                    source_dataset=row.source_dataset,
                    source_table=row.source_table,
                    direction=StreamDirection(row.stream_direction) if row.stream_direction else StreamDirection.INTERNAL,
                    flow=StreamFlow(row.stream_flow) if row.stream_flow else StreamFlow.BATCH,
                    last_sync_offset=row.last_sync_offset or 0,
                    total_records_synced=row.total_records_synced or 0,
                )
                self.streams[stream_id] = stream
                return stream
        except Exception as e:
            logger.error(f"Error loading stream {stream_id}: {e}")

        return None

    def get_all_streams(self) -> List[LogStream]:
        """Get all registered streams."""
        try:
            query = """
            SELECT * FROM `diatonic-ai-gcp.central_logging_v1.log_streams`
            WHERE is_active = TRUE
            """
            results = list(self.client.query(query).result())

            streams = []
            for row in results:
                import json
                coords_data = json.loads(row.coordinates) if row.coordinates else {}
                stream = LogStream(
                    stream_id=row.stream_id,
                    stream_name=row.stream_name,
                    source_dataset=row.source_dataset,
                    source_table=row.source_table,
                    direction=StreamDirection(row.stream_direction) if row.stream_direction else StreamDirection.INTERNAL,
                    flow=StreamFlow(row.stream_flow) if row.stream_flow else StreamFlow.BATCH,
                    coordinates=StreamCoordinates(**coords_data) if coords_data else StreamCoordinates(),
                    is_active=row.is_active,
                    last_sync_at=row.last_sync_at,
                    last_sync_offset=row.last_sync_offset or 0,
                    total_records_synced=row.total_records_synced or 0,
                )
                streams.append(stream)
                self.streams[stream.stream_id] = stream

            return streams

        except Exception as e:
            logger.error(f"Error loading streams: {e}")
            return list(self.streams.values())

    def get_pending_streams(self) -> List[LogStream]:
        """Get streams that need syncing (have new data)."""
        pending = []
        for stream in self.get_all_streams():
            row_count = stream.config.get("row_count", 0)
            if stream.last_sync_offset < row_count:
                pending.append(stream)
        return pending
