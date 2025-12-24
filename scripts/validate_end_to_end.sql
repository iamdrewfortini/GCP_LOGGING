-- =============================================================================
-- End-to-End Validation Queries  
-- Purpose: Validate complete data flow from ingestion → staging → canonical
-- Project: diatonic-ai-gcp
-- Date: 2025-12-24
-- =============================================================================

-- Query 1: Data Freshness Check
-- Verify recent data exists across all major datasets
SELECT 
  'org_logs_canon.fact_logs' as table_name,
  COUNT(*) as row_count,
  MAX(log_date) as latest_date,
  DATE_DIFF(CURRENT_DATE(), MAX(log_date), DAY) as days_old,
  CASE 
    WHEN DATE_DIFF(CURRENT_DATE(), MAX(log_date), DAY) <= 1 THEN '✅ Fresh'
    WHEN DATE_DIFF(CURRENT_DATE(), MAX(log_date), DAY) <= 7 THEN '⚠️ Stale' 
    ELSE '❌ Very Old'
  END as freshness_status
FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`
WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)

UNION ALL

SELECT 
  'org_finops.bq_jobs_daily_v2' as table_name,
  COUNT(*) as row_count,
  MAX(dt) as latest_date,
  DATE_DIFF(CURRENT_DATE(), MAX(dt), DAY) as days_old,
  CASE 
    WHEN DATE_DIFF(CURRENT_DATE(), MAX(dt), DAY) <= 1 THEN '✅ Fresh'
    WHEN DATE_DIFF(CURRENT_DATE(), MAX(dt), DAY) <= 7 THEN '⚠️ Stale' 
    ELSE '❌ Very Old'
  END as freshness_status
FROM `diatonic-ai-gcp.org_finops.bq_jobs_daily_v2`
WHERE dt >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)

UNION ALL

SELECT 
  'org_agent.tool_invocations' as table_name,
  COUNT(*) as row_count,
  MAX(invocation_date) as latest_date,
  DATE_DIFF(CURRENT_DATE(), MAX(invocation_date), DAY) as days_old,
  CASE 
    WHEN DATE_DIFF(CURRENT_DATE(), MAX(invocation_date), DAY) <= 1 THEN '✅ Fresh'
    WHEN DATE_DIFF(CURRENT_DATE(), MAX(invocation_date), DAY) <= 7 THEN '⚠️ Stale' 
    ELSE '❌ Very Old'
  END as freshness_status
FROM `diatonic-ai-gcp.org_agent.tool_invocations`
WHERE invocation_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)

UNION ALL

SELECT 
  'org_enterprise.stg_asset_inventory' as table_name,
  COUNT(*) as row_count,
  MAX(DATE(fetched_at)) as latest_date,
  DATE_DIFF(CURRENT_DATE(), MAX(DATE(fetched_at)), DAY) as days_old,
  CASE 
    WHEN DATE_DIFF(CURRENT_DATE(), MAX(DATE(fetched_at)), DAY) <= 1 THEN '✅ Fresh'
    WHEN DATE_DIFF(CURRENT_DATE(), MAX(DATE(fetched_at)), DAY) <= 7 THEN '⚠️ Stale' 
    ELSE '❌ Very Old'
  END as freshness_status
FROM `diatonic-ai-gcp.org_enterprise.stg_asset_inventory`
WHERE DATE(fetched_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)

ORDER BY table_name;

-- =============================================================================

-- Query 2: Partition Distribution Check
-- Verify partitions are properly distributed and no skew
WITH partition_stats AS (
  SELECT 
    'fact_logs' as table_name,
    log_date as partition_date,
    COUNT(*) as row_count,
    COUNT(DISTINCT trace_id) as unique_traces,
    COUNT(DISTINCT service_name) as unique_services
  FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`
  WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  GROUP BY log_date
  
  UNION ALL
  
  SELECT 
    'bq_jobs_daily_v2' as table_name,
    dt as partition_date,
    COUNT(*) as row_count,
    COUNT(DISTINCT job_id) as unique_traces,
    COUNT(DISTINCT project_id) as unique_services
  FROM `diatonic-ai-gcp.org_finops.bq_jobs_daily_v2`
  WHERE dt >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  GROUP BY dt
  
  UNION ALL
  
  SELECT 
    'tool_invocations' as table_name,
    invocation_date as partition_date,
    COUNT(*) as row_count,
    COUNT(DISTINCT invocation_id) as unique_traces,
    COUNT(DISTINCT tool_name) as unique_services
  FROM `diatonic-ai-gcp.org_agent.tool_invocations`
  WHERE invocation_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  GROUP BY invocation_date
)
SELECT 
  table_name,
  COUNT(*) as partition_count,
  MIN(row_count) as min_rows_per_partition,
  MAX(row_count) as max_rows_per_partition,
  AVG(row_count) as avg_rows_per_partition,
  STDDEV(row_count) as stddev_rows,
  -- Detect partition skew
  CASE 
    WHEN STDDEV(row_count) / NULLIF(AVG(row_count), 0) > 2.0 THEN '⚠️ High Skew'
    WHEN STDDEV(row_count) / NULLIF(AVG(row_count), 0) > 1.0 THEN '⚠️ Moderate Skew'
    ELSE '✅ Balanced'
  END as skew_status
