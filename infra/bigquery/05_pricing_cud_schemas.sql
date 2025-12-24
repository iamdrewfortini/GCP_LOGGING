-- =============================================================================
-- Pricing and CUD Export Schemas
-- Purpose: Schema definitions for pricing data and committed use discounts
-- Service Account: billing-export-service@diatonic-ai-gcp.iam.gserviceaccount.com
-- =============================================================================

-- -----------------------------------------------------------------------------
-- SECTION 1: Pricing Data Schema
-- -----------------------------------------------------------------------------

-- Create pricing table for SKU price data
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.billing_pricing.cloud_pricing_export`
(
  -- Core identifiers
  service_id STRING NOT NULL,
  service_display_name STRING,
  sku_id STRING NOT NULL,
  sku_description STRING,
  
  -- Geographic information
  service_region STRING,
  pricing_location STRING,
  
  -- Pricing details
  currency_code STRING NOT NULL,
  usage_unit STRING,
  usage_unit_description STRING,
  
  -- Tiered pricing structure
  pricing_info ARRAY<STRUCT<
    summary STRING,
    pricing_expression STRUCT<
      usage_unit STRING,
      usage_unit_description STRING,
      base_unit STRING,
      base_unit_description STRING,
      base_unit_conversion_factor FLOAT64,
      display_quantity FLOAT64,
      tiered_rates ARRAY<STRUCT<
        start_usage_amount FLOAT64,
        unit_price STRUCT<
          currency_code STRING,
          units STRING,
          nanos INT64
        >
      >>
    >,
    aggregation_info STRUCT<
      aggregation_level STRING,
      aggregation_interval STRING,
      aggregation_count INT64
    >,
    currency_conversion_rate FLOAT64,
    effective_time TIMESTAMP
  >>,
  
  -- Metadata
  export_time TIMESTAMP,
  last_updated_time TIMESTAMP,
  
  -- Data lineage
  source_system STRING DEFAULT 'cloud_billing_pricing_export',
  ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  schema_version STRING DEFAULT 'v1'
)
PARTITION BY DATE(export_time)
CLUSTER BY service_id, sku_id, pricing_location, currency_code
OPTIONS (
  description = 'Cloud Billing pricing data export for SKU price tracking',
  labels = [
    ('team', 'finops'), ('owner', 'billing-export-service'),
    ('data_product', 'pricing'), ('version', 'v1'),
    ('retention_policy', 'standard'), ('cost_tier', 'standard')
  ],
  partition_expiration_days = 730, -- 2 years
  require_partition_filter = TRUE
);

-- -----------------------------------------------------------------------------
-- SECTION 2: Committed Use Discounts (CUD) Schema  
-- -----------------------------------------------------------------------------

-- Create CUD table for discount tracking
CREATE TABLE IF NOT EXISTS `diatonic-ai-gcp.billing_cud.cloud_cud_export`
(
  -- Core identifiers
  billing_account_id STRING NOT NULL,
  project_id STRING,
  project_name STRING,
  
  -- Commitment details
  commitment_id STRING NOT NULL,
  commitment_name STRING,
  commitment_type STRING, -- COMPUTE_OPTIMIZED_C3, GENERAL_PURPOSE_E2, etc.
  commitment_plan STRING, -- 1_YEAR, 3_YEAR
  commitment_status STRING, -- ACTIVE, EXPIRED, etc.
  
  -- Usage period
  usage_date DATE NOT NULL,
  usage_start_time TIMESTAMP,
  usage_end_time TIMESTAMP,
  
  -- Resource details
  service_id STRING,
  service_description STRING,
  sku_id STRING,
  sku_description STRING,
  resource_name STRING,
  resource_location STRING,
  
  -- Commitment metrics
  commitment_cost FLOAT64,
  commitment_cost_currency STRING,
  usage_amount FLOAT64,
  usage_unit STRING,
  coverage_percentage FLOAT64,
  
  -- Discount calculations
  list_cost FLOAT64,
  discount_amount FLOAT64,
  discount_percentage FLOAT64,
  net_cost FLOAT64,
  
  -- Commitment lifecycle
  commitment_start_date DATE,
  commitment_end_date DATE,
  commitment_remaining_amount FLOAT64,
  commitment_utilization_percentage FLOAT64,
  
  -- Labels and attribution
  labels ARRAY<STRUCT<
    key STRING,
    value STRING
  >>,
  
  -- Metadata
  export_time TIMESTAMP,
  
  -- Data lineage
  source_system STRING DEFAULT 'cloud_billing_cud_export',
  ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  schema_version STRING DEFAULT 'v1'
)
PARTITION BY usage_date
CLUSTER BY billing_account_id, commitment_id, project_id, service_id
OPTIONS (
  description = 'Cloud Billing committed use discounts export for cost optimization',
  labels = [
    ('team', 'finops'), ('owner', 'billing-export-service'),
    ('data_product', 'cud'), ('version', 'v1'),
    ('retention_policy', 'extended'), ('cost_tier', 'standard')
  ],
  partition_expiration_days = 1095, -- 3 years (CUD lifecycle)
  require_partition_filter = TRUE
);

-- -----------------------------------------------------------------------------
-- SECTION 3: Integration Views
-- -----------------------------------------------------------------------------

-- Comprehensive pricing analysis view
CREATE OR REPLACE VIEW `diatonic-ai-gcp.billing_pricing.v_pricing_analysis`
OPTIONS (
  description = 'Comprehensive pricing analysis across SKUs and regions'
)
AS
SELECT 
  service_id,
  service_display_name,
  sku_id,
  sku_description,
  service_region,
  pricing_location,
  currency_code,
  usage_unit,
  
  -- Extract current pricing (latest pricing info)
  (SELECT p.pricing_expression.tiered_rates[OFFSET(0)].unit_price.units 
   FROM UNNEST(pricing_info) AS p 
   ORDER BY p.effective_time DESC LIMIT 1) AS current_base_price_units,
  
  (SELECT p.pricing_expression.tiered_rates[OFFSET(0)].unit_price.nanos 
   FROM UNNEST(pricing_info) AS p 
   ORDER BY p.effective_time DESC LIMIT 1) AS current_base_price_nanos,
  
  -- Calculate effective price per unit
  (SELECT 
     CAST(p.pricing_expression.tiered_rates[OFFSET(0)].unit_price.units AS FLOAT64) + 
     (CAST(p.pricing_expression.tiered_rates[OFFSET(0)].unit_price.nanos AS FLOAT64) / 1000000000)
   FROM UNNEST(pricing_info) AS p 
   ORDER BY p.effective_time DESC LIMIT 1) AS effective_price_per_unit,
  
  -- Latest update info
  MAX(last_updated_time) as latest_price_update,
  COUNT(*) as pricing_tiers_count,
  
  export_time,
  ingestion_timestamp

FROM `diatonic-ai-gcp.billing_pricing.cloud_pricing_export`
WHERE DATE(export_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 
  service_id, service_display_name, sku_id, sku_description,
  service_region, pricing_location, currency_code, usage_unit,
  pricing_info, export_time, ingestion_timestamp;

-- CUD utilization analysis view  
CREATE OR REPLACE VIEW `diatonic-ai-gcp.billing_cud.v_cud_utilization`
OPTIONS (
  description = 'CUD utilization analysis for optimization recommendations'
)
AS
SELECT 
  billing_account_id,
  commitment_id,
  commitment_name,
  commitment_type,
  commitment_plan,
  commitment_status,
  
  -- Current period metrics
  DATE_TRUNC(usage_date, MONTH) as usage_month,
  COUNT(*) as usage_days,
  SUM(commitment_cost) as total_commitment_cost,
  SUM(usage_amount) as total_usage_amount,
  AVG(coverage_percentage) as avg_coverage_percentage,
  
  -- Discount impact
  SUM(list_cost) as total_list_cost,
  SUM(discount_amount) as total_discount_amount,
  SUM(net_cost) as total_net_cost,
  SAFE_DIVIDE(SUM(discount_amount), SUM(list_cost)) * 100 as overall_discount_percentage,
  
  -- Utilization metrics
  AVG(commitment_utilization_percentage) as avg_utilization_percentage,
  MIN(commitment_utilization_percentage) as min_utilization_percentage,
  MAX(commitment_utilization_percentage) as max_utilization_percentage,
  
  -- Commitment lifecycle
  MIN(commitment_start_date) as commitment_start_date,
  MAX(commitment_end_date) as commitment_end_date,
  DATE_DIFF(MAX(commitment_end_date), CURRENT_DATE(), DAY) as days_until_expiry,
  
  -- Optimization indicators
  CASE 
    WHEN AVG(commitment_utilization_percentage) < 50 THEN 'UNDER_UTILIZED'
    WHEN AVG(commitment_utilization_percentage) < 80 THEN 'MODERATE'
    WHEN AVG(commitment_utilization_percentage) < 95 THEN 'WELL_UTILIZED'
    ELSE 'OVER_UTILIZED'
  END as utilization_status,
  
  MAX(ingestion_timestamp) as latest_update

FROM `diatonic-ai-gcp.billing_cud.cloud_cud_export`
WHERE usage_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND commitment_status = 'ACTIVE'
GROUP BY 
  billing_account_id, commitment_id, commitment_name, 
  commitment_type, commitment_plan, commitment_status,
  DATE_TRUNC(usage_date, MONTH)
ORDER BY usage_month DESC, total_discount_amount DESC;

-- -----------------------------------------------------------------------------
-- SECTION 4: Integration with Comprehensive Billing
-- -----------------------------------------------------------------------------

-- Enhanced cost analysis with pricing and CUD integration
CREATE OR REPLACE VIEW `diatonic-ai-gcp.org_finops_comprehensive.v_enhanced_cost_analysis`
OPTIONS (
  description = 'Enhanced cost analysis integrating billing, pricing, and CUD data'
)
AS
WITH billing_base AS (
  SELECT 
    billing_account_id,
    service_id,
    service_name,
    sku_id,
    sku_description,
    project_id,
    usage_date,
    usage_amount,
    usage_unit,
    cost,
    currency,
    location,
    labels
  FROM `diatonic-ai-gcp.org_finops_comprehensive.billing_detailed_current`
  WHERE usage_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
),
pricing_context AS (
  SELECT 
    service_id,
    sku_id,
    pricing_location,
    effective_price_per_unit,
    latest_price_update
  FROM `diatonic-ai-gcp.billing_pricing.v_pricing_analysis`
),
cud_benefits AS (
  SELECT 
    billing_account_id,
    project_id,
    service_id,
    sku_id,
    usage_date,
    SUM(discount_amount) as cud_discount_amount,
    AVG(coverage_percentage) as cud_coverage_percentage
  FROM `diatonic-ai-gcp.billing_cud.cloud_cud_export`
  WHERE usage_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  GROUP BY billing_account_id, project_id, service_id, sku_id, usage_date
)
SELECT 
  b.billing_account_id,
  b.service_name,
  b.sku_description,
  b.project_id,
  b.usage_date,
  
  -- Usage and cost metrics
  b.usage_amount,
  b.usage_unit,
  b.cost as actual_cost,
  b.currency,
  
  -- Pricing context
  p.effective_price_per_unit,
  CASE 
    WHEN p.effective_price_per_unit IS NOT NULL AND b.usage_amount > 0
    THEN b.usage_amount * p.effective_price_per_unit
    ELSE NULL
  END as calculated_list_cost,
  
  -- CUD benefits
  COALESCE(c.cud_discount_amount, 0) as cud_discount_applied,
  COALESCE(c.cud_coverage_percentage, 0) as cud_coverage_percentage,
  
  -- Cost efficiency metrics
  CASE 
    WHEN p.effective_price_per_unit IS NOT NULL AND b.usage_amount > 0
    THEN (b.cost - COALESCE(c.cud_discount_amount, 0)) / (b.usage_amount * p.effective_price_per_unit) * 100
    ELSE NULL
  END as cost_efficiency_percentage,
  
  -- Optimization indicators
  CASE 
    WHEN COALESCE(c.cud_coverage_percentage, 0) = 0 THEN 'NO_CUD_COVERAGE'
    WHEN COALESCE(c.cud_coverage_percentage, 0) < 50 THEN 'LOW_CUD_COVERAGE'
    WHEN COALESCE(c.cud_coverage_percentage, 0) < 80 THEN 'MODERATE_CUD_COVERAGE'
    ELSE 'HIGH_CUD_COVERAGE'
  END as cud_optimization_status,
  
  b.location,
  b.labels,
  CURRENT_TIMESTAMP() as analysis_timestamp

FROM billing_base b
LEFT JOIN pricing_context p 
  ON b.service_id = p.service_id 
  AND b.sku_id = p.sku_id
  AND (p.pricing_location = b.location OR p.pricing_location IS NULL)
LEFT JOIN cud_benefits c
  ON b.billing_account_id = c.billing_account_id
  AND b.project_id = c.project_id
  AND b.service_id = c.service_id
  AND b.sku_id = c.sku_id
  AND b.usage_date = c.usage_date

WHERE b.cost > 0.001 -- Filter out negligible costs
ORDER BY b.usage_date DESC, b.cost DESC;