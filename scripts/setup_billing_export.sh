#!/bin/bash
# setup_billing_export.sh
# Enable BigQuery billing export to populate org_finops dataset

set -e

echo "💰 Setting up BigQuery Billing Export"
echo "====================================="

# Configuration
PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"
DATASET_ID="org_finops"
TABLE_ID="bq_billing_export"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}!${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

# Check prerequisites
echo "🔍 Checking prerequisites..."

if ! command -v gcloud &> /dev/null; then
    log_error "gcloud CLI not installed"
    exit 1
fi

# Check if authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    log_error "Not authenticated. Run: gcloud auth login"
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID
log_info "Using project: $PROJECT_ID"

# Check if billing is enabled
echo ""
echo "💳 Checking billing configuration..."

BILLING_ACCOUNT=$(gcloud billing projects describe $PROJECT_ID --format="value(billingAccountName)" 2>/dev/null || echo "")

if [ -z "$BILLING_ACCOUNT" ]; then
    log_error "No billing account linked to project $PROJECT_ID"
    echo "   Please link a billing account first:"
    echo "   1. Go to: https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID"
    echo "   2. Or run: gcloud billing projects link $PROJECT_ID --billing-account=BILLING_ACCOUNT_ID"
    exit 1
else
    log_info "Billing account linked: $BILLING_ACCOUNT"
fi

# Ensure BigQuery API is enabled
echo ""
echo "🔧 Enabling required APIs..."

gcloud services enable bigquery.googleapis.com cloudbilling.googleapis.com
log_info "BigQuery and Cloud Billing APIs enabled"

# Create or verify dataset
echo ""
echo "📊 Setting up BigQuery dataset..."

if bq show $PROJECT_ID:$DATASET_ID &>/dev/null; then
    log_info "Dataset $DATASET_ID already exists"
else
    bq mk --location=US --description="FinOps billing and cost data" \
       --label=team:finops \
       --label=env:prod \
       --label=data_product:billing \
       $PROJECT_ID:$DATASET_ID
    log_info "Created dataset $DATASET_ID"
fi

# Set up billing export
echo ""
echo "💾 Configuring billing export..."

BILLING_ACCOUNT_ID=$(echo $BILLING_ACCOUNT | sed 's/.*\///')

# Check if export already exists
EXISTING_EXPORTS=$(gcloud billing accounts get-iam-policy $BILLING_ACCOUNT_ID --format="value(bindings[].members)" 2>/dev/null | grep -c "bigquery-$PROJECT_ID" || echo "0")

if [ "$EXISTING_EXPORTS" -gt 0 ]; then
    log_warn "Billing export may already be configured"
else
    log_info "Setting up new billing export..."
fi

# Instructions for manual setup (some parts require Console)
cat << EOF

📋 MANUAL SETUP REQUIRED
========================

The billing export setup requires Console access. Please complete these steps:

1. 📊 Set up BigQuery export:
   URL: https://console.cloud.google.com/billing/$BILLING_ACCOUNT_ID/export

2. ⚙️ Configure the export:
   - Export type: BigQuery export
   - Projects: Select '$PROJECT_ID'
   - BigQuery dataset: '$DATASET_ID'
   - Table name: '$TABLE_ID'

3. 🎯 Export options:
   - ✅ Enable detailed usage cost export
   - ✅ Enable pricing export
   - ✅ Include credits and promotions

4. ⏱️ Data timeline:
   - Export starts from configuration date
   - Historical data: Limited (usually 1-2 months)
   - Full data available: 24-48 hours after setup

5. 🔍 Verification:
   After 24-48 hours, run:
   bq query "SELECT COUNT(*) FROM \`$PROJECT_ID.$DATASET_ID.$TABLE_ID\` WHERE _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)"

EOF

# Create monitoring script
cat > scripts/monitor_billing_export.sh << 'MONITOR_EOF'
#!/bin/bash
# Monitor billing export data arrival

PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"
DATASET_ID="org_finops"
TABLE_ID="bq_billing_export"

echo "📊 Billing Export Monitor"
echo "========================"

# Check if table exists
if bq show $PROJECT_ID:$DATASET_ID.$TABLE_ID &>/dev/null; then
    echo "✓ Export table exists"
    
    # Check recent data
    RECENT_ROWS=$(bq query --use_legacy_sql=false --format=csv \
        "SELECT COUNT(*) FROM \`$PROJECT_ID.$DATASET_ID.$TABLE_ID\` 
         WHERE _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)" 2>/dev/null | tail -1)
    
    echo "Recent rows (last 7 days): $RECENT_ROWS"
    
    if [ "$RECENT_ROWS" -gt 0 ]; then
        echo "✅ Billing data is flowing!"
        
        # Show sample data
        echo ""
        echo "Sample data:"
        bq query --use_legacy_sql=false --max_rows=5 \
            "SELECT service.description, sku.description, cost, currency, usage_start_time
             FROM \`$PROJECT_ID.$DATASET_ID.$TABLE_ID\`
             WHERE _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
             ORDER BY usage_start_time DESC
             LIMIT 5"
    else
        echo "⚠️ No recent billing data found"
        echo "   - Check if export is configured correctly"
        echo "   - Wait 24-48 hours for data to appear"
    fi
else
    echo "⚠️ Billing export table not found"
    echo "   Complete the manual setup steps first"
fi
MONITOR_EOF

chmod +x scripts/monitor_billing_export.sh

# Create transformation script to populate bq_jobs_daily_v2
cat > scripts/transform_billing_to_finops.sql << 'TRANSFORM_EOF'
-- Transform billing export data to match bq_jobs_daily_v2 schema
-- Run this daily to populate org_finops.bq_jobs_daily_v2

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
  COALESCE(labels.value, 'unknown') as statement_type,
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
  service.description = 'BigQuery'
  AND DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND cost > 0;
TRANSFORM_EOF

log_info "Created monitoring and transformation scripts"

echo ""
echo "🎯 NEXT STEPS:"
echo "1. Complete manual billing export setup (see instructions above)"
echo "2. Wait 24-48 hours for data to populate"
echo "3. Run: ./scripts/monitor_billing_export.sh"
echo "4. Execute transformation: bq query < scripts/transform_billing_to_finops.sql"
echo ""
echo "✅ Billing export setup preparation complete!"