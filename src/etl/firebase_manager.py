"""
ETL Firebase Manager

Firebase/Firestore-based management for ETL pipeline.
Handles job tracking, stream configuration, and monitoring.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """ETL job status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class ETLJobRecord:
    """ETL job record for Firestore."""
    job_id: str
    job_type: str  # full, incremental, stream
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None

    # Configuration
    config: Dict = None
    stream_id: Optional[str] = None
    hours_lookback: Optional[int] = None
    enable_ai: bool = False
    batch_size: int = 1000

    # Metrics
    streams_processed: int = 0
    total_extracted: int = 0
    total_normalized: int = 0
    total_transformed: int = 0
    total_loaded: int = 0
    error_count: int = 0

    # Errors
    errors: List[str] = None

    # Trigger info
    trigger_source: str = "manual"  # manual, scheduler, pubsub
    trigger_id: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to Firestore document."""
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "ETLJobRecord":
        """Create from Firestore document."""
        if isinstance(data.get("started_at"), str):
            data["started_at"] = datetime.fromisoformat(data["started_at"])
        if isinstance(data.get("completed_at"), str):
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])
        return cls(**data)


@dataclass
class StreamConfig:
    """Stream configuration for Firestore."""
    stream_id: str
    source_dataset: str
    source_table: str
    direction: str  # INBOUND, OUTBOUND, INTERNAL
    flow: str  # REALTIME, BATCH, SCHEDULED

    # Processing settings
    enabled: bool = True
    priority: int = 1  # Higher = process first
    batch_size: int = 1000
    enable_ai: bool = False

    # Sync state
    last_sync_offset: int = 0
    last_sync_timestamp: Optional[datetime] = None
    total_records_synced: int = 0

    # Metadata
    created_at: datetime = None
    updated_at: datetime = None

    def to_dict(self) -> Dict:
        """Convert to Firestore document."""
        data = asdict(self)
        if self.last_sync_timestamp:
            data["last_sync_timestamp"] = self.last_sync_timestamp.isoformat()
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        return data


class ETLFirebaseManager:
    """
    Firebase-based ETL management service.

    Handles:
    - Job history and tracking
    - Stream configuration
    - Pipeline status monitoring
    - Alerts and notifications
    """

    JOBS_COLLECTION = "etl_jobs"
    STREAMS_COLLECTION = "etl_streams"
    METRICS_COLLECTION = "etl_metrics"
    ALERTS_COLLECTION = "etl_alerts"

    def __init__(self, project_id: str = "diatonic-ai-gcp"):
        self.project_id = project_id
        self.db = None
        self._init_firestore()

    def _init_firestore(self):
        """Initialize Firestore client."""
        try:
            import os
            from google.cloud import firestore

            # Check for emulator
            emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST")
            if emulator_host:
                logger.info(f"Using Firestore emulator at {emulator_host}")

            self.db = firestore.Client(project=self.project_id)
            logger.info("Firestore client initialized")

        except Exception as e:
            logger.warning(f"Could not initialize Firestore: {e}")
            self.db = None

    # ==================== Job Management ====================

    def create_job(
        self,
        job_id: str,
        job_type: str,
        config: Dict = None,
        trigger_source: str = "manual",
        trigger_id: str = None
    ) -> Optional[ETLJobRecord]:
        """Create a new ETL job record."""
        if not self.db:
            return None

        try:
            job = ETLJobRecord(
                job_id=job_id,
                job_type=job_type,
                status=JobStatus.RUNNING.value,
                started_at=datetime.utcnow(),
                config=config or {},
                hours_lookback=config.get("hours") if config else None,
                enable_ai=config.get("enable_ai", False) if config else False,
                batch_size=config.get("batch_size", 1000) if config else 1000,
                trigger_source=trigger_source,
                trigger_id=trigger_id,
                errors=[]
            )

            doc_ref = self.db.collection(self.JOBS_COLLECTION).document(job_id)
            doc_ref.set(job.to_dict())

            logger.info(f"Created ETL job record: {job_id}")
            return job

        except Exception as e:
            logger.error(f"Error creating job record: {e}")
            return None

    def update_job_progress(
        self,
        job_id: str,
        extracted: int = 0,
        normalized: int = 0,
        transformed: int = 0,
        loaded: int = 0,
        streams_processed: int = 0
    ):
        """Update job progress metrics."""
        if not self.db:
            return

        try:
            doc_ref = self.db.collection(self.JOBS_COLLECTION).document(job_id)
            doc_ref.update({
                "total_extracted": extracted,
                "total_normalized": normalized,
                "total_transformed": transformed,
                "total_loaded": loaded,
                "streams_processed": streams_processed,
            })
        except Exception as e:
            logger.warning(f"Error updating job progress: {e}")

    def complete_job(
        self,
        job_id: str,
        status: JobStatus,
        errors: List[str] = None,
        final_metrics: Dict = None
    ):
        """Mark job as complete."""
        if not self.db:
            return

        try:
            update_data = {
                "status": status.value,
                "completed_at": datetime.utcnow().isoformat(),
                "error_count": len(errors) if errors else 0,
            }

            if errors:
                update_data["errors"] = errors[:100]  # Limit stored errors

            if final_metrics:
                update_data.update(final_metrics)

            doc_ref = self.db.collection(self.JOBS_COLLECTION).document(job_id)
            doc_ref.update(update_data)

            logger.info(f"Completed ETL job: {job_id} with status {status.value}")

            # Check for alerts
            if status == JobStatus.FAILED:
                self._create_alert(
                    "job_failed",
                    f"ETL job {job_id} failed",
                    {"job_id": job_id, "errors": errors[:5] if errors else []}
                )

        except Exception as e:
            logger.error(f"Error completing job: {e}")

    def get_job(self, job_id: str) -> Optional[ETLJobRecord]:
        """Get job by ID."""
        if not self.db:
            return None

        try:
            doc = self.db.collection(self.JOBS_COLLECTION).document(job_id).get()
            if doc.exists:
                return ETLJobRecord.from_dict(doc.to_dict())
            return None
        except Exception as e:
            logger.error(f"Error getting job: {e}")
            return None

    def get_recent_jobs(
        self,
        limit: int = 20,
        status: Optional[JobStatus] = None
    ) -> List[ETLJobRecord]:
        """Get recent ETL jobs."""
        if not self.db:
            return []

        try:
            query = self.db.collection(self.JOBS_COLLECTION)\
                .order_by("started_at", direction="DESCENDING")\
                .limit(limit)

            if status:
                query = query.where("status", "==", status.value)

            jobs = []
            for doc in query.stream():
                try:
                    jobs.append(ETLJobRecord.from_dict(doc.to_dict()))
                except Exception:
                    pass

            return jobs

        except Exception as e:
            logger.error(f"Error getting recent jobs: {e}")
            return []

    def get_running_jobs(self) -> List[ETLJobRecord]:
        """Get currently running jobs."""
        return self.get_recent_jobs(limit=10, status=JobStatus.RUNNING)

    # ==================== Stream Management ====================

    def register_stream(self, stream: StreamConfig) -> bool:
        """Register or update a stream configuration."""
        if not self.db:
            return False

        try:
            stream.created_at = stream.created_at or datetime.utcnow()
            stream.updated_at = datetime.utcnow()

            doc_ref = self.db.collection(self.STREAMS_COLLECTION).document(stream.stream_id)
            doc_ref.set(stream.to_dict(), merge=True)

            logger.info(f"Registered stream: {stream.stream_id}")
            return True

        except Exception as e:
            logger.error(f"Error registering stream: {e}")
            return False

    def get_stream(self, stream_id: str) -> Optional[StreamConfig]:
        """Get stream configuration."""
        if not self.db:
            return None

        try:
            doc = self.db.collection(self.STREAMS_COLLECTION).document(stream_id).get()
            if doc.exists:
                data = doc.to_dict()
                return StreamConfig(**data)
            return None
        except Exception as e:
            logger.error(f"Error getting stream: {e}")
            return None

    def get_all_streams(self, enabled_only: bool = False) -> List[StreamConfig]:
        """Get all stream configurations."""
        if not self.db:
            return []

        try:
            query = self.db.collection(self.STREAMS_COLLECTION)

            if enabled_only:
                query = query.where("enabled", "==", True)

            streams = []
            for doc in query.stream():
                try:
                    data = doc.to_dict()
                    streams.append(StreamConfig(**data))
                except Exception:
                    pass

            # Sort by priority
            streams.sort(key=lambda s: s.priority, reverse=True)
            return streams

        except Exception as e:
            logger.error(f"Error getting streams: {e}")
            return []

    def update_stream_sync(
        self,
        stream_id: str,
        offset: int,
        records_synced: int
    ):
        """Update stream sync state."""
        if not self.db:
            return

        try:
            doc_ref = self.db.collection(self.STREAMS_COLLECTION).document(stream_id)
            doc_ref.update({
                "last_sync_offset": offset,
                "last_sync_timestamp": datetime.utcnow().isoformat(),
                "total_records_synced": firestore.Increment(records_synced),
                "updated_at": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.warning(f"Error updating stream sync: {e}")

    def enable_stream(self, stream_id: str, enabled: bool = True):
        """Enable or disable a stream."""
        if not self.db:
            return

        try:
            doc_ref = self.db.collection(self.STREAMS_COLLECTION).document(stream_id)
            doc_ref.update({
                "enabled": enabled,
                "updated_at": datetime.utcnow().isoformat(),
            })
            logger.info(f"Stream {stream_id} {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            logger.error(f"Error updating stream: {e}")

    # ==================== Metrics ====================

    def record_metrics(self, metrics: Dict):
        """Record ETL metrics snapshot."""
        if not self.db:
            return

        try:
            metrics["timestamp"] = datetime.utcnow().isoformat()
            self.db.collection(self.METRICS_COLLECTION).add(metrics)
        except Exception as e:
            logger.warning(f"Error recording metrics: {e}")

    def get_metrics_summary(self, hours: int = 24) -> Dict:
        """Get metrics summary for the past N hours."""
        if not self.db:
            return {}

        try:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

            # Get recent jobs
            jobs_query = self.db.collection(self.JOBS_COLLECTION)\
                .where("started_at", ">=", cutoff)\
                .stream()

            jobs = list(jobs_query)

            total_loaded = 0
            total_errors = 0
            job_count = len(jobs)
            completed_count = 0
            failed_count = 0

            for doc in jobs:
                data = doc.to_dict()
                total_loaded += data.get("total_loaded", 0)
                total_errors += data.get("error_count", 0)
                if data.get("status") == JobStatus.COMPLETED.value:
                    completed_count += 1
                elif data.get("status") == JobStatus.FAILED.value:
                    failed_count += 1

            return {
                "period_hours": hours,
                "total_jobs": job_count,
                "completed_jobs": completed_count,
                "failed_jobs": failed_count,
                "total_logs_loaded": total_loaded,
                "total_errors": total_errors,
                "success_rate": (completed_count / job_count * 100) if job_count > 0 else 0,
            }

        except Exception as e:
            logger.error(f"Error getting metrics summary: {e}")
            return {}

    # ==================== Alerts ====================

    def _create_alert(self, alert_type: str, message: str, details: Dict = None):
        """Create an alert."""
        if not self.db:
            return

        try:
            alert = {
                "type": alert_type,
                "message": message,
                "details": details or {},
                "created_at": datetime.utcnow().isoformat(),
                "acknowledged": False,
            }
            self.db.collection(self.ALERTS_COLLECTION).add(alert)
            logger.warning(f"Alert created: {alert_type} - {message}")
        except Exception as e:
            logger.warning(f"Error creating alert: {e}")

    def get_unacknowledged_alerts(self, limit: int = 20) -> List[Dict]:
        """Get unacknowledged alerts."""
        if not self.db:
            return []

        try:
            query = self.db.collection(self.ALERTS_COLLECTION)\
                .where("acknowledged", "==", False)\
                .order_by("created_at", direction="DESCENDING")\
                .limit(limit)

            return [doc.to_dict() | {"id": doc.id} for doc in query.stream()]

        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            return []

    def acknowledge_alert(self, alert_id: str):
        """Acknowledge an alert."""
        if not self.db:
            return

        try:
            doc_ref = self.db.collection(self.ALERTS_COLLECTION).document(alert_id)
            doc_ref.update({
                "acknowledged": True,
                "acknowledged_at": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.error(f"Error acknowledging alert: {e}")

    # ==================== Dashboard Data ====================

    def get_dashboard_data(self) -> Dict:
        """Get data for ETL dashboard."""
        return {
            "running_jobs": [j.to_dict() for j in self.get_running_jobs()],
            "recent_jobs": [j.to_dict() for j in self.get_recent_jobs(limit=10)],
            "streams": [s.to_dict() for s in self.get_all_streams()],
            "metrics_24h": self.get_metrics_summary(24),
            "metrics_7d": self.get_metrics_summary(168),
            "alerts": self.get_unacknowledged_alerts(10),
        }


# Firestore increment sentinel
try:
    from google.cloud import firestore
except ImportError:
    class firestore:
        @staticmethod
        def Increment(value):
            return value