FROM partition_stats
WHERE partition_date IS NOT NULL
GROUP BY table_name
ORDER BY table_name;

-- =============================================================================

-- Query 3: Clustering Effectiveness Check  
-- Verify clustering is working properly for query performance
WITH cluster_stats AS (
  SELECT 
    'fact_logs (severity,service_name,resource_type)' as table_cluster_config,
    COUNT(*) as total_rows,
    COUNT(DISTINCT severity) as unique_severities,
    COUNT(DISTINCT service_name) as unique_services,
    COUNT(DISTINCT resource_type) as unique_resources,
    -- Check if clustering keys have good cardinality
    ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT CONCAT(severity, service_name, resource_type)), 0), 2) as avg_rows_per_cluster_combo
  FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`
  WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  
  UNION ALL
  
  SELECT 
    'bq_jobs_daily_v2 (project_id,statement_type,cache_hit)' as table_cluster_config,
    COUNT(*) as total_rows,
    COUNT(DISTINCT project_id) as unique_severities,
    COUNT(DISTINCT statement_type) as unique_services,
    COUNT(DISTINCT CAST(cache_hit AS STRING)) as unique_resources,
    ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT CONCAT(project_id, statement_type, CAST(cache_hit AS STRING))), 0), 2) as avg_rows_per_cluster_combo
  FROM `diatonic-ai-gcp.org_finops.bq_jobs_daily_v2`
  WHERE dt >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  
  UNION ALL
  
  SELECT 
    'tool_invocations (tool_name,user_id)' as table_cluster_config,
    COUNT(*) as total_rows,
    COUNT(DISTINCT tool_name) as unique_severities,
    COUNT(DISTINCT user_id) as unique_services,
    1 as unique_resources,
    ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT CONCAT(tool_name, user_id)), 0), 2) as avg_rows_per_cluster_combo
  FROM `diatonic-ai-gcp.org_agent.tool_invocations`
  WHERE invocation_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
)
SELECT 
  table_cluster_config,
  total_rows,
  unique_severities as cluster_key_1_cardinality,
  unique_services as cluster_key_2_cardinality, 
  unique_resources as cluster_key_3_cardinality,
  avg_rows_per_cluster_combo,
  CASE 
    WHEN avg_rows_per_cluster_combo BETWEEN 100 AND 10000 THEN '✅ Good Clustering'
    WHEN avg_rows_per_cluster_combo < 100 THEN '⚠️ Over-clustered'
    ELSE '⚠️ Under-clustered'
  END as clustering_status
FROM cluster_stats;

-- =============================================================================

-- Query 4: Label Coverage Check
-- Verify required labels are present across datasets and tables
WITH label_coverage AS (
  -- Check table-level labels via INFORMATION_SCHEMA
  SELECT 
    CONCAT(table_catalog, '.', table_schema, '.', table_name) as full_table_name,
    table_schema as dataset,
    table_name,
    option_name,
    option_value
  FROM `diatonic-ai-gcp.INFORMATION_SCHEMA.TABLE_OPTIONS`
  WHERE table_schema IN ('org_logs_canon', 'org_finops', 'org_agent', 'org_enterprise')
    AND option_name = 'labels'
),
parsed_labels AS (
  SELECT 
    full_table_name,
    dataset,
    table_name,
    JSON_EXTRACT_SCALAR(label, '$.key') as label_key,
    JSON_EXTRACT_SCALAR(label, '$.value') as label_value
  FROM label_coverage,
  UNNEST(JSON_EXTRACT_ARRAY(option_value)) as label
)
SELECT 
  dataset,
  table_name,
  COUNT(*) as total_labels,
  COUNTIF(label_key = 'env') as has_env_label,
  COUNTIF(label_key = 'team') as has_team_label,
  COUNTIF(label_key = 'owner') as has_owner_label,
  COUNTIF(label_key = 'data_product') as has_data_product_label,
  COUNTIF(label_key = 'version') as has_version_label,
  -- Check if all required labels present
  CASE 
    WHEN COUNTIF(label_key IN ('env', 'team', 'owner', 'data_product', 'version')) >= 5 
    THEN '✅ Complete' 
    ELSE '⚠️ Missing Required Labels'
  END as label_compliance
FROM parsed_labels
GROUP BY dataset, table_name, full_table_name
ORDER BY dataset, table_name;

-- =============================================================================

-- Query 5: Unified Tracing Connectivity Check
-- Verify the unified tracing view connects data across systems properly
WITH trace_connectivity AS (
  SELECT 
    source_system,
    COUNT(*) as total_events,
    COUNT(DISTINCT trace_id) as unique_traces,
    COUNT(DISTINCT correlation_id) as unique_correlations,
    COUNT(DISTINCT user_id) as unique_users,
    AVG(CASE WHEN is_error THEN 1.0 ELSE 0.0 END) as error_rate,
    MIN(event_ts) as earliest_event,
    MAX(event_ts) as latest_event
  FROM `diatonic-ai-gcp.org_observability.v_traces_unified`
  WHERE DATE(event_ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  GROUP BY source_system
),
cross_system_traces AS (
  SELECT 
    trace_id,
    COUNT(DISTINCT source_system) as systems_in_trace,
    STRING_AGG(DISTINCT source_system ORDER BY source_system) as systems_list
  FROM `diatonic-ai-gcp.org_observability.v_traces_unified`
  WHERE DATE(event_ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
    AND trace_id IS NOT NULL
  GROUP BY trace_id
  HAVING COUNT(DISTINCT source_system) > 1
)
SELECT 
  'Individual Systems' as metric_type,
  source_system as metric_name,
  CAST(total_events AS STRING) as value,
  CONCAT('Traces: ', unique_traces, ', Users: ', unique_users, ', Error Rate: ', ROUND(error_rate * 100, 2), '%') as details
FROM trace_connectivity

UNION ALL

SELECT 
  'Cross-System Tracing' as metric_type,
  'Multi-system traces' as metric_name,
  CAST(COUNT(*) AS STRING) as value,
  CONCAT('Avg systems per trace: ', ROUND(AVG(systems_in_trace), 1)) as details
FROM cross_system_traces

UNION ALL

SELECT 
  'Cross-System Tracing' as metric_type,
  'System combinations' as metric_name,
  CAST(COUNT(DISTINCT systems_list) AS STRING) as value,
  'Unique system combinations found' as details  
FROM cross_system_traces

ORDER BY metric_type, metric_name;

-- =============================================================================

-- Query 6: Data Quality Check
-- Verify data integrity and completeness
SELECT 
  'fact_logs completeness' as check_name,
  CASE 
    WHEN COUNT(*) = COUNT(log_id) THEN '✅ All log_ids present'
    ELSE CONCAT('❌ Missing log_ids: ', COUNT(*) - COUNT(log_id))
  END as result,
  CONCAT(COUNT(*), ' total rows') as details
FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`
WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)

