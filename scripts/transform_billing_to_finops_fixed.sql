-- Transform billing export data to match bq_jobs_daily_v2 schema
-- Run this to populate org_finops.bq_jobs_daily_v2

CREATE OR REPLACE TABLE `diatonic-ai-gcp.org_finops.bq_jobs_daily_v2`
PARTITION BY dt
CLUSTER BY project_id, statement_type, cache_hit
OPTIONS (
  description = 'BigQuery job cost/usage (clustered, labeled)',
  labels = [
    ('env','prod'),('team','finops'),('owner','platform-data'),
    ('data_product','bq-costs'),('version','v2'),('lineage_hash','billing_export_transform'),
    ('retention_class','finance')
  ],
  require_partition_filter = TRUE
)
AS
SELECT
  DATE(usage_start_time) as dt,
  project.id as project_id,
  COALESCE(service.description, 'unknown') as statement_type,
  cost as cost_usd,
  currency,
  service.description as service_name,
  sku.description as sku_description,
  usage_start_time,
  usage_end_time,
  CAST(NULL AS STRING) as job_id,
  CAST(NULL AS STRING) as user_email,
  CAST(NULL AS INT64) as total_bytes_processed,
  CAST(NULL AS BOOL) as cache_hit,
  'billing_export' as source_system,
  CURRENT_TIMESTAMP() as ingestion_time
FROM `diatonic-ai-gcp.org_finops.bq_billing_export`
WHERE 
  service.description IS NOT NULL
  AND DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND cost > 0;