"""
ETL Pipeline

Complete Extract-Transform-Load pipeline for log normalization.
Orchestrates all ETL components for continuous processing.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable

from src.etl.stream_manager import StreamManager, LogStream
from src.etl.extractor import LogExtractor, RawLogRecord
from src.etl.normalizer import LogNormalizer, NormalizedLog
from src.etl.transformer import LogTransformer, LightweightTransformer, TransformConfig
from src.etl.loader import LogLoader

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for ETL pipeline."""
    project_id: str = "diatonic-ai-gcp"

    # Extraction
    batch_size: int = 1000
    max_batches_per_stream: Optional[int] = None
    hours_lookback: Optional[int] = None  # None = all time

    # Transformation
    enable_ai_enrichment: bool = False  # Use LightweightTransformer if False
    ai_model: str = "gemini-2.0-flash"

    # Loading
    load_batch_size: int = 500

    # Processing
    parallel_streams: int = 1  # Number of streams to process in parallel
    continue_on_error: bool = True

    # Cleanup
    cleanup_source_after_days: Optional[int] = None  # None = no cleanup


@dataclass
class PipelineResult:
    """Result of a pipeline run."""
    pipeline_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "RUNNING"
    streams_processed: int = 0
    total_extracted: int = 0
    total_normalized: int = 0
    total_transformed: int = 0
    total_loaded: int = 0
    errors: List[str] = field(default_factory=list)
    stream_results: Dict[str, Dict] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "pipeline_id": self.pipeline_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "streams_processed": self.streams_processed,
            "total_extracted": self.total_extracted,
            "total_normalized": self.total_normalized,
            "total_transformed": self.total_transformed,
            "total_loaded": self.total_loaded,
            "errors": self.errors,
            "stream_results": self.stream_results,
        }


