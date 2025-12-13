#!/bin/bash
# GCP Traffic Generator
# Generates a mix of log types and severities to exercise the logging pipeline.

PROJECT_ID="diatonic-ai-gcp"

echo "=========================================="
echo " Generating Traffic for Project: $PROJECT_ID"
echo "=========================================="

# 1. Write Application Logs (Global Resource) -> Should land in 'syslog' or 'global' table
echo "[1/4] Writing Application Logs..."
gcloud logging write my-test-log "INFO: Application startup complete." --severity=INFO --project=$PROJECT_ID
gcloud logging write my-test-log "WARNING: Deprecated API usage detected." --severity=WARNING --project=$PROJECT_ID
gcloud logging write my-test-log "ERROR: Database connection timeout." --severity=ERROR --project=$PROJECT_ID
gcloud logging write my-test-log "CRITICAL: Payment gateway unreachable!" --severity=CRITICAL --project=$PROJECT_ID

# 2. Write Structured JSON Log -> Should test JSON payload parsing
echo "[2/4] Writing Structured JSON Log..."
gcloud logging write my-json-log '{"event": "user_login", "status": "success", "user_id": 12345}' --payload-type=json --severity=INFO --project=$PROJECT_ID

# 3. Trigger Admin Activity (Audit Log) -> Should land in 'cloudaudit_googleapis_com_activity'
echo "[3/4] Triggering Real Admin Activity (Bucket Create/Delete)..."
BUCKET_NAME="diatonic-traffic-test-$(date +%s)"
gcloud storage buckets create gs://$BUCKET_NAME --project=$PROJECT_ID --location=us-central1 --quiet
gcloud storage buckets delete gs://$BUCKET_NAME --quiet

# 4. Trigger BigQuery Data Access (if enabled, optional)
# echo "[4/4] triggering BQ interaction..."
# bq ls "$PROJECT_ID:central_logging_v1" >/dev/null

echo "=========================================="
echo " Traffic Generation Complete."
echo " Check Glass Pane in ~2-5 minutes (BigQuery Latency)."
echo "=========================================="
