"""
Configuration module for Glass Pane service.
Centralizes all configuration with validation.
"""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # GCP Settings
    project_id: str = field(
        default_factory=lambda: os.environ.get("PROJECT_ID", "diatonic-ai-gcp")
    )

    # BigQuery Settings
    canonical_view: str = field(
        default_factory=lambda: os.environ.get(
            "CANONICAL_VIEW", "org_observability.logs_canonical_v2"
        )
    )

    # Query Limits
    default_limit: int = field(
        default_factory=lambda: int(os.environ.get("DEFAULT_LIMIT", "100"))
    )
    max_limit: int = field(
        default_factory=lambda: int(os.environ.get("MAX_LIMIT", "1000"))
    )
    default_time_window_hours: int = field(
        default_factory=lambda: int(os.environ.get("DEFAULT_TIME_WINDOW_HOURS", "24"))
    )
    max_time_window_hours: int = field(
        default_factory=lambda: int(os.environ.get("MAX_TIME_WINDOW_HOURS", "168"))
    )

    # Server Settings
    port: int = field(
        default_factory=lambda: int(os.environ.get("PORT", "8080"))
    )

    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if not self.project_id:
            errors.append("PROJECT_ID is required")

        if self.default_limit < 1:
            errors.append("DEFAULT_LIMIT must be at least 1")

        if self.default_limit > self.max_limit:
            errors.append("DEFAULT_LIMIT cannot exceed MAX_LIMIT")

        if self.default_time_window_hours > self.max_time_window_hours:
            errors.append(
                "DEFAULT_TIME_WINDOW_HOURS cannot exceed MAX_TIME_WINDOW_HOURS"
            )

        return errors

    def get_full_view_path(self) -> str:
        """Get fully qualified view path."""
        return f"{self.project_id}.{self.canonical_view}"


# Global config instance
config = Config()
