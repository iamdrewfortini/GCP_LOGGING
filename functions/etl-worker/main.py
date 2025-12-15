"""
ETL Worker Cloud Function

Processes log ETL jobs triggered by Cloud Scheduler or Pub/Sub.
Normalizes logs from source tables into the master_logs table.
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import functions_framework
from google.cloud import pubsub_v1

# Add project root to path
FUNCTION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FUNCTION_DIR.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.etl.pipeline import ETLPipeline, PipelineConfig, PipelineResult
from src.etl.stream_manager import StreamManager
from src.etl.firebase_manager import ETLFirebaseManager, JobStatus

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
PROJECT_ID = os.getenv("PROJECT_ID", "diatonic-ai-gcp")
ENABLE_AI = os.getenv("ENABLE_AI_ENRICHMENT", "false").lower() == "true"
BATCH_SIZE = int(os.getenv("ETL_BATCH_SIZE", "1000"))
RESULTS_TOPIC = os.getenv("ETL_RESULTS_TOPIC", "etl-results")


@functions_framework.cloud_event
def process_etl_job(cloud_event):
    """
    Cloud Function entry point for ETL jobs.

    Triggered by Pub/Sub message with job configuration.

    Message format:
    {
        "job_type": "full" | "incremental" | "stream",
        "hours": 24,  # For incremental
        "stream_id": "dataset.table",  # For stream-specific
        "enable_ai": false,
        "batch_size": 1000
    }
    """
    logger.info(f"Received ETL job event: {cloud_event}")

    # Initialize Firebase manager for job tracking
    firebase_mgr = ETLFirebaseManager(PROJECT_ID)

    try:
        # Parse message
        message_data = cloud_event.data.get("message", {}).get("data", "")
        if message_data:
            import base64
            config_json = base64.b64decode(message_data).decode("utf-8")
            job_config = json.loads(config_json)
        else:
            job_config = {}

        # Extract job parameters
        job_type = job_config.get("job_type", "incremental")
        hours = job_config.get("hours", 24)
        stream_id = job_config.get("stream_id")
        enable_ai = job_config.get("enable_ai", ENABLE_AI)
        batch_size = job_config.get("batch_size", BATCH_SIZE)

        logger.info(f"ETL job config: type={job_type}, hours={hours}, ai={enable_ai}")

        # Configure pipeline
        config = PipelineConfig(
            project_id=PROJECT_ID,
            enable_ai_enrichment=enable_ai,
            batch_size=batch_size,
            hours_lookback=hours if job_type == "incremental" else None,
        )

        pipeline = ETLPipeline(config)

        # Create job record in Firebase
        job_record = firebase_mgr.create_job(
            job_id=pipeline.config.project_id + "_" + str(datetime.utcnow().timestamp()),
            job_type=job_type,
            config=job_config,
            trigger_source="pubsub",
            trigger_id=cloud_event.get("id", "unknown")
        )

        # Run appropriate job type
        if job_type == "stream" and stream_id:
            result = pipeline.run_single_stream(stream_id)
        elif job_type == "incremental":
            result = pipeline.run_incremental(hours=hours)
        else:
            result = pipeline.run()

        # Update Firebase with results
        if job_record:
            status = JobStatus.COMPLETED if result.status == "COMPLETED" else \
                     JobStatus.PARTIAL if result.status == "PARTIAL" else JobStatus.FAILED
            firebase_mgr.complete_job(
                job_id=job_record.job_id,
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

        # Publish result to Pub/Sub
        _publish_result(result)

        logger.info(f"ETL job completed: {result.status}, loaded={result.total_loaded}")
        return {"status": result.status, "loaded": result.total_loaded}

    except Exception as e:
        logger.error(f"ETL job failed: {e}")
        raise


@functions_framework.http
def etl_http_handler(request):
    """
    HTTP entry point for manual ETL triggers.

    Query parameters:
    - job_type: full | incremental | stream
    - hours: hours lookback for incremental
    - stream_id: specific stream to process
    - enable_ai: true/false
    """
    logger.info(f"HTTP ETL request: {request.args}")

    try:
        # Parse parameters
        job_type = request.args.get("job_type", "incremental")
        hours = int(request.args.get("hours", 24))
        stream_id = request.args.get("stream_id")
        enable_ai = request.args.get("enable_ai", "false").lower() == "true"
        batch_size = int(request.args.get("batch_size", BATCH_SIZE))

        # Configure pipeline
        config = PipelineConfig(
            project_id=PROJECT_ID,
            enable_ai_enrichment=enable_ai,
            batch_size=batch_size,
            hours_lookback=hours if job_type == "incremental" else None,
        )

        pipeline = ETLPipeline(config)

        # Run job
        if job_type == "stream" and stream_id:
            result = pipeline.run_single_stream(stream_id)
        elif job_type == "incremental":
            result = pipeline.run_incremental(hours=hours)
        else:
            result = pipeline.run()

        return {
            "status": result.status,
            "pipeline_id": result.pipeline_id,
            "streams_processed": result.streams_processed,
            "total_extracted": result.total_extracted,
            "total_loaded": result.total_loaded,
            "errors": result.errors[:10],  # First 10 errors
        }, 200

    except Exception as e:
        logger.error(f"HTTP ETL failed: {e}")
        return {"error": str(e)}, 500


@functions_framework.http
def etl_status_handler(request):
    """
    HTTP endpoint to check ETL status and stream info.
    """
    try:
        stream_manager = StreamManager(PROJECT_ID)
        streams = stream_manager.get_all_streams()

        return {
            "status": "ok",
            "project_id": PROJECT_ID,
            "streams": [
                {
                    "stream_id": s.stream_id,
                    "direction": s.direction.value,
                    "flow": s.flow.value,
                    "last_sync_offset": s.last_sync_offset,
                    "total_synced": s.total_records_synced,
                }
                for s in streams
            ],
            "total_streams": len(streams),
        }, 200

    except Exception as e:
        return {"error": str(e)}, 500


def _publish_result(result: PipelineResult):
    """Publish ETL result to Pub/Sub for monitoring."""
    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, RESULTS_TOPIC)

        message = json.dumps(result.to_dict())
        publisher.publish(topic_path, message.encode("utf-8"))
        logger.info(f"Published ETL result to {RESULTS_TOPIC}")

    except Exception as e:
        logger.warning(f"Could not publish ETL result: {e}")


# Local testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run ETL pipeline locally")
    parser.add_argument("--job-type", default="incremental", choices=["full", "incremental", "stream"])
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--stream-id", default=None)
    parser.add_argument("--enable-ai", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1000)

    args = parser.parse_args()

    config = PipelineConfig(
        project_id=PROJECT_ID,
        enable_ai_enrichment=args.enable_ai,
        batch_size=args.batch_size,
        hours_lookback=args.hours if args.job_type == "incremental" else None,
    )

    pipeline = ETLPipeline(config)

    if args.job_type == "stream" and args.stream_id:
        result = pipeline.run_single_stream(args.stream_id)
    elif args.job_type == "incremental":
        result = pipeline.run_incremental(hours=args.hours)
    else:
        result = pipeline.run()

    print(f"\nPipeline Result:")
    print(f"  Status: {result.status}")
    print(f"  Streams: {result.streams_processed}")
    print(f"  Extracted: {result.total_extracted}")
    print(f"  Loaded: {result.total_loaded}")
    print(f"  Errors: {len(result.errors)}")
