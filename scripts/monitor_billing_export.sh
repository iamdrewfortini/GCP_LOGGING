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