class ETLPipeline:
    """
    Complete ETL pipeline for log normalization.

    Pipeline stages:
    1. DISCOVER - Find all log streams
    2. EXTRACT - Pull raw logs from BigQuery sources
    3. NORMALIZE - Parse payloads into unified schema
    4. TRANSFORM - Apply AI enrichment (optional)
    5. LOAD - Insert into master_logs table
    """

    def __init__(self, config: PipelineConfig = None):
        self.config = config or PipelineConfig()

        # Initialize components
        self.stream_manager = StreamManager(self.config.project_id)
        self.extractor = LogExtractor(self.config.project_id)
        self.normalizer = LogNormalizer()
        self.loader = LogLoader(self.config.project_id)

        # Initialize transformer based on config
        if self.config.enable_ai_enrichment:
            transform_config = TransformConfig(
                model_name=self.config.ai_model,
                project_id=self.config.project_id,
            )
            self.transformer = LogTransformer(transform_config)
        else:
            self.transformer = LightweightTransformer()

        # Progress callback
        self.on_progress: Optional[Callable[[str, int, int], None]] = None

    def run(
        self,
        streams: Optional[List[str]] = None,
        discover: bool = True
    ) -> PipelineResult:
        """
        Run the full ETL pipeline.

        Args:
            streams: Optional list of stream IDs to process (None = all)
            discover: Whether to discover new streams first

        Returns:
            PipelineResult with statistics
        """
        result = PipelineResult(
            pipeline_id=str(uuid.uuid4()),
            started_at=datetime.utcnow()
        )

        try:
            # Ensure tables exist
            logger.info("Ensuring master_logs table exists...")
            self.loader.ensure_tables()

            # Discover streams
            if discover:
                logger.info("Discovering log streams...")
                discovered = self.stream_manager.discover_streams()
                logger.info(f"Discovered {len(discovered)} streams")

                # Register discovered streams
                for stream in discovered:
                    self.stream_manager.register_stream(stream)

            # Get streams to process
            if streams:
                target_streams = [
                    self.stream_manager.get_stream(s) for s in streams
                    if self.stream_manager.get_stream(s)
                ]
            else:
                target_streams = self.stream_manager.get_all_streams()

            if not target_streams:
                logger.warning("No streams to process")
                result.status = "COMPLETED"
                result.completed_at = datetime.utcnow()
                return result

            logger.info(f"Processing {len(target_streams)} streams...")

            # Process each stream
            for stream in target_streams:
                try:
                    stream_result = self._process_stream(stream, result)
                    result.stream_results[stream.stream_id] = stream_result
                    result.streams_processed += 1
                except Exception as e:
                    error_msg = f"Error processing stream {stream.stream_id}: {e}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)

                    if not self.config.continue_on_error:
                        raise

            # Cleanup old source data if configured
            if self.config.cleanup_source_after_days:
                self._cleanup_sources(target_streams)

            result.status = "COMPLETED" if not result.errors else "PARTIAL"
            result.completed_at = datetime.utcnow()

            logger.info(f"Pipeline complete: {result.total_loaded} logs loaded, "
                       f"{len(result.errors)} errors")

        except Exception as e:
            result.status = "FAILED"
            result.errors.append(str(e))
            result.completed_at = datetime.utcnow()
            logger.error(f"Pipeline failed: {e}")

        return result

    def _process_stream(
        self,
        stream: LogStream,
        result: PipelineResult
    ) -> Dict[str, Any]:
        """Process a single stream through the ETL pipeline."""
        stream_result = {
            "stream_id": stream.stream_id,
            "extracted": 0,
            "normalized": 0,
            "transformed": 0,
            "loaded": 0,
            "errors": [],
        }

        logger.info(f"Processing stream: {stream.stream_id}")

        # Get starting offset from checkpoint
        start_offset = stream.last_sync_offset

        batch_count = 0
        for raw_batch in self.extractor.extract_batch(
            stream,
            batch_size=self.config.batch_size,
            max_batches=self.config.max_batches_per_stream,
            start_offset=start_offset
        ):
            batch_count += 1

            try:
                # Stage 1: Extract (already done by iterator)
                stream_result["extracted"] += len(raw_batch)
                result.total_extracted += len(raw_batch)

                # Stage 2: Normalize
                normalized = self.normalizer.normalize_batch(raw_batch)
                stream_result["normalized"] += len(normalized)
                result.total_normalized += len(normalized)

                # Stage 3: Transform
                transformed = self.transformer.transform_batch(normalized)
                stream_result["transformed"] += len(transformed)
                result.total_transformed += len(transformed)

                # Stage 4: Load
                loaded = self.loader.load(transformed)
                stream_result["loaded"] += loaded
                result.total_loaded += loaded

                # Update checkpoint
                new_offset = start_offset + stream_result["extracted"]
                self.stream_manager.update_sync_state(
                    stream.stream_id,
                    offset=new_offset,
                    records_synced=len(raw_batch)
                )

                # Progress callback
                if self.on_progress:
                    self.on_progress(stream.stream_id, stream_result["loaded"], stream_result["extracted"])

                logger.info(f"  Batch {batch_count}: extracted={len(raw_batch)}, loaded={loaded}")

            except Exception as e:
                error_msg = f"Error in batch {batch_count}: {e}"
                logger.error(error_msg)
                stream_result["errors"].append(error_msg)

                if not self.config.continue_on_error:
                    raise

        logger.info(f"Completed stream {stream.stream_id}: "
                   f"extracted={stream_result['extracted']}, loaded={stream_result['loaded']}")

        return stream_result

    def _cleanup_sources(self, streams: List[LogStream]):
        """Clean up old data from source tables."""
        cutoff = datetime.utcnow() - timedelta(days=self.config.cleanup_source_after_days)
        logger.info(f"Cleaning up source data older than {cutoff.isoformat()}")

        for stream in streams:
            try:
                count = self.loader.cleanup_source_table(
                    stream.source_dataset,
                    stream.source_table,
                    cutoff,
                    dry_run=True  # Change to False to actually delete
                )
                logger.info(f"  {stream.stream_id}: {count} records eligible for cleanup")
            except Exception as e:
                logger.warning(f"Cleanup error for {stream.stream_id}: {e}")

    def run_incremental(self, hours: int = 24) -> PipelineResult:
        """
        Run incremental ETL for recent logs only.

        Args:
            hours: Number of hours to look back

        Returns:
            PipelineResult
        """
        logger.info(f"Running incremental ETL for last {hours} hours")

        # Create a modified config for incremental
        original_lookback = self.config.hours_lookback
        self.config.hours_lookback = hours

        try:
            result = self.run(discover=True)
        finally:
            self.config.hours_lookback = original_lookback

        return result

    def run_single_stream(self, stream_id: str) -> PipelineResult:
        """
        Run ETL for a single stream.

        Args:
            stream_id: Stream ID to process

        Returns:
            PipelineResult
        """
        return self.run(streams=[stream_id], discover=False)

    def get_pipeline_status(self) -> Dict:
        """Get current pipeline status and statistics."""
        return {
            "extractor_stats": {},
            "normalizer_stats": self.normalizer.get_stats(),
            "transformer_stats": self.transformer.get_stats(),
            "loader_stats": self.loader.get_stats(),
            "streams": [s.to_dict() for s in self.stream_manager.get_all_streams()],
        }


def run_etl_pipeline(
    project_id: str = "diatonic-ai-gcp",
    enable_ai: bool = False,
    batch_size: int = 1000,
    hours: Optional[int] = None
) -> PipelineResult:
    """
    Convenience function to run the ETL pipeline.

    Args:
        project_id: GCP project ID
        enable_ai: Whether to use AI enrichment
        batch_size: Records per batch
        hours: Optional hours lookback (None = all time)

    Returns:
        PipelineResult
    """
    config = PipelineConfig(
        project_id=project_id,
        enable_ai_enrichment=enable_ai,
        batch_size=batch_size,
        hours_lookback=hours,
    )

    pipeline = ETLPipeline(config)
    return pipeline.run()


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run pipeline
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else None
    result = run_etl_pipeline(hours=hours)

    print(f"\nPipeline completed: {result.status}")
    print(f"  Streams processed: {result.streams_processed}")
    print(f"  Total extracted: {result.total_extracted}")
    print(f"  Total loaded: {result.total_loaded}")
    print(f"  Errors: {len(result.errors)}")
