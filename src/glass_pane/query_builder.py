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
  """Builder for canonical log view queries."""

  DISPLAY_FIELDS = [
    "insert_id",
    "event_timestamp",
    "severity",
    "service_name",
    "log_name",
    "display_message",
    "source_table",
    "trace_id",
    "span_id",
  ]

  def __init__(self, project_id: str, view_name: str):
    self.project_id = project_id
    self.view_name = view_name
    self.full_view = f"{project_id}.{view_name}"

  def build_list_query(self, params: LogQueryParams) -> Dict[str, Any]:
    bq_params = []
    where_clauses = []

    # Time window filter (always required for performance)
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
      where_clauses.append("(display_message LIKE @search OR json_payload LIKE @search)")
      bq_params.append(bigquery.ScalarQueryParameter("search", "STRING", f"%{params.search}%"))

    if params.source_table:
      where_clauses.append("source_table = @source_table")
      bq_params.append(
        bigquery.ScalarQueryParameter("source_table", "STRING", params.source_table)
      )

    bq_params.append(bigquery.ScalarQueryParameter("limit", "INT64", params.limit))

    fields = ", ".join(self.DISPLAY_FIELDS)
    where = " AND ".join(where_clauses)

    sql = f"""
      SELECT {fields}
      FROM `{self.full_view}`
      WHERE {where}
      ORDER BY event_timestamp DESC
      LIMIT @limit
    """

    return {"sql": sql.strip(), "params": bq_params}

  def build_count_by_severity_query(self, hours: int = 24) -> Dict[str, Any]:
    sql = f"""
      SELECT
        severity,
        COUNT(*) as count
      FROM `{self.full_view}`
      WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
      GROUP BY severity
      ORDER BY count DESC
    """
    params = [bigquery.ScalarQueryParameter("hours", "INT64", hours)]
    return {"sql": sql.strip(), "params": params}

  def build_count_by_service_query(self, hours: int = 24) -> Dict[str, Any]:
    sql = f"""
      SELECT
        service_name,
        COUNT(*) as count,
        COUNTIF(severity IN ('ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY')) as error_count
      FROM `{self.full_view}`
      WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
      GROUP BY service_name
      ORDER BY count DESC
    """
    params = [bigquery.ScalarQueryParameter("hours", "INT64", hours)]
    return {"sql": sql.strip(), "params": params}

  def build_source_table_stats_query(self, hours: int = 24) -> Dict[str, Any]:
    sql = f"""
      SELECT
        source_table,
        COUNT(*) as count
      FROM `{self.full_view}`
      WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
      GROUP BY source_table
      ORDER BY count DESC
    """
    params = [bigquery.ScalarQueryParameter("hours", "INT64", hours)]
    return {"sql": sql.strip(), "params": params}
