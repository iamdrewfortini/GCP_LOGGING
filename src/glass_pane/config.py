"""src.glass_pane.config

Configuration for the Glass Pane UI + log query layer.

This module is used by the unified FastAPI Cloud Run service.
"""

import os
from dataclasses import dataclass, field
from typing import List


def _get_logs_project_id() -> str:
  return (
    os.environ.get("PROJECT_ID_LOGS")
    or os.environ.get("PROJECT_ID")
    or os.environ.get("GOOGLE_CLOUD_PROJECT")
    or "diatonic-ai-gcp"
  )


@dataclass
class GlassPaneConfig:
  # GCP / BigQuery
  logs_project_id: str = field(default_factory=_get_logs_project_id)

  # Dataset + view name (without project), e.g. "org_observability.logs_canonical_v2"
  canonical_view: str = field(
    default_factory=lambda: os.environ.get(
      "CANONICAL_VIEW",
      "org_observability.logs_canonical_v2",
    )
  )

  # Query limits
  default_limit: int = field(default_factory=lambda: int(os.environ.get("DEFAULT_LIMIT", "100")))
  max_limit: int = field(default_factory=lambda: int(os.environ.get("MAX_LIMIT", "250")))
  default_time_window_hours: int = field(
    default_factory=lambda: int(os.environ.get("DEFAULT_TIME_WINDOW_HOURS", "24"))
  )
  max_time_window_hours: int = field(
    default_factory=lambda: int(os.environ.get("MAX_TIME_WINDOW_HOURS", "168"))
  )

  # Server
  port: int = field(default_factory=lambda: int(os.environ.get("PORT", "8080")))

  def validate(self) -> List[str]:
    errors: List[str] = []

    if not self.logs_project_id:
      errors.append("PROJECT_ID_LOGS/PROJECT_ID is required")

    if self.default_limit < 1:
      errors.append("DEFAULT_LIMIT must be at least 1")

    if self.default_limit > self.max_limit:
      errors.append("DEFAULT_LIMIT cannot exceed MAX_LIMIT")

    if self.default_time_window_hours > self.max_time_window_hours:
      errors.append("DEFAULT_TIME_WINDOW_HOURS cannot exceed MAX_TIME_WINDOW_HOURS")

    return errors

  @property
  def full_view(self) -> str:
    return f"{self.logs_project_id}.{self.canonical_view}"


glass_config = GlassPaneConfig()