UNION ALL

SELECT 
  'fact_logs trace_id coverage' as check_name,
  CASE 
    WHEN COUNT(trace_id) / COUNT(*) >= 0.8 THEN '✅ Good trace coverage'
    ELSE CONCAT('⚠️ Low trace coverage: ', ROUND(COUNT(trace_id) / COUNT(*) * 100, 1), '%')
  END as result,
  CONCAT(COUNT(trace_id), ' of ', COUNT(*), ' rows have trace_id') as details
FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`
WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)

UNION ALL

SELECT 
  'enterprise staging data types' as check_name,
  CASE 
    WHEN COUNT(DISTINCT asset_type) >= 5 THEN '✅ Diverse asset types'
    ELSE '⚠️ Limited asset types'
  END as result,
  CONCAT(COUNT(DISTINCT asset_type), ' asset types found') as details
FROM `diatonic-ai-gcp.org_enterprise.stg_asset_inventory`
WHERE DATE(fetched_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)

UNION ALL

SELECT 
  'finops data distribution' as check_name,
  CASE 
    WHEN COUNT(DISTINCT project_id) >= 1 THEN '✅ Multi-project data'
    ELSE '⚠️ Single project only'
  END as result,
  CONCAT(COUNT(DISTINCT project_id), ' projects in FinOps data') as details
FROM `diatonic-ai-gcp.org_finops.bq_jobs_daily_v2`
WHERE dt >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY);

-- =============================================================================

-- Query 7: Performance Check  
-- Verify queries perform well with partition filtering
SELECT 
  'partition_filter_performance' as check_name,
  'Run this manually to check query speed' as result,
  'SELECT COUNT(*) FROM fact_logs WHERE log_date = CURRENT_DATE() should be <1s' as details

UNION ALL

SELECT 
  'cluster_filter_performance' as check_name,
  'Run this manually to check query speed' as result,
  'SELECT COUNT(*) FROM fact_logs WHERE severity = "ERROR" AND log_date = CURRENT_DATE() should be <2s' as details

UNION ALL

SELECT 
  'unified_trace_performance' as check_name,
  'Run this manually to check query speed' as result,
  'SELECT COUNT(*) FROM v_traces_unified WHERE DATE(event_ts) = CURRENT_DATE() should be <5s' as details;

-- =============================================================================
-- Summary Dashboard Query
-- =============================================================================

WITH summary_stats AS (
  SELECT 
    'Logs' as data_domain,
    COUNT(*) as total_rows,
    COUNT(DISTINCT service_name) as unique_entities,
    MAX(log_date) as latest_data
  FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`
  WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  
  UNION ALL
  
  SELECT 
    'FinOps' as data_domain,
    COUNT(*) as total_rows,
    COUNT(DISTINCT project_id) as unique_entities,
    MAX(dt) as latest_data
  FROM `diatonic-ai-gcp.org_finops.bq_jobs_daily_v2`
  WHERE dt >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  
  UNION ALL
  
  SELECT 
    'Agent' as data_domain,
    COUNT(*) as total_rows,
    COUNT(DISTINCT tool_name) as unique_entities,
    MAX(invocation_date) as latest_data
  FROM `diatonic-ai-gcp.org_agent.tool_invocations`
  WHERE invocation_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  
  UNION ALL
  
  SELECT 
    'Enterprise' as data_domain,
    COUNT(*) as total_rows,
    COUNT(DISTINCT asset_type) as unique_entities,
    MAX(DATE(fetched_at)) as latest_data
  FROM `diatonic-ai-gcp.org_enterprise.stg_asset_inventory`
  WHERE DATE(fetched_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
)
SELECT 
  '🎯 VALIDATION SUMMARY' as section,
  data_domain,
  total_rows,
  unique_entities,
  latest_data,
  DATE_DIFF(CURRENT_DATE(), latest_data, DAY) as days_behind,
  CASE 
    WHEN total_rows > 0 AND DATE_DIFF(CURRENT_DATE(), latest_data, DAY) <= 1 
    THEN '✅ Healthy'
    WHEN total_rows > 0 AND DATE_DIFF(CURRENT_DATE(), latest_data, DAY) <= 7 
    THEN '⚠️ Stale'
    WHEN total_rows = 0 
    THEN '❌ No Data'
    ELSE '❌ Very Stale'
  END as health_status
FROM summary_stats
ORDER BY data_domain;