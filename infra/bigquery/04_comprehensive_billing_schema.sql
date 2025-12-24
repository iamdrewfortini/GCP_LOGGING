-- =============================================================================
-- Comprehensive Billing Schema Design
-- Purpose: Complete billing ingestion across ALL GCP services with lifecycle mgmt
-- Scope: $135 monthly spend across all services, accounts, projects
-- Archival: 1-year deep archive, 6-month hot storage, cost-efficient lifecycle
-- =============================================================================

-- -----------------------------------------------------------------------------
-- SECTION 1: Enhanced Billing Datasets with Lifecycle Management
-- -----------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS `diatonic-ai-gcp.org_finops_comprehensive`
OPTIONS (
  description = 'Comprehensive billing data across ALL GCP services with lifecycle management',
  labels = [
    ('env', 'prod'), ('team', 'finops'), ('owner', 'platform-data'),
    ('data_product', 'comprehensive-billing'), ('version', 'v3'),
    ('retention_policy', 'tiered'), ('archival_strategy', 'cost_optimized')
  ]
);

-- Real-time billing data (6 months hot storage)
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_current`
PARTITION BY usage_date
CLUSTER BY billing_account_id, service_id, project_id, sku_id
OPTIONS (
  description = 'Current billing data - 6 months hot storage',
  labels = [
    ('tier', 'hot'), ('retention_months', '6'), ('partition_type', 'daily'),
    ('data_freshness', 'realtime'), ('cost_tier', 'standard')
  ],
  partition_expiration_days = 180, -- 6 months
  require_partition_filter = TRUE
)
AS
SELECT 
  -- Core identifiers
  billing_account_id,
  service.id as service_id,
  service.description as service_name,
  sku.id as sku_id,
  sku.description as sku_description,
  project.id as project_id,
  project.name as project_name,
  
  -- Time dimensions
  DATE(usage_start_time) as usage_date,
  usage_start_time,
  usage_end_time,
  
  -- Cost and usage
  cost,
  currency,
  cost_type,
  usage.amount as usage_amount,
  usage.unit as usage_unit,
  usage.amount_in_pricing_units as usage_pricing_amount,
  pricing.effective_price,
  pricing.tier_start_amount,
  
  -- Geographic and organizational
  location.location as location,
  location.country as country,
  location.region as region,
  location.zone as zone,
  
  -- Credits and adjustments
  credits,
  adjustment_info,
  
  -- Labels and metadata
  labels,
  system_labels,
  tags,
  
  -- Attribution (Who/Why)
  invoice.month as invoice_month,
  cost_at_list,
  
  -- Tracing and lineage
  export_time,
  _PARTITIONTIME as partition_time,
  
  -- Data lineage
  'comprehensive_billing_export' as source_system,
  CURRENT_TIMESTAMP() as ingestion_timestamp,
  'v3' as schema_version

FROM `diatonic-ai-gcp.org_finops.PLACEHOLDER_FULL_BILLING_EXPORT`
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY);

-- Archived billing data (1+ year cold storage)
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_archive`
PARTITION BY archive_year
CLUSTER BY billing_account_id, service_id, cost_bucket
OPTIONS (
  description = 'Archived billing data - 1+ year cold storage with aggregation',
  labels = [
    ('tier', 'archive'), ('retention_years', '7'), ('partition_type', 'annual'),
    ('data_freshness', 'historical'), ('cost_tier', 'coldline')
  ],
  require_partition_filter = TRUE
)
AS
SELECT
  EXTRACT(YEAR FROM usage_date) as archive_year,
  EXTRACT(MONTH FROM usage_date) as archive_month,
  
  -- Aggregated identifiers (reduced granularity for cost efficiency)
  billing_account_id,
  service_id,
  service_name,
  sku_id,
  sku_description,
  project_id,
  
  -- Cost buckets for efficient querying
  CASE 
    WHEN cost < 0.01 THEN 'micro'
    WHEN cost < 1.0 THEN 'small'
    WHEN cost < 10.0 THEN 'medium'
    WHEN cost < 100.0 THEN 'large'
    ELSE 'xlarge'
  END as cost_bucket,
  
  -- Aggregated metrics
  COUNT(*) as record_count,
  SUM(cost) as total_cost,
  AVG(cost) as avg_cost,
  MAX(cost) as max_cost,
  SUM(usage_amount) as total_usage_amount,
  usage_unit,
  
  -- Geographic rollup
  country,
  region,
  
  -- Time rollup (daily -> monthly)
  MIN(usage_date) as period_start,
  MAX(usage_date) as period_end,
  
  -- Metadata
  'archived_aggregated' as source_system,
  CURRENT_TIMESTAMP() as archive_timestamp

FROM `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_current`
WHERE usage_date < DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
GROUP BY 1,2,3,4,5,6,7,8,9,usage_unit,country,region;

-- -----------------------------------------------------------------------------
-- SECTION 2: Service-Specific Cost Analysis Tables
-- -----------------------------------------------------------------------------

-- BigQuery specific costs (detailed for optimization)
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_finops_comprehensive.bigquery_costs_detailed`
PARTITION BY usage_date
CLUSTER BY project_id, user_email, query_type
OPTIONS (
  description = 'Detailed BigQuery costs with job correlation for optimization',
  partition_expiration_days = 365, -- 1 year detailed retention
  require_partition_filter = TRUE
)
AS
WITH bq_billing AS (
  SELECT * FROM `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_current`
  WHERE service_id = '24E6-581D-38E5' -- BigQuery service ID
),
bq_jobs AS (
  SELECT 
    job_id,
    DATE(creation_time) as job_date,
    project_id,
    user_email,
    statement_type,
    total_bytes_billed,
    total_slot_ms,
    cache_hit
  FROM `diatonic-ai-gcp.region-us.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
  WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
)
SELECT 
  b.usage_date,
  b.project_id,
  b.cost,
  b.usage_amount,
  b.sku_description,
  
  -- Job correlation
  j.job_id,
  j.user_email,
  j.statement_type as query_type,
  j.total_bytes_billed,
  j.total_slot_ms,
  j.cache_hit,
  
  -- Cost efficiency metrics
  CASE 
    WHEN j.total_bytes_billed > 0 
    THEN b.cost / (j.total_bytes_billed / POWER(1024, 4)) -- $/TB
    ELSE NULL 
  END as cost_per_tb,
  
  CASE 
    WHEN j.total_slot_ms > 0 
    THEN b.cost / (j.total_slot_ms / 1000) -- $/slot-second
    ELSE NULL 
  END as cost_per_slot_second,
  
  -- Attribution
  b.labels,
  CURRENT_TIMESTAMP() as analysis_timestamp

FROM bq_billing b
LEFT JOIN bq_jobs j ON b.project_id = j.project_id AND b.usage_date = j.job_date;

-- Compute Engine specific costs
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_finops_comprehensive.compute_costs_detailed`
PARTITION BY usage_date  
CLUSTER BY project_id, machine_type, zone
OPTIONS (
  description = 'Detailed Compute Engine costs with instance optimization insights',
  partition_expiration_days = 365,
  require_partition_filter = TRUE
)
AS
SELECT 
  usage_date,
  project_id,
  cost,
  usage_amount,
  usage_unit,
  sku_description,
  
  -- Extract instance details from SKU description
  REGEXP_EXTRACT(sku_description, r'(n1-|n2-|e2-|c2-|m1-|f1-|g1-)[a-z0-9-]+') as machine_type,
  REGEXP_EXTRACT(sku_description, r'running in (.+)') as zone,
  
  -- Classify cost types
  CASE 
    WHEN sku_description LIKE '%Preemptible%' THEN 'preemptible'
    WHEN sku_description LIKE '%Spot%' THEN 'spot'  
    ELSE 'standard'
  END as instance_type,
  
  CASE
    WHEN sku_description LIKE '%Core%' THEN 'cpu'
    WHEN sku_description LIKE '%Ram%' THEN 'memory'
    WHEN sku_description LIKE '%Disk%' THEN 'storage'
    WHEN sku_description LIKE '%GPU%' THEN 'gpu'
    ELSE 'other'
  END as resource_type,
  
  location,
  labels,
  CURRENT_TIMESTAMP() as analysis_timestamp

FROM `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_current`
WHERE service_name = 'Compute Engine';

-- Cloud Storage costs
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_finops_comprehensive.storage_costs_detailed`
PARTITION BY usage_date
CLUSTER BY project_id, storage_class, location
OPTIONS (
  description = 'Detailed Cloud Storage costs with bucket optimization insights',
  partition_expiration_days = 365,
  require_partition_filter = TRUE
)
AS
SELECT 
  usage_date,
  project_id,
  cost,
  usage_amount,
  usage_unit,
  sku_description,
  
  -- Extract storage details
  CASE 
    WHEN sku_description LIKE '%Standard%' THEN 'standard'
    WHEN sku_description LIKE '%Nearline%' THEN 'nearline'
    WHEN sku_description LIKE '%Coldline%' THEN 'coldline'
    WHEN sku_description LIKE '%Archive%' THEN 'archive'
    ELSE 'unknown'
  END as storage_class,
  
  CASE
    WHEN sku_description LIKE '%Storage%' THEN 'storage'
    WHEN sku_description LIKE '%Download%' OR sku_description LIKE '%Egress%' THEN 'network'
    WHEN sku_description LIKE '%Operation%' THEN 'operations'
    ELSE 'other'
  END as cost_type,
  
  location,
  region,
  labels,
  CURRENT_TIMESTAMP() as analysis_timestamp

