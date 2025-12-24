#!/bin/bash
# refresh_real_billing.sh
# Automated script to refresh real BigQuery billing data from INFORMATION_SCHEMA

set -e

echo "🔄 Refreshing Real BigQuery Billing Data"
echo "========================================"

# Configuration
PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"
DATASET_ID="org_finops"
TABLE_ID="bq_jobs_daily_v2"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}!${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

echo "📊 Extracting real BigQuery job data from INFORMATION_SCHEMA..."

# Run the extraction query
bq query --use_legacy_sql=false < scripts/extract_real_billing_data.sql

if [ $? -eq 0 ]; then
    log_info "Real billing data refresh completed"
    
    # Get summary stats
    echo ""
    echo "📈 Summary of refreshed data:"
    bq query --use_legacy_sql=false --format=table \
        "SELECT 
           dt,
           COUNT(*) as jobs,
           ROUND(SUM(cost_usd), 4) as daily_cost_usd,
           ROUND(SUM(total_bytes_processed)/POWER(1024,3), 2) as gb_processed
         FROM \`$PROJECT_ID.$DATASET_ID.$TABLE_ID\`
         WHERE dt >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
         GROUP BY dt
         ORDER BY dt DESC
         LIMIT 7"
    
    log_info "✅ Real billing data refresh successful!"
    
    echo ""
    echo "🔗 Next steps:"
    echo "  - Data is automatically refreshed from BigQuery INFORMATION_SCHEMA"
    echo "  - Run this script daily via cron: 0 2 * * * /path/to/refresh_real_billing.sh"
    echo "  - Monitor costs: SELECT SUM(cost_usd) FROM \`$PROJECT_ID.$DATASET_ID.$TABLE_ID\` WHERE dt = CURRENT_DATE()"
else
    log_error "Failed to refresh billing data"
    exit 1
fi