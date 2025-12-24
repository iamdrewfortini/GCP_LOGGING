-- Extract real BigQuery job billing data and populate FinOps tables
-- This uses INFORMATION_SCHEMA.JOBS_BY_PROJECT for actual usage data

CREATE OR REPLACE TABLE `diatonic-ai-gcp.org_finops.bq_jobs_daily_v2`
PARTITION BY dt
CLUSTER BY project_id, statement_type, cache_hit
OPTIONS (
  description = 'BigQuery job cost/usage from real INFORMATION_SCHEMA data',
  labels = [
    ('env','prod'),('team','finops'),('owner','platform-data'),
    ('data_product','bq-costs'),('version','v2'),('lineage_hash','information_schema_jobs'),
    ('retention_class','finance')
  ],
  require_partition_filter = TRUE
)
AS
SELECT
  DATE(creation_time) as dt,
  project_id,
  COALESCE(statement_type, 'QUERY') as statement_type,
  
  -- Calculate actual cost based on BigQuery pricing
  ROUND(
    CASE 
      WHEN total_bytes_billed IS NOT NULL THEN
        -- $6.25 per TB for on-demand queries (as of 2024)
        (CAST(total_bytes_billed AS FLOAT64) / POWER(1024, 4)) * 6.25
      ELSE 0.0
    END, 6
  ) as cost_usd,
  
  'USD' as currency,
  'BigQuery' as service_name,
  job_type as sku_description,
  creation_time as usage_start_time,
  end_time as usage_end_time,
  job_id,
  user_email,
  total_bytes_processed,
  cache_hit,
  'information_schema' as source_system,
  CURRENT_TIMESTAMP() as ingestion_time,
  
  -- Additional useful fields
  total_slot_ms,
  total_bytes_billed,
  state,
  error_result,
  labels as job_labels
  
FROM `diatonic-ai-gcp.region-us.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE 
  creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND job_type IN ('QUERY', 'LOAD', 'EXPORT', 'COPY')
  AND state = 'DONE';
