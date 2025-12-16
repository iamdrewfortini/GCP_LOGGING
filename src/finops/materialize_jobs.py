from google.cloud import bigquery
from datetime import datetime, timedelta
from src.config import config
import os


def materialize_daily_jobs():
    """
    Materializes yesterday's BQ jobs into org_finops.bq_jobs_daily.
    """
    yesterday = (datetime.utcnow() - timedelta(days=1)).date()
    # Or just run for a specific date range.
    
    # We rely on the project ID where jobs run. 
    # Usually we query `region-us.INFORMATION_SCHEMA.JOBS`.
    # We need to loop over projects if multiple, or assume we run this in the main project.
    
    # Simplified SQL as per prompt requirements
    sql = f"""
    CREATE TABLE IF NOT EXISTS `{config.PROJECT_ID_FINOPS}.org_finops.bq_jobs_daily`
    (dt DATE, job_id STRING, project_id STRING, user_email STRING, labels JSON, total_bytes_processed INT64, total_slot_ms INT64, cache_hit BOOL, statement_type STRING, query_hash STRING, referenced_tables ARRAY<STRING>)
    PARTITION BY dt
    OPTIONS(description="Daily rollup of BigQuery jobs");
    
    INSERT INTO `{config.PROJECT_ID_FINOPS}.org_finops.bq_jobs_daily`
    SELECT
        DATE(creation_time) as dt,
        job_id,
        project_id,
        user_email,
        TO_JSON(labels) as labels,
        total_bytes_processed,
        total_slot_ms,
        cache_hit,
        statement_type,
        query_info.query_hashes.normalized_literals as query_hash,
        referenced_tables.table_id as referenced_tables -- simplified
    FROM `{config.PROJECT_ID_LOGS}.region-{config.BQ_LOCATION.lower()}.INFORMATION_SCHEMA.JOBS`
    WHERE DATE(creation_time) = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
    """
    
    # Note: referenced_tables is complex in InfoSchema, simplified here.
    
    client = bigquery.Client(project=config.PROJECT_ID_FINOPS)
    job = client.query(sql)
    job.result()
    print("Materialized bq_jobs_daily")

if __name__ == "__main__":
    materialize_daily_jobs()
