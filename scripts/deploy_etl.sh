#!/bin/bash
# Deploy ETL Pipeline Infrastructure
# Creates Pub/Sub topics, Cloud Function, and Cloud Scheduler jobs

set -e

PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"
REGION="${REGION:-us-central1}"
ETL_TOPIC="etl-jobs"
ETL_RESULTS_TOPIC="etl-results"
FUNCTION_NAME="etl-worker"

echo "=========================================="
echo "ETL Pipeline Deployment"
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_success() { echo -e "${GREEN}✓ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
log_error() { echo -e "${RED}✗ $1${NC}"; }

# 1. Create Pub/Sub Topics
echo ""
echo "Step 1: Creating Pub/Sub Topics..."
echo "-----------------------------------"

# ETL Jobs topic
if gcloud pubsub topics describe ${ETL_TOPIC} --project=${PROJECT_ID} &>/dev/null; then
    log_warning "Topic ${ETL_TOPIC} already exists"
else
    gcloud pubsub topics create ${ETL_TOPIC} --project=${PROJECT_ID}
    log_success "Created topic: ${ETL_TOPIC}"
fi

# ETL Results topic
if gcloud pubsub topics describe ${ETL_RESULTS_TOPIC} --project=${PROJECT_ID} &>/dev/null; then
    log_warning "Topic ${ETL_RESULTS_TOPIC} already exists"
else
    gcloud pubsub topics create ${ETL_RESULTS_TOPIC} --project=${PROJECT_ID}
    log_success "Created topic: ${ETL_RESULTS_TOPIC}"
fi

# 2. Deploy Cloud Function
echo ""
echo "Step 2: Deploying ETL Cloud Function..."
echo "----------------------------------------"

FUNCTION_DIR="$(dirname "$0")/../functions/etl-worker"

if [ ! -d "${FUNCTION_DIR}" ]; then
    log_error "Function directory not found: ${FUNCTION_DIR}"
    exit 1
fi

gcloud functions deploy ${FUNCTION_NAME} \
    --gen2 \
    --runtime=python312 \
    --region=${REGION} \
    --source=${FUNCTION_DIR} \
    --entry-point=process_etl_job \
    --trigger-topic=${ETL_TOPIC} \
    --memory=1024MB \
    --timeout=540s \
    --set-env-vars=PROJECT_ID=${PROJECT_ID},ETL_BATCH_SIZE=1000,ETL_RESULTS_TOPIC=${ETL_RESULTS_TOPIC} \
    --project=${PROJECT_ID}

log_success "Deployed Cloud Function: ${FUNCTION_NAME}"

# Also deploy HTTP handler for manual triggers
gcloud functions deploy ${FUNCTION_NAME}-http \
    --gen2 \
    --runtime=python312 \
    --region=${REGION} \
    --source=${FUNCTION_DIR} \
    --entry-point=etl_http_handler \
    --trigger-http \
    --allow-unauthenticated \
    --memory=1024MB \
    --timeout=540s \
    --set-env-vars=PROJECT_ID=${PROJECT_ID},ETL_BATCH_SIZE=1000 \
    --project=${PROJECT_ID}

log_success "Deployed HTTP handler: ${FUNCTION_NAME}-http"

# 3. Create Cloud Scheduler Jobs
echo ""
echo "Step 3: Creating Cloud Scheduler Jobs..."
echo "-----------------------------------------"

# Incremental hourly job
SCHEDULER_NAME="etl-incremental-hourly"
if gcloud scheduler jobs describe ${SCHEDULER_NAME} --location=${REGION} --project=${PROJECT_ID} &>/dev/null; then
    log_warning "Scheduler job ${SCHEDULER_NAME} already exists, updating..."
    gcloud scheduler jobs update pubsub ${SCHEDULER_NAME} \
        --location=${REGION} \
        --schedule="0 * * * *" \
        --topic=${ETL_TOPIC} \
        --message-body='{"job_type":"incremental","hours":2,"enable_ai":false,"batch_size":1000}' \
        --time-zone="America/Chicago" \
        --project=${PROJECT_ID}
else
    gcloud scheduler jobs create pubsub ${SCHEDULER_NAME} \
        --location=${REGION} \
        --schedule="0 * * * *" \
        --topic=${ETL_TOPIC} \
        --message-body='{"job_type":"incremental","hours":2,"enable_ai":false,"batch_size":1000}' \
        --time-zone="America/Chicago" \
        --description="Process new logs from the last 2 hours" \
        --project=${PROJECT_ID}
fi
log_success "Created scheduler: ${SCHEDULER_NAME}"

# Full daily job
SCHEDULER_NAME="etl-full-daily"
if gcloud scheduler jobs describe ${SCHEDULER_NAME} --location=${REGION} --project=${PROJECT_ID} &>/dev/null; then
    log_warning "Scheduler job ${SCHEDULER_NAME} already exists, updating..."
    gcloud scheduler jobs update pubsub ${SCHEDULER_NAME} \
        --location=${REGION} \
        --schedule="0 2 * * *" \
        --topic=${ETL_TOPIC} \
        --message-body='{"job_type":"full","enable_ai":true,"batch_size":500}' \
        --time-zone="America/Chicago" \
        --project=${PROJECT_ID}
else
    gcloud scheduler jobs create pubsub ${SCHEDULER_NAME} \
        --location=${REGION} \
        --schedule="0 2 * * *" \
        --topic=${ETL_TOPIC} \
        --message-body='{"job_type":"full","enable_ai":true,"batch_size":500}' \
        --time-zone="America/Chicago" \
        --description="Full ETL processing with AI enrichment" \
        --project=${PROJECT_ID}
fi
log_success "Created scheduler: ${SCHEDULER_NAME}"

# AI enrichment job
SCHEDULER_NAME="etl-ai-enrichment"
if gcloud scheduler jobs describe ${SCHEDULER_NAME} --location=${REGION} --project=${PROJECT_ID} &>/dev/null; then
    log_warning "Scheduler job ${SCHEDULER_NAME} already exists, updating..."
    gcloud scheduler jobs update pubsub ${SCHEDULER_NAME} \
        --location=${REGION} \
        --schedule="0 */6 * * *" \
        --topic=${ETL_TOPIC} \
        --message-body='{"job_type":"incremental","hours":6,"enable_ai":true,"batch_size":200}' \
        --time-zone="America/Chicago" \
        --project=${PROJECT_ID}
else
    gcloud scheduler jobs create pubsub ${SCHEDULER_NAME} \
        --location=${REGION} \
        --schedule="0 */6 * * *" \
        --topic=${ETL_TOPIC} \
        --message-body='{"job_type":"incremental","hours":6,"enable_ai":true,"batch_size":200}' \
        --time-zone="America/Chicago" \
        --description="AI enrichment pass on recent logs" \
        --project=${PROJECT_ID}
fi
log_success "Created scheduler: ${SCHEDULER_NAME}"

# 4. Apply BigQuery Schema
echo ""
echo "Step 4: Applying BigQuery Schema..."
echo "------------------------------------"

SCHEMA_FILE="$(dirname "$0")/../schemas/bigquery/master_logs.sql"

if [ -f "${SCHEMA_FILE}" ]; then
    # Execute schema (ignoring errors if tables exist)
    bq query --use_legacy_sql=false --project_id=${PROJECT_ID} < "${SCHEMA_FILE}" 2>/dev/null || true
    log_success "Applied BigQuery schema"
else
    log_warning "Schema file not found: ${SCHEMA_FILE}"
fi

# 5. Summary
echo ""
echo "=========================================="
echo "ETL Pipeline Deployment Complete"
echo "=========================================="
echo ""
echo "Resources created:"
echo "  - Pub/Sub Topic: ${ETL_TOPIC}"
echo "  - Pub/Sub Topic: ${ETL_RESULTS_TOPIC}"
echo "  - Cloud Function: ${FUNCTION_NAME}"
echo "  - Cloud Function: ${FUNCTION_NAME}-http"
echo "  - Scheduler: etl-incremental-hourly (hourly)"
echo "  - Scheduler: etl-full-daily (daily at 2am)"
echo "  - Scheduler: etl-ai-enrichment (every 6 hours)"
echo ""
echo "Manual trigger:"
echo "  gcloud scheduler jobs run etl-incremental-hourly --location=${REGION}"
echo ""
echo "HTTP trigger:"
echo "  curl \"https://${REGION}-${PROJECT_ID}.cloudfunctions.net/${FUNCTION_NAME}-http?job_type=incremental&hours=1\""
echo ""
echo "View logs:"
echo "  gcloud functions logs read ${FUNCTION_NAME} --region=${REGION}"
echo ""
