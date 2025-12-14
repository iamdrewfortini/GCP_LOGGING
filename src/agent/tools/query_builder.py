from typing import List, Optional
import os

PROJECT_ID = os.environ.get("PROJECT_ID", "diatonic-ai-gcp")
DATASET_ID = os.environ.get("DATASET_ID", "central_logging_v1")

class QueryBuilder:
    @staticmethod
    def get_canonical_sql(
        start_time: str,
        end_time: str,
        severity: Optional[str] = None,
        service: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[str, list]:
        """
        Returns (sql_string, query_parameters).
        Constructs the query over the 'virtual' canonical view.
        """
        
        # Base CTE (mimics the VIEW logic)
        # In a real prod env, this would be CREATE VIEW and we'd just select from it.
        # Here we inline it to ensure it works without DDL.
        # Just use the view directly now that it has insertId, logName, trace, spanId
        base_cte = f"""
        WITH unioned_logs AS (
            SELECT *
            FROM `{PROJECT_ID}.{DATASET_ID}.view_canonical_logs`
            WHERE event_ts BETWEEN @start_time AND @end_time
        )
        """

        # Filters
        where_clauses = ["1=1"]
        params = [
            bigquery.ScalarQueryParameter("start_time", "TIMESTAMP", start_time),
            bigquery.ScalarQueryParameter("end_time", "TIMESTAMP", end_time)
        ]

        if severity:
            where_clauses.append("severity = @severity")
            params.append(bigquery.ScalarQueryParameter("severity", "STRING", severity))
        
        if service:
            where_clauses.append("service = @service")
            params.append(bigquery.ScalarQueryParameter("service", "STRING", service))

        # Final Query
        sql = f"""
        {base_cte}
        SELECT * FROM unioned_logs
        WHERE {" AND ".join(where_clauses)}
        ORDER BY event_ts DESC
        LIMIT @limit OFFSET @offset
        """
        
        params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
        params.append(bigquery.ScalarQueryParameter("offset", "INT64", offset))

        return sql, params

# We need to import bigquery inside methods or at top level if available
from google.cloud import bigquery
