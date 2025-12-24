#!/bin/bash
# =============================================================================
# Comprehensive Billing System Status Verification
# =============================================================================

set -euo pipefail

PROJECT_ID="diatonic-ai-gcp"
FUNCTION_NAME="comprehensive-billing-ingest"
REGION="us-central1"
BILLING_ACCOUNT="018EE0-B71384-D44551"

echo "🔍 COMPREHENSIVE BILLING SYSTEM STATUS"
echo "======================================"
echo

# Check function status
echo "📦 CLOUD FUNCTION STATUS:"
FUNCTION_STATUS=$(gcloud functions describe "$FUNCTION_NAME" --region="$REGION" --format="value(state)" 2>/dev/null || echo "NOT_FOUND")
FUNCTION_URL=$(gcloud functions describe "$FUNCTION_NAME" --region="$REGION" --format="value(serviceConfig.uri)" 2>/dev/null || echo "UNKNOWN")

if [[ "$FUNCTION_STATUS" == "ACTIVE" ]]; then
    echo "   ✅ Function: $FUNCTION_NAME ($FUNCTION_STATUS)"
    echo "   🔗 URL: $FUNCTION_URL"
else
    echo "   ❌ Function: $FUNCTION_NAME ($FUNCTION_STATUS)"
fi

# Check scheduler status
echo
echo "⏰ SCHEDULER STATUS:"
SCHEDULER_STATUS=$(gcloud scheduler jobs describe "$FUNCTION_NAME-daily" --location="$REGION" --format="value(state)" 2>/dev/null || echo "NOT_FOUND")
if [[ "$SCHEDULER_STATUS" == "ENABLED" ]]; then
    echo "   ✅ Daily Schedule: $SCHEDULER_STATUS (6 AM EST)"
    NEXT_RUN=$(gcloud scheduler jobs describe "$FUNCTION_NAME-daily" --location="$REGION" --format="value(scheduleTime)" 2>/dev/null || echo "UNKNOWN")
    echo "   📅 Next Run: $NEXT_RUN"
else
    echo "   ❌ Daily Schedule: $SCHEDULER_STATUS"
fi

# Check BigQuery dataset
echo
echo "🗃️  BIGQUERY DATASET STATUS:"
DATASET_EXISTS=$(bq ls -d 2>/dev/null | grep "org_finops_comprehensive" || echo "")
if [[ -n "$DATASET_EXISTS" ]]; then
    echo "   ✅ Dataset: org_finops_comprehensive exists"
    
    # Check tables
    TABLE_COUNT=$(bq ls org_finops_comprehensive 2>/dev/null | grep -c "TABLE" || echo "0")
    echo "   📊 Tables: $TABLE_COUNT created"
    
    # Check current data
    RECORD_COUNT=$(bq query --use_legacy_sql=false --format=csv --quiet "SELECT COUNT(*) as count FROM \`$PROJECT_ID.org_finops_comprehensive.billing_detailed_current\`" 2>/dev/null | tail -1 || echo "0")
    echo "   📈 Current Records: $RECORD_COUNT"
    
else
    echo "   ❌ Dataset: org_finops_comprehensive not found"
fi

# Check IAM permissions
echo
echo "🔐 IAM PERMISSIONS STATUS:"
BILLING_PERM=$(gcloud beta billing accounts get-iam-policy "$BILLING_ACCOUNT" 2>/dev/null | grep -A1 "role: roles/billing.viewer" | grep "serviceAccount:$PROJECT_ID@appspot.gserviceaccount.com" || echo "")
if [[ -n "$BILLING_PERM" ]]; then
    echo "   ✅ Billing Account Access: Configured"
else
    echo "   ❌ Billing Account Access: Not configured"
fi

# Test function
echo
echo "🧪 FUNCTION TEST:"
echo "   Testing function with 1-day fetch..."
FUNCTION_TEST=$(curl -s -X POST "$FUNCTION_URL" \
    -H "Content-Type: application/json" \
    -d '{"days_to_fetch": 1}' \
    -w "%{http_code}" -o /tmp/function_response.json)