FROM `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_current`
WHERE service_name = 'Cloud Storage';

-- -----------------------------------------------------------------------------
-- SECTION 3: Enterprise Organization & Workforce Schema
-- -----------------------------------------------------------------------------

-- Enhanced organization hierarchy with billing attribution
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.dim_organization_enhanced`
PARTITION BY effective_date
CLUSTER BY org_id, billing_account_id
OPTIONS (
  description = 'Enhanced org hierarchy with billing account mapping',
  require_partition_filter = TRUE
)
AS
SELECT 
  org_id,
  org_name,
  parent_org_id,
  billing_account_id,
  cost_center_id,
  budget_allocation,
  
  -- Hierarchy levels
  organization_level, -- enterprise, division, department, team
  reporting_hierarchy,
  
  -- Cost allocation
  cost_allocation_method, -- direct, shared, percentage
  chargeback_enabled,
  
  -- Effective dating for SCD2
  DATE(CURRENT_DATE()) as effective_date,
  CAST(NULL AS DATE) as expiration_date,
  TRUE as is_current,
  
  -- Metadata
  CURRENT_TIMESTAMP() as created_at,
  'org_management' as source_system

FROM (
  -- This would be populated from your org management system
  SELECT 'ORG001' as org_id, 'Diatonic AI' as org_name, NULL as parent_org_id,
         '018EE0-B71384-D44551' as billing_account_id, 'CC001' as cost_center_id,
         1000000.00 as budget_allocation, 'enterprise' as organization_level,
         'CEO > CTO > Engineering' as reporting_hierarchy, 'direct' as cost_allocation_method,
         TRUE as chargeback_enabled
);

-- Workforce billing attribution
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.org_enterprise.workforce_cost_attribution`
PARTITION BY attribution_date
CLUSTER BY member_id, project_id, service_id
OPTIONS (
  description = 'Workforce cost attribution for chargeback and analysis',
  partition_expiration_days = 1095, -- 3 years
  require_partition_filter = TRUE
)
AS
SELECT 
  DATE(CURRENT_DATE()) as attribution_date,
  member_id,
  email,
  project_id,
  service_id,
  
  -- Cost attribution
  direct_cost, -- costs directly attributable to user
  allocated_cost, -- shared costs allocated to user
  total_attributed_cost,
  attribution_method,
  
  -- Usage attribution
  resource_hours_used,
  storage_gb_used,
  compute_units_used,
  
  -- Time tracking
  hours_logged,
  project_percentage,
  
  -- Metadata
  cost_center_id,
  manager_id,
  CURRENT_TIMESTAMP() as calculated_at

FROM (
  -- This would be populated from time tracking + billing correlation
  SELECT 'USER001' as member_id, 'drew@dacvisuals.com' as email,
         'diatonic-ai-gcp' as project_id, '24E6-581D-38E5' as service_id,
         45.50 as direct_cost, 12.25 as allocated_cost, 57.75 as total_attributed_cost,
         'time_based' as attribution_method, 160.0 as resource_hours_used,
         25.5 as storage_gb_used, 450.0 as compute_units_used,
         40.0 as hours_logged, 0.75 as project_percentage,
         'CC001' as cost_center_id, 'MGR001' as manager_id
);

-- -----------------------------------------------------------------------------
-- SECTION 4: Unified Cost Analysis Views
-- -----------------------------------------------------------------------------

