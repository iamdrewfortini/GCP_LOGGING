"""
ETL API Routes

REST API endpoints for ETL pipeline monitoring and management.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

from src.etl.firebase_manager import ETLFirebaseManager, JobStatus
from src.etl.pipeline import ETLPipeline, PipelineConfig
from src.etl.stream_manager import StreamManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/etl", tags=["ETL"])

# Initialize services
PROJECT_ID = "diatonic-ai-gcp"


# ==================== Pydantic Models ====================

class ETLJobRequest(BaseModel):
    """Request to trigger ETL job."""
    job_type: str = "incremental"  # full, incremental, stream
    hours: Optional[int] = 24
    stream_id: Optional[str] = None
    enable_ai: bool = False
    batch_size: int = 1000


class ETLJobResponse(BaseModel):
    """ETL job response."""
    job_id: str
    status: str
    job_type: str
    started_at: str
    completed_at: Optional[str] = None
    streams_processed: int = 0
    total_extracted: int = 0
    total_loaded: int = 0
    error_count: int = 0


class StreamResponse(BaseModel):
    """Stream configuration response."""
    stream_id: str
    source_dataset: str
    source_table: str
    direction: str
    flow: str
    enabled: bool
    priority: int
    last_sync_offset: int
    total_records_synced: int


class ETLDashboardResponse(BaseModel):
    """ETL dashboard data."""
    running_jobs: List[dict]
    recent_jobs: List[dict]
    streams: List[dict]
    metrics_24h: dict
    alerts: List[dict]


# ==================== Job Endpoints ====================

@router.get("/jobs", response_model=List[ETLJobResponse])
async def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(20, le=100)
):
    """List ETL jobs with optional status filter."""
    try:
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)

        job_status = None
        if status:
            try:
                job_status = JobStatus(status.upper())
            except ValueError:
                raise HTTPException(400, f"Invalid status: {status}")

        jobs = firebase_mgr.get_recent_jobs(limit=limit, status=job_status)

        return [
            ETLJobResponse(
                job_id=j.job_id,
                status=j.status,
                job_type=j.job_type,
                started_at=j.started_at.isoformat(),
                completed_at=j.completed_at.isoformat() if j.completed_at else None,
                streams_processed=j.streams_processed,
                total_extracted=j.total_extracted,
                total_loaded=j.total_loaded,
                error_count=j.error_count,
            )
            for j in jobs
        ]

    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(500, str(e))


@router.get("/jobs/{job_id}", response_model=ETLJobResponse)
async def get_job(job_id: str):
    """Get ETL job details."""
    try:
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)
        job = firebase_mgr.get_job(job_id)

        if not job:
            raise HTTPException(404, f"Job not found: {job_id}")

        return ETLJobResponse(
            job_id=job.job_id,
            status=job.status,
            job_type=job.job_type,
            started_at=job.started_at.isoformat(),
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            streams_processed=job.streams_processed,
            total_extracted=job.total_extracted,
            total_loaded=job.total_loaded,
            error_count=job.error_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job: {e}")
        raise HTTPException(500, str(e))


@router.post("/jobs", response_model=ETLJobResponse)
async def trigger_job(request: ETLJobRequest, background_tasks: BackgroundTasks):
    """Trigger a new ETL job."""
    try:
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)

        # Create job record
        job_id = f"manual_{datetime.utcnow().timestamp()}"
        job_record = firebase_mgr.create_job(
            job_id=job_id,
            job_type=request.job_type,
            config={
                "hours": request.hours,
                "stream_id": request.stream_id,
                "enable_ai": request.enable_ai,
                "batch_size": request.batch_size,
            },
            trigger_source="api"
        )

        # Run job in background
        background_tasks.add_task(
            _run_etl_job,
            job_id=job_id,
            job_type=request.job_type,
            hours=request.hours,
            stream_id=request.stream_id,
            enable_ai=request.enable_ai,
            batch_size=request.batch_size
        )

        return ETLJobResponse(
            job_id=job_id,
            status="RUNNING",
            job_type=request.job_type,
            started_at=datetime.utcnow().isoformat(),
            streams_processed=0,
            total_extracted=0,
            total_loaded=0,
            error_count=0,
        )

    except Exception as e:
        logger.error(f"Error triggering job: {e}")
        raise HTTPException(500, str(e))


async def _run_etl_job(
    job_id: str,
    job_type: str,
    hours: int,
    stream_id: str,
    enable_ai: bool,
    batch_size: int
):
    """Background task to run ETL job."""
    firebase_mgr = ETLFirebaseManager(PROJECT_ID)

    try:
        config = PipelineConfig(
            project_id=PROJECT_ID,
            enable_ai_enrichment=enable_ai,
            batch_size=batch_size,
            hours_lookback=hours if job_type == "incremental" else None,
        )

        pipeline = ETLPipeline(config)

        if job_type == "stream" and stream_id:
            result = pipeline.run_single_stream(stream_id)
        elif job_type == "incremental":
            result = pipeline.run_incremental(hours=hours)
        else:
            result = pipeline.run()

        # Update job status
        status = JobStatus.COMPLETED if result.status == "COMPLETED" else \
                 JobStatus.PARTIAL if result.status == "PARTIAL" else JobStatus.FAILED

        firebase_mgr.complete_job(
            job_id=job_id,
            status=status,
            errors=result.errors,
            final_metrics={
                "streams_processed": result.streams_processed,
                "total_extracted": result.total_extracted,
                "total_normalized": result.total_normalized,
                "total_transformed": result.total_transformed,
                "total_loaded": result.total_loaded,
            }
        )

    except Exception as e:
        logger.error(f"ETL job {job_id} failed: {e}")
        firebase_mgr.complete_job(
            job_id=job_id,
            status=JobStatus.FAILED,
            errors=[str(e)]
        )


# ==================== Stream Endpoints ====================

@router.get("/streams", response_model=List[StreamResponse])
async def list_streams(enabled_only: bool = False):
    """List all ETL streams."""
    try:
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)
        streams = firebase_mgr.get_all_streams(enabled_only=enabled_only)

        return [
            StreamResponse(
                stream_id=s.stream_id,
                source_dataset=s.source_dataset,
                source_table=s.source_table,
                direction=s.direction,
                flow=s.flow,
                enabled=s.enabled,
                priority=s.priority,
                last_sync_offset=s.last_sync_offset,
                total_records_synced=s.total_records_synced,
            )
            for s in streams
        ]

    except Exception as e:
        logger.error(f"Error listing streams: {e}")
        raise HTTPException(500, str(e))


@router.post("/streams/discover")
async def discover_streams():
    """Discover new log streams from BigQuery."""
    try:
        stream_manager = StreamManager(PROJECT_ID)
        streams = stream_manager.discover_streams()

        # Register discovered streams
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)
        for stream in streams:
            from src.etl.firebase_manager import StreamConfig
            firebase_mgr.register_stream(StreamConfig(
                stream_id=stream.stream_id,
                source_dataset=stream.source_dataset,
                source_table=stream.source_table,
                direction=stream.direction.value,
                flow=stream.flow.value,
            ))

        return {
            "discovered": len(streams),
            "streams": [
                {
                    "stream_id": s.stream_id,
                    "direction": s.direction.value,
                    "flow": s.flow.value,
                    "row_count": s.config.get("row_count", 0),
                }
                for s in streams
            ]
        }

    except Exception as e:
        logger.error(f"Error discovering streams: {e}")
        raise HTTPException(500, str(e))


@router.put("/streams/{stream_id}/enable")
async def enable_stream(stream_id: str, enabled: bool = True):
    """Enable or disable a stream."""
    try:
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)
        firebase_mgr.enable_stream(stream_id, enabled)
        return {"stream_id": stream_id, "enabled": enabled}
    except Exception as e:
        logger.error(f"Error updating stream: {e}")
        raise HTTPException(500, str(e))


# ==================== Metrics & Dashboard ====================

@router.get("/metrics")
async def get_metrics(hours: int = Query(24, le=168)):
    """Get ETL metrics for the specified period."""
    try:
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)
        return firebase_mgr.get_metrics_summary(hours=hours)
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(500, str(e))


@router.get("/dashboard", response_model=ETLDashboardResponse)
async def get_dashboard():
    """Get ETL dashboard data."""
    try:
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)
        data = firebase_mgr.get_dashboard_data()
        return ETLDashboardResponse(**data)
    except Exception as e:
        logger.error(f"Error getting dashboard: {e}")
        raise HTTPException(500, str(e))


# ==================== Alerts ====================

@router.get("/alerts")
async def get_alerts(limit: int = Query(20, le=100)):
    """Get unacknowledged ETL alerts."""
    try:
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)
        return firebase_mgr.get_unacknowledged_alerts(limit=limit)
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(500, str(e))


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an ETL alert."""
    try:
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)
        firebase_mgr.acknowledge_alert(alert_id)
        return {"alert_id": alert_id, "acknowledged": True}
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(500, str(e))


# ==================== Health ====================

@router.get("/health")
async def etl_health():
    """Check ETL system health."""
    try:
        firebase_mgr = ETLFirebaseManager(PROJECT_ID)
        stream_manager = StreamManager(PROJECT_ID)

        # Check Firebase connection
        firebase_ok = firebase_mgr.db is not None

        # Check running jobs
        running_jobs = firebase_mgr.get_running_jobs()

        # Get stream count
        streams = stream_manager.get_all_streams()

        return {
            "status": "healthy" if firebase_ok else "degraded",
            "firebase_connected": firebase_ok,
            "running_jobs": len(running_jobs),
            "total_streams": len(streams),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