if [[ "$FUNCTION_TEST" == "200" ]]; then
    echo "   ✅ Function Test: PASSED (HTTP 200)"
    RECORDS_PROCESSED=$(cat /tmp/function_response.json | grep -o '"total_records":[0-9]*' | grep -o '[0-9]*' || echo "0")
    echo "   📊 Records Processed: $RECORDS_PROCESSED"
else
    echo "   ❌ Function Test: FAILED (HTTP $FUNCTION_TEST)"
fi

# Check for billing export
echo
echo "💰 BILLING EXPORT STATUS:"
EXPORT_EXISTS=$(bq ls -d 2>/dev/null | grep "billing_export" || echo "")
if [[ -n "$EXPORT_EXISTS" ]]; then
    echo "   ✅ Billing Export Dataset: Exists"
    
    # Check for actual export table
    EXPORT_TABLE=$(bq ls billing_export 2>/dev/null | grep "gcp_billing_export_018EE0_B71384_D44551" || echo "")
    if [[ -n "$EXPORT_TABLE" ]]; then
        echo "   ✅ Export Table: Ready"
        
        # Check data volume
        EXPORT_RECORDS=$(bq query --use_legacy_sql=false --format=csv --quiet "SELECT COUNT(*) FROM \`$PROJECT_ID.billing_export.gcp_billing_export_018EE0_B71384_D44551\`" 2>/dev/null | tail -1 || echo "0")
        echo "   📈 Export Records: $EXPORT_RECORDS"
    else
        echo "   ⏳ Export Table: Not created yet (need manual setup)"
    fi
else
    echo "   ⏳ Billing Export Dataset: Manual setup required"
fi

# Summary
echo
echo "🎯 SYSTEM SUMMARY:"
if [[ "$FUNCTION_STATUS" == "ACTIVE" && "$SCHEDULER_STATUS" == "ENABLED" && -n "$DATASET_EXISTS" ]]; then
    echo "   ✅ Core System: DEPLOYED & READY"
    
    if [[ -n "$EXPORT_EXISTS" ]]; then
        echo "   ✅ Billing Export: CONFIGURED"
        echo "   🚀 Status: FULLY OPERATIONAL"
    else
        echo "   ⏳ Billing Export: MANUAL SETUP REQUIRED"
        echo "   🎯 Status: READY FOR DATA (pending export setup)"
    fi
else
    echo "   ❌ Core System: INCOMPLETE"
    echo "   🛠️  Status: NEEDS TROUBLESHOOTING"
fi

echo
echo "📋 NEXT STEPS:"
if [[ -z "$EXPORT_EXISTS" ]]; then
    echo "   1. 🔧 Set up billing export (CRITICAL):"
    echo "      URL: https://console.cloud.google.com/billing/$BILLING_ACCOUNT"
    echo "      Action: Enable BigQuery export to $PROJECT_ID.billing_export"
    echo
    echo "   2. ⏱️  Wait 24 hours for first data"
    echo
    echo "   3. 🔍 Verify full cost capture:"
    echo "      Target: \$135/month across all services"
else
    echo "   1. ✅ System fully deployed"
    echo "   2. 📊 Monitor daily ingestion at 6 AM EST"
    echo "   3. 📈 Analyze cost dashboard for full \$135/month visibility"
fi

echo
echo "📊 MONITORING COMMANDS:"
echo "   Function Logs: gcloud functions logs read $FUNCTION_NAME --region=$REGION --limit=50"
echo "   Cost Dashboard: bq query --use_legacy_sql=false 'SELECT * FROM \`$PROJECT_ID.org_finops_comprehensive.v_cost_dashboard\` LIMIT 10'"
echo "   Data Validation: bq query --use_legacy_sql=false 'SELECT service_name, SUM(cost) as total_cost FROM \`$PROJECT_ID.org_finops_comprehensive.billing_detailed_current\` GROUP BY service_name ORDER BY total_cost DESC'"

rm -f /tmp/function_response.json 2>/dev/null || true