-- Comprehensive cost dashboard view
CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_finops_comprehensive.v_cost_dashboard`
OPTIONS (
  description = 'Unified cost dashboard across all services with 5W+1H attribution'
)
AS
WITH daily_costs AS (
  SELECT 
    usage_date,
    billing_account_id,
    service_name,
    project_id,
    SUM(cost) as daily_cost,
    COUNT(*) as line_items,
    STRING_AGG(DISTINCT sku_description LIMIT 5) as top_skus
  FROM `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_current`
  GROUP BY 1,2,3,4
),
workforce_attribution AS (
  SELECT 
    attribution_date,
    project_id,
    SUM(total_attributed_cost) as workforce_attributed_cost,
    COUNT(DISTINCT member_id) as active_members
  FROM `diatonic-ai-gcp.org_enterprise.workforce_cost_attribution`
  GROUP BY 1,2
)
SELECT 
  -- WHO: User/Team attribution
  COALESCE(w.active_members, 0) as who_active_members,
  
  -- WHAT: Services and resources
  d.service_name as what_service,
  d.top_skus as what_resources,
  
  -- WHERE: Geographic and project location  
  d.project_id as where_project,
  d.billing_account_id as where_billing_account,
  
  -- WHEN: Time dimensions
  d.usage_date as when_date,
  EXTRACT(DAYOFWEEK FROM d.usage_date) as when_day_of_week,
  EXTRACT(HOUR FROM CURRENT_TIMESTAMP()) as when_hour,
  
  -- WHY: Cost center and purpose (from org hierarchy)
  'operational' as why_purpose, -- Would be enriched from org data
  
  -- HOW: Cost efficiency and attribution
  d.daily_cost as how_much_cost,
  COALESCE(w.workforce_attributed_cost, 0) as how_much_attributed,
  d.daily_cost - COALESCE(w.workforce_attributed_cost, 0) as how_much_unattributed,
  d.line_items as how_many_line_items,
  
  -- Efficiency metrics
  CASE 
    WHEN d.daily_cost > 0 AND COALESCE(w.workforce_attributed_cost, 0) > 0 
    THEN COALESCE(w.workforce_attributed_cost, 0) / d.daily_cost 
    ELSE 0 
  END as attribution_efficiency,
  
  -- Time aggregations
  DATE_TRUNC(d.usage_date, WEEK) as week_start,
  DATE_TRUNC(d.usage_date, MONTH) as month_start

FROM daily_costs d
LEFT JOIN workforce_attribution w 
  ON d.usage_date = w.attribution_date 
  AND d.project_id = w.project_id
WHERE d.usage_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY);

-- -----------------------------------------------------------------------------
-- SECTION 5: Data Lifecycle Management Procedures
-- -----------------------------------------------------------------------------

-- Archival procedure (run monthly)
CREATE OR REPLACE PROCEDURE `diatonic-ai-gcp.org_finops_comprehensive.sp_archive_billing_data`()
BEGIN
  -- Move data older than 6 months to archive with aggregation
  INSERT INTO `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_archive`
  SELECT 
    EXTRACT(YEAR FROM usage_date) as archive_year,
    EXTRACT(MONTH FROM usage_date) as archive_month,
    billing_account_id,
    service_id,
    service_name,
    sku_id,
    sku_description,
    project_id,
    CASE 
      WHEN cost < 0.01 THEN 'micro'
      WHEN cost < 1.0 THEN 'small'  
      WHEN cost < 10.0 THEN 'medium'
      WHEN cost < 100.0 THEN 'large'
      ELSE 'xlarge'
    END as cost_bucket,
    COUNT(*) as record_count,
    SUM(cost) as total_cost,
    AVG(cost) as avg_cost,
    MAX(cost) as max_cost,
    SUM(usage_amount) as total_usage_amount,
    usage_unit,
    country,
    region,
    MIN(usage_date) as period_start,
    MAX(usage_date) as period_end,
    'archived_aggregated' as source_system,
    CURRENT_TIMESTAMP() as archive_timestamp
  FROM `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_current`
  WHERE usage_date < DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
    AND usage_date NOT IN (
      SELECT period_start FROM `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_archive`
    )
  GROUP BY 1,2,3,4,5,6,7,8,9,usage_unit,country,region;
  
  -- Archive workforce data
  INSERT INTO `diatonic-ai-gcp.org_enterprise.workforce_cost_attribution_archive`
  SELECT * FROM `diatonic-ai-gcp.org_enterprise.workforce_cost_attribution`
  WHERE attribution_date < DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY);
  
END;

-- Cost optimization recommendations view
CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_finops_comprehensive.v_cost_optimization_recommendations`
AS
WITH cost_trends AS (
  SELECT 
    service_name,
    project_id,
    AVG(cost) as avg_daily_cost,
    STDDEV(cost) as cost_volatility,
    COUNT(DISTINCT usage_date) as active_days
  FROM `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_current`
  WHERE usage_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  GROUP BY 1,2
)
SELECT 
  service_name,
  project_id,
  avg_daily_cost,
  avg_daily_cost * 30 as projected_monthly_cost,
  
  -- Optimization recommendations
  CASE 
    WHEN service_name = 'Compute Engine' AND avg_daily_cost > 10 
    THEN 'Consider preemptible instances for non-critical workloads'
    WHEN service_name = 'Cloud Storage' AND cost_volatility > avg_daily_cost * 0.5
    THEN 'Review storage class optimization for lifecycle management'
    WHEN service_name = 'BigQuery' AND avg_daily_cost > 5
    THEN 'Implement slot reservations for predictable workloads'
    ELSE 'Monitor usage patterns'
  END as optimization_recommendation,
  
  CASE 
    WHEN avg_daily_cost > 20 THEN 'high'
    WHEN avg_daily_cost > 5 THEN 'medium'
    ELSE 'low'
  END as cost_priority,
  
  cost_volatility,
  active_days

FROM cost_trends
WHERE avg_daily_cost > 0.10 -- Focus on meaningful costs
ORDER BY avg_daily_cost DESC;