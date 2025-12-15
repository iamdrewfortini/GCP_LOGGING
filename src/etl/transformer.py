"""
Log Transformer

Transforms normalized logs with Vertex AI enrichment.
Adds AI-generated summaries, classifications, and insights.
"""

import logging
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

from src.etl.normalizer import NormalizedLog

logger = logging.getLogger(__name__)


# Log categories for classification
LOG_CATEGORIES = [
    "authentication",      # Login, auth, tokens
    "authorization",       # Permissions, access control
    "data_access",         # Database, storage operations
    "deployment",          # Build, deploy, release
    "error",               # Errors, exceptions, failures
    "performance",         # Latency, throughput, metrics
    "security",            # Security events, threats
    "system",              # Infrastructure, system events
    "application",         # Application-level logs
    "network",             # Network, connectivity
    "configuration",       # Config changes
    "other"                # Uncategorized
]


@dataclass
class TransformConfig:
    """Configuration for log transformation."""
    enable_summarization: bool = True
    enable_classification: bool = True
    enable_analysis: bool = False  # Deep analysis (expensive)
    model_name: str = "gemini-2.0-flash"
    batch_size: int = 10
    max_summary_length: int = 200
    project_id: str = "diatonic-ai-gcp"
    location: str = "us-central1"


class LogTransformer:
    """
    Transforms logs with Vertex AI enrichment.

    Features:
    - Message summarization (concise AI-generated summaries)
    - Category classification (security, deployment, error, etc.)
    - Anomaly detection hints
    - Related log suggestions
    """

    def __init__(self, config: TransformConfig = None):
        self.config = config or TransformConfig()
        self.model: Optional[GenerativeModel] = None
        self._init_vertex()
        self.stats = {
            "processed": 0,
            "summarized": 0,
            "classified": 0,
            "errors": 0,
        }

    def _init_vertex(self):
        """Initialize Vertex AI client."""
        try:
            vertexai.init(
                project=self.config.project_id,
                location=self.config.location
            )
            self.model = GenerativeModel(self.config.model_name)
            logger.info(f"Initialized Vertex AI model: {self.config.model_name}")
        except Exception as e:
            logger.warning(f"Could not initialize Vertex AI: {e}")
            self.model = None

    def transform(self, log: NormalizedLog) -> NormalizedLog:
        """
        Transform a single log with AI enrichment.

        Args:
            log: NormalizedLog to transform

        Returns:
            Enriched NormalizedLog
        """
        self.stats["processed"] += 1

        # Skip AI processing if disabled or model not available
        if not self.model:
            return log

        try:
            # Generate summary
            if self.config.enable_summarization and log.message:
                log.message_summary = self._summarize(log)
                if log.message_summary:
                    self.stats["summarized"] += 1

            # Classify log
            if self.config.enable_classification:
                log.message_category = self._classify(log)
                if log.message_category:
                    self.stats["classified"] += 1

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error transforming log {log.log_id}: {e}")

        return log

    def transform_batch(self, logs: List[NormalizedLog]) -> List[NormalizedLog]:
        """
        Transform a batch of logs with AI enrichment.

        Uses batch processing for efficiency.
        """
        if not self.model:
            return logs

        # Process in sub-batches for efficiency
        batch_size = self.config.batch_size
        for i in range(0, len(logs), batch_size):
            batch = logs[i:i + batch_size]

            # Batch summarization
            if self.config.enable_summarization:
                summaries = self._batch_summarize(batch)
                for log, summary in zip(batch, summaries):
                    log.message_summary = summary
                    if summary:
                        self.stats["summarized"] += 1

            # Batch classification
            if self.config.enable_classification:
                categories = self._batch_classify(batch)
                for log, category in zip(batch, categories):
                    log.message_category = category
                    if category:
                        self.stats["classified"] += 1

            self.stats["processed"] += len(batch)

        return logs

    def _summarize(self, log: NormalizedLog) -> Optional[str]:
        """Generate a concise summary for a log."""
        if not log.message or len(log.message) < 50:
            return log.message[:self.config.max_summary_length] if log.message else None

        prompt = f"""Summarize this log entry in 1-2 sentences (max {self.config.max_summary_length} chars):

Severity: {log.severity}
Service: {log.service_name}
Type: {log.log_type}
Message: {log.message[:2000]}

Summary:"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=100,
                )
            )
            summary = response.text.strip()
            return summary[:self.config.max_summary_length]
        except Exception as e:
            logger.debug(f"Summarization error: {e}")
            return None

    def _classify(self, log: NormalizedLog) -> Optional[str]:
        """Classify log into a category."""
        # Quick heuristic classification first
        category = self._quick_classify(log)
        if category:
            return category

        # Fall back to AI classification for ambiguous cases
        prompt = f"""Classify this log into ONE category from: {', '.join(LOG_CATEGORIES)}

Severity: {log.severity}
Service: {log.service_name}
Type: {log.log_type}
Message: {log.message[:500]}

Category (single word):"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=20,
                )
            )
            category = response.text.strip().lower().replace(" ", "_")
            if category in LOG_CATEGORIES:
                return category
            return "other"
        except Exception as e:
            logger.debug(f"Classification error: {e}")
            return "other"

    def _quick_classify(self, log: NormalizedLog) -> Optional[str]:
        """Quick heuristic-based classification."""
        message = (log.message or "").lower()
        service = (log.service_name or "").lower()
        log_type = log.log_type

        # Audit logs
        if log.is_audit or "audit" in log_type:
            if any(kw in message for kw in ["login", "signin", "auth", "token"]):
                return "authentication"
            if any(kw in message for kw in ["permission", "access", "denied", "forbidden"]):
                return "authorization"
            if any(kw in message for kw in ["read", "write", "delete", "create", "update"]):
                return "data_access"
            return "security"

        # Build/deployment
        if "build" in service or "deploy" in message or log_type == "build":
            return "deployment"

        # Errors
        if log.is_error or log.error_message:
            return "error"

        # Request logs
        if log.is_request or log.http_method:
            if log.http_status and log.http_status >= 400:
                return "error"
            if log.http_latency_ms and log.http_latency_ms > 1000:
                return "performance"
            return "network"

        # Security keywords
        if any(kw in message for kw in ["security", "threat", "attack", "vulnerability"]):
            return "security"

        # Config changes
        if any(kw in message for kw in ["config", "setting", "environment"]):
            return "configuration"

        # System logs
        if log_type == "system" or "syslog" in service:
            return "system"

        return None

    def _batch_summarize(self, logs: List[NormalizedLog]) -> List[Optional[str]]:
        """Batch summarization for efficiency."""
        # Build batch prompt
        entries = []
        for i, log in enumerate(logs):
            if log.message and len(log.message) >= 50:
                entries.append(f"{i}. [{log.severity}] {log.message[:500]}")
            else:
                entries.append(f"{i}. SKIP")

        if not any("SKIP" not in e for e in entries):
            return [log.message[:self.config.max_summary_length] if log.message else None for log in logs]

        prompt = f"""Summarize each log entry in 1 short sentence. Format: NUMBER. Summary

{chr(10).join(entries)}

Summaries:"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=500,
                )
            )

            # Parse response
            summaries = [None] * len(logs)
            for line in response.text.strip().split("\n"):
                try:
                    if ". " in line:
                        idx_str, summary = line.split(". ", 1)
                        idx = int(idx_str.strip())
                        if 0 <= idx < len(logs):
                            summaries[idx] = summary[:self.config.max_summary_length]
                except:
                    continue

            # Fill in missing with truncated original
            for i, (s, log) in enumerate(zip(summaries, logs)):
                if s is None and log.message:
                    summaries[i] = log.message[:self.config.max_summary_length]

            return summaries

        except Exception as e:
            logger.debug(f"Batch summarization error: {e}")
            return [log.message[:self.config.max_summary_length] if log.message else None for log in logs]

    def _batch_classify(self, logs: List[NormalizedLog]) -> List[Optional[str]]:
        """Batch classification for efficiency."""
        # Use quick classification first
        results = []
        needs_ai = []

        for i, log in enumerate(logs):
            quick = self._quick_classify(log)
            if quick:
                results.append(quick)
            else:
                results.append(None)
                needs_ai.append(i)

        # Only use AI for ambiguous cases
        if not needs_ai or not self.model:
            return results

        # Build batch prompt for remaining
        entries = []
        for idx in needs_ai:
            log = logs[idx]
            entries.append(f"{idx}. [{log.severity}] {log.service_name}: {log.message[:200]}")

        prompt = f"""Classify each log into ONE category from: {', '.join(LOG_CATEGORIES)}
Format: NUMBER. category

{chr(10).join(entries)}

Classifications:"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=200,
                )
            )

            for line in response.text.strip().split("\n"):
                try:
                    if ". " in line:
                        idx_str, category = line.split(". ", 1)
                        idx = int(idx_str.strip())
                        category = category.strip().lower().replace(" ", "_")
                        if 0 <= idx < len(logs) and category in LOG_CATEGORIES:
                            results[idx] = category
                except:
                    continue

        except Exception as e:
            logger.debug(f"Batch classification error: {e}")

        # Fill remaining with 'other'
        return [r or "other" for r in results]

    def get_stats(self) -> Dict:
        """Get transformation statistics."""
        return self.stats.copy()


class LightweightTransformer:
    """
    Lightweight transformer without AI (for high-volume processing).

    Uses heuristics only for classification and truncation for summaries.
    """

    def __init__(self):
        self.stats = {"processed": 0}

    def transform(self, log: NormalizedLog) -> NormalizedLog:
        """Transform log with heuristics only."""
        self.stats["processed"] += 1

        # Truncated summary
        if log.message:
            log.message_summary = log.message[:200]

        # Heuristic classification
        log.message_category = self._classify(log)

        return log

    def transform_batch(self, logs: List[NormalizedLog]) -> List[NormalizedLog]:
        """Transform batch of logs."""
        return [self.transform(log) for log in logs]

    def _classify(self, log: NormalizedLog) -> str:
        """Quick classification using heuristics."""
        message = (log.message or "").lower()

        if log.is_audit:
            return "security"
        if log.is_error or log.severity in ["ERROR", "CRITICAL", "ALERT", "EMERGENCY"]:
            return "error"
        if log.is_request:
            return "network"
        if "build" in log.source_table.lower():
            return "deployment"
        if "auth" in message or "login" in message:
            return "authentication"

        return "application"

    def get_stats(self) -> Dict:
        return self.stats.copy()
