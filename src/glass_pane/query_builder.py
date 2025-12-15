"""src.glass_pane.query_builder

Query builder module for canonical log queries.
Provides type-safe, parameterized query construction over the canonical view.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from google.cloud import bigquery


VALID_SEVERITIES = [
  "DEFAULT",
  "DEBUG",
  "INFO",
  "NOTICE",
  "WARNING",
  "ERROR",
  "CRITICAL",
  "ALERT",
  "EMERGENCY",
]


@dataclass
class LogQueryParams:
  """Parameters for log query."""

  limit: int = 100
  hours: int = 24
  severity: Optional[str] = None
  service: Optional[str] = None
  search: Optional[str] = None
  source_table: Optional[str] = None

  def validate(self, max_limit: int = 1000, max_hours: int = 168) -> List[str]:
    errors: List[str] = []

    if self.limit < 1:
      errors.append("Limit must be at least 1")
    if self.limit > max_limit:
      errors.append(f"Limit cannot exceed {max_limit}")

    if self.hours < 1:
      errors.append("Hours must be at least 1")
    if self.hours > max_hours:
      errors.append(f"Hours cannot exceed {max_hours}")

    if self.severity and self.severity.upper() not in VALID_SEVERITIES:
      errors.append(f"Invalid severity: {self.severity}")

    return errors


class CanonicalQueryBuilder:
  """Builder for canonical log queries against master_logs table."""

  DISPLAY_FIELDS = [
    "log_id",
    "event_timestamp",
    "severity",
    "service_name",
    "source_log_name",
    "message",
    "source_table",
    "stream_id",
    "trace_id",
    "span_id",
    "log_type",
    "resource_type",
  ]

  # Universal Envelope fields from the canonical view
  ENVELOPE_FIELDS = [
    "universal_envelope.event_id AS envelope_event_id",
    "universal_envelope.event_ts AS envelope_event_ts",
    "universal_envelope.service.name AS envelope_service_name",
    "universal_envelope.trace.trace_id AS envelope_trace_id",
    "universal_envelope.actor.user_id AS envelope_user_id",
    "universal_envelope.privacy.pii_risk AS envelope_pii_risk",
    "universal_envelope.environment AS envelope_environment",
    "universal_envelope.correlation.request_id AS envelope_request_id",
    "universal_envelope.correlation.session_id AS envelope_session_id",
  ]

  # Canonical view name for envelope queries
  CANONICAL_VIEW = "org_logs_norm.v_logs_all_entry_canon"

  def __init__(
    self,
    project_id: str,
    view_name: str = "central_logging_v1.master_logs",
    include_envelope: bool = False
  ):
    self.project_id = project_id
    self.view_name = view_name
    self.full_view = f"{project_id}.{view_name}"
    self.include_envelope = include_envelope

  def build_list_query(self, params: LogQueryParams, use_envelope: bool = False) -> Dict[str, Any]:
    from datetime import datetime, timedelta

    bq_params = []
    where_clauses = []

    # Partition filter for performance (master_logs is partitioned by log_date)
    start_date = (datetime.utcnow() - timedelta(hours=params.hours)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    where_clauses.append(f"log_date BETWEEN '{start_date}' AND '{end_date}'")

    # Time window filter
    where_clauses.append(
      "event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)"
    )
    bq_params.append(bigquery.ScalarQueryParameter("hours", "INT64", params.hours))

    if params.severity:
      where_clauses.append("severity = @severity")
      bq_params.append(
        bigquery.ScalarQueryParameter("severity", "STRING", params.severity.upper())
      )

    if params.service:
      where_clauses.append("service_name LIKE @service")
      bq_params.append(bigquery.ScalarQueryParameter("service", "STRING", f"%{params.service}%"))

    if params.search:
      where_clauses.append("(message LIKE @search OR CAST(json_payload AS STRING) LIKE @search)")
      bq_params.append(bigquery.ScalarQueryParameter("search", "STRING", f"%{params.search}%"))

    if params.source_table:
      where_clauses.append("source_table = @source_table")
      bq_params.append(
        bigquery.ScalarQueryParameter("source_table", "STRING", params.source_table)
      )

    bq_params.append(bigquery.ScalarQueryParameter("limit", "INT64", params.limit))

    # Build field list - include envelope fields if requested
    fields_list = self.DISPLAY_FIELDS.copy()
    if use_envelope or self.include_envelope:
      fields_list.extend(self.ENVELOPE_FIELDS)

    fields = ", ".join(fields_list)
    where = " AND ".join(where_clauses)

    # Use canonical view for envelope queries
    if use_envelope or self.include_envelope:
      view = f"{self.project_id}.{self.CANONICAL_VIEW}"
    else:
      view = self.full_view

    sql = f"""
      SELECT {fields}
      FROM `{view}`
      WHERE {where}
      ORDER BY event_timestamp DESC
      LIMIT @limit
    """

    return {"sql": sql.strip(), "params": bq_params}

  def build_count_by_severity_query(self, hours: int = 24) -> Dict[str, Any]:
    from datetime import datetime, timedelta
    start_date = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")

    sql = f"""
      SELECT
        severity,
        COUNT(*) as count
      FROM `{self.full_view}`
      WHERE log_date BETWEEN '{start_date}' AND '{end_date}'
        AND event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
      GROUP BY severity
      ORDER BY count DESC
    """
    params = [bigquery.ScalarQueryParameter("hours", "INT64", hours)]
    return {"sql": sql.strip(), "params": params}

  def build_count_by_service_query(self, hours: int = 24) -> Dict[str, Any]:
    from datetime import datetime, timedelta
    start_date = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")

    sql = f"""
      SELECT
        service_name,
        COUNT(*) as count,
        COUNTIF(severity IN ('ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY')) as error_count
      FROM `{self.full_view}`
      WHERE log_date BETWEEN '{start_date}' AND '{end_date}'
        AND event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
      GROUP BY service_name
      ORDER BY count DESC
    """
    params = [bigquery.ScalarQueryParameter("hours", "INT64", hours)]
    return {"sql": sql.strip(), "params": params}

  def build_source_table_stats_query(self, hours: int = 24) -> Dict[str, Any]:
    from datetime import datetime, timedelta
    start_date = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")

    sql = f"""
      SELECT
        source_table,
        stream_id,
        COUNT(*) as count
      FROM `{self.full_view}`
      WHERE log_date BETWEEN '{start_date}' AND '{end_date}'
        AND event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
      GROUP BY source_table, stream_id
      ORDER BY count DESC
    """
    params = [bigquery.ScalarQueryParameter("hours", "INT64", hours)]
    return {"sql": sql.strip(), "params": params}
