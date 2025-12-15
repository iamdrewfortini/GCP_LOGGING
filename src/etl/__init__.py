"""
ETL Pipeline for GCP Log Normalization

This package provides a complete Extract-Transform-Load pipeline for normalizing
all GCP log types into a unified master_logs table.

Pipeline Stages:
1. EXTRACT - Pull logs from source tables with stream tracking
2. NORMALIZE - Parse all payload types (text, JSON, proto) into unified schema
3. TRANSFORM - Apply Vertex AI analysis and enrichment
4. LOAD - Insert into master_logs table

Components:
- extractor: Extracts logs from BigQuery source tables
- normalizer: Normalizes different payload types
- transformer: Applies AI enrichment via Vertex AI
- loader: Loads normalized logs into master_logs
- scheduler: Manages ETL job scheduling
- stream_manager: Tracks data streams and coordinates
"""

__version__ = "1.0.0"

from src.etl.extractor import LogExtractor
from src.etl.normalizer import LogNormalizer
from src.etl.transformer import LogTransformer
from src.etl.loader import LogLoader
from src.etl.pipeline import ETLPipeline
from src.etl.stream_manager import StreamManager
from src.etl.firebase_manager import ETLFirebaseManager

__all__ = [
    "LogExtractor",
    "LogNormalizer",
    "LogTransformer",
    "LogLoader",
    "ETLPipeline",
    "StreamManager",
    "ETLFirebaseManager",
]
