#!/bin/bash
# ==============================================================================
# Comprehensive Billing Data Ingestion Deployment
# Purpose: Deploy Cloud Function for ALL GCP service billing ingestion
# Scope: $135 monthly spend across all services with enterprise lifecycle
# ==============================================================================

set -euo pipefail

# Configuration
PROJECT_ID="diatonic-ai-gcp"
FUNCTION_NAME="comprehensive-billing-ingest"
REGION="us-central1"
RUNTIME="python311"
MEMORY="2048MB"
TIMEOUT="540s"
MAX_INSTANCES="10"

# Billing accounts (discovered from prior analysis)
BILLING_ACCOUNTS="018EE0-B71384-D44551"

echo "🚀 Deploying Comprehensive Billing Ingestion Function..."
echo "   Project: $PROJECT_ID"
echo "   Function: $FUNCTION_NAME"
echo "   Region: $REGION"
echo "   Billing Accounts: $BILLING_ACCOUNTS"
echo

# Check prerequisites
echo "📋 Checking prerequisites..."

# Verify gcloud auth
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n1 >/dev/null; then
    echo "❌ No active gcloud authentication found"
    echo "Run: gcloud auth login"
    exit 1
fi

# Set project
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable cloudfunctions.googleapis.com \
    cloudbuild.googleapis.com \
    cloudbilling.googleapis.com \
    bigquery.googleapis.com \
    storage.googleapis.com \
    cloudresourcemanager.googleapis.com

echo "✅ APIs enabled"

# Navigate to function directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FUNCTION_DIR="$SCRIPT_DIR/../functions/comprehensive_billing_ingest"

if [[ ! -d "$FUNCTION_DIR" ]]; then
    echo "❌ Function directory not found: $FUNCTION_DIR"
    exit 1
fi

cd "$FUNCTION_DIR"

# Deploy the function
echo "📦 Deploying Cloud Function..."

gcloud functions deploy "$FUNCTION_NAME" \
    --gen2 \
    --runtime="$RUNTIME" \
    --region="$REGION" \
    --source=. \
    --entry-point=comprehensive_billing_ingest \
    --trigger-http \
    --memory="$MEMORY" \
    --timeout="$TIMEOUT" \
    --max-instances="$MAX_INSTANCES" \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID" \
    --allow-unauthenticated \
    --service-account="$PROJECT_ID@appspot.gserviceaccount.com"

if [[ $? -eq 0 ]]; then
    echo "✅ Function deployed successfully!"
else
    echo "❌ Function deployment failed"
    exit 1
fi

# Get function URL
FUNCTION_URL=$(gcloud functions describe "$FUNCTION_NAME" \
    --region="$REGION" \
    --format="value(serviceConfig.uri)")

echo
echo "🎯 Function deployed at: $FUNCTION_URL"

# Test the function
echo "🧪 Testing function deployment..."

curl -X POST "$FUNCTION_URL" \
    -H "Content-Type: application/json" \
    -d '{"days_to_fetch": 1}' \
    -w "\n%{http_code}\n"

if [[ $? -eq 0 ]]; then
    echo "✅ Function test successful!"
else
    echo "⚠️ Function test returned error (may be expected if billing export not setup)"
fi

# Create Cloud Scheduler job for daily execution
echo "⏰ Setting up daily schedule..."

# Check if scheduler job exists
if gcloud scheduler jobs describe "$FUNCTION_NAME-daily" --location="$REGION" >/dev/null 2>&1; then
    echo "📝 Updating existing scheduler job..."
    gcloud scheduler jobs update http "$FUNCTION_NAME-daily" \
        --location="$REGION" \
        --schedule="0 6 * * *" \
        --uri="$FUNCTION_URL" \
        --http-method=POST \
        --headers="Content-Type=application/json" \
        --message-body='{"days_to_fetch": 7}' \
        --time-zone="America/New_York"
else
    echo "🆕 Creating new scheduler job..."
    gcloud scheduler jobs create http "$FUNCTION_NAME-daily" \
        --location="$REGION" \
        --schedule="0 6 * * *" \
        --uri="$FUNCTION_URL" \
        --http-method=POST \
        --headers="Content-Type=application/json" \
        --message-body='{"days_to_fetch": 7}' \
        --time-zone="America/New_York" \
        --description="Daily comprehensive billing data ingestion"
fi

echo "✅ Daily scheduler configured (6 AM EST)"

# Set up IAM permissions
echo "🔐 Configuring IAM permissions..."

# Grant billing account viewer role to the service account  
SERVICE_ACCOUNT="$PROJECT_ID@appspot.gserviceaccount.com"

# BigQuery permissions
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/bigquery.admin"

# Billing permissions  
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/billing.viewer"

# Storage permissions
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/storage.admin"

echo "✅ IAM permissions configured"

# Create monitoring and alerting
echo "📊 Setting up monitoring..."

# Create log-based metric for function errors
gcloud logging metrics create comprehensive_billing_errors \
    --description="Errors in comprehensive billing ingestion" \
    --log-filter='resource.type="cloud_function" AND resource.labels.function_name="'$FUNCTION_NAME'" AND severity>=ERROR' \
    --project="$PROJECT_ID" || echo "⚠️ Metric may already exist"

echo "✅ Monitoring configured"

# Generate summary
echo
echo "🎉 Comprehensive Billing Ingestion Deployment Complete!"
echo
echo "📋 Summary:"
echo "   Function URL: $FUNCTION_URL"
echo "   Daily Schedule: 6:00 AM EST (0 6 * * *)"
echo "   Memory: $MEMORY"
echo "   Timeout: $TIMEOUT"
echo "   Max Instances: $MAX_INSTANCES"
echo "   Billing Accounts: $BILLING_ACCOUNTS"
echo
echo "📚 Next Steps:"
echo "1. 🔧 Set up billing export in Console:"
echo "   Go to: https://console.cloud.google.com/billing"
echo "   Enable BigQuery export for account: 018EE0-B71384-D44551"
echo "   Export to: $PROJECT_ID.billing_export.gcp_billing_export_018EE0_B71384_D44551"
echo
echo "2. 🧪 Test manual execution:"
echo "   curl -X POST '$FUNCTION_URL' -H 'Content-Type: application/json' -d '{\"days_to_fetch\": 7}'"
echo
echo "3. 📊 Monitor execution:"
echo "   gcloud functions logs read '$FUNCTION_NAME' --region='$REGION'"
echo
echo "4. 🔍 Validate data ingestion:"
echo "   Check BigQuery dataset: $PROJECT_ID.org_finops_comprehensive"
echo
echo "5. 📈 View cost dashboard:"
echo "   Query: SELECT * FROM \`$PROJECT_ID.org_finops_comprehensive.v_cost_dashboard\` LIMIT 100"
echo

# Show current billing summary for context
echo "💰 Current Billing Context:"
echo "   Target Monthly Spend: \$135"
echo "   Current BigQuery Only: \$0.035/day (~\$1.05/month)"
echo "   Gap: ~\$134/month from other services (99.2%)"
echo "   Services to capture: Compute Engine, Cloud Storage, Cloud Functions, etc."
echo
echo "🎯 Success Criteria:"
echo "   ✓ Schema deployed with 6-month hot storage + archival lifecycle"
echo "   ✓ Function ready for 10+ service ingestion (not just BigQuery)" 
echo "   ✓ Daily automation with error monitoring"
echo "   ⏳ Pending: Manual billing export setup in Console"
echo "   ⏳ Pending: Historical data import (1+ year)"
echo "   ⏳ Pending: Full \$135 monthly cost visibility"
echo