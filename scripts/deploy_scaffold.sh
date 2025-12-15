#!/bin/bash
# GCP Logging Infrastructure Scaffold
# Author: Gemini Agent for Diatonic AI
# Date: 2025-12-13

#set -e

# Configuration
ORG_ID="93534264368"
PROJECT_ID="diatonic-ai-gcp"
REGION="us-central1"
SERVICE_NAME="glass-pane" # Cloud Run service name

# Naming Conventions
BUCKET_NAME="dacvisuals-central-logs-archive-v1"
DATASET_NAME="central_logging_v1"
TOPIC_NAME="logging-critical-alerts"
SINK_GCS="org-central-sink-gcs"
SINK_BQ="org-central-sink-bq"
SINK_PUBSUB="org-central-sink-alerts"

echo "==================================================="
echo "Starting GCP Logging Infrastructure Scaffold Deployment"
echo "Org: $ORG_ID | Project: $PROJECT_ID | Region: $REGION"
echo "==================================================="

# 1. Create/Verify GCS Archive Bucket
echo "[1/9] Configuring GCS Archive Bucket: gs://$BUCKET_NAME"
if ! gsutil ls -b gs://$BUCKET_NAME >/dev/null 2>&1; then
    gcloud storage buckets create gs://$BUCKET_NAME --project=$PROJECT_ID --location=$REGION --uniform-bucket-level-access
    echo " -> Bucket created."
else
    echo " -> Bucket exists."
fi
# Apply Lifecycle
gcloud storage buckets update gs://$BUCKET_NAME --lifecycle-file="$(pwd)/config/gcs_lifecycle.json" || true
echo " -> Lifecycle policy applied."

# 2. Create/Verify BigQuery Dataset (raw sink tables)
echo "[2/9] Configuring BigQuery Dataset: $DATASET_NAME"
if ! bq show "$PROJECT_ID:$DATASET_NAME" >/dev/null 2>&1; then
    bq mk --dataset --description "Centralized Organization Logging" --location=US "$PROJECT_ID:$DATASET_NAME"
    echo " -> Dataset created."
else
    echo " -> Dataset exists."
fi

# 2b. Create/Verify BigQuery Dataset for canonical views
OBS_DATASET="org_observability"
if ! bq show "$PROJECT_ID:$OBS_DATASET" >/dev/null 2>&1; then
    bq mk --dataset --description "Organization Observability (canonical views)" --location=US "$PROJECT_ID:$OBS_DATASET"
    echo " -> Dataset $OBS_DATASET created."
else
    echo " -> Dataset $OBS_DATASET exists."
fi

# Apply canonical contract view (idempotent)
# NOTE: infra/bigquery/02_canonical_contract_v2_fixed.sql currently contains a hard-coded project name.
# This scaffold script is also hard-coded to PROJECT_ID=diatonic-ai-gcp.
if [[ -f "infra/bigquery/02_canonical_contract_v2_fixed.sql" ]]; then
    echo " -> Applying canonical view: $PROJECT_ID.$OBS_DATASET.logs_canonical_v2"
    bq query --nouse_legacy_sql < "infra/bigquery/02_canonical_contract_v2_fixed.sql" || true
fi

# 3. Create/Verify Pub/Sub Topic
echo "[3/9] Configuring Pub/Sub Topic: $TOPIC_NAME"
if ! gcloud pubsub topics describe $TOPIC_NAME --project=$PROJECT_ID >/dev/null 2>&1; then
    gcloud pubsub topics create $TOPIC_NAME --project=$PROJECT_ID
    echo " -> Topic created."
else
    echo " -> Topic exists."
fi

# 4. Create Organization Logging Sinks
# Note: Unique Writer Identity must be granted permissions.

# 4a. GCS Sink
echo "[4/9] Creating/Updating Org Sink: $SINK_GCS"
if gcloud logging sinks describe $SINK_GCS --organization=$ORG_ID >/dev/null 2>&1; then
    echo " -> Sink $SINK_GCS already exists, attempting update."
    gcloud logging sinks update $SINK_GCS storage.googleapis.com/$BUCKET_NAME --organization=$ORG_ID --log-filter="severity>=INFO" --quiet || true
else
    gcloud logging sinks create $SINK_GCS storage.googleapis.com/$BUCKET_NAME --organization=$ORG_ID --include-children --log-filter="severity>=INFO" --quiet || true
    echo " -> Sink $SINK_GCS created."
fi

# Grant IAM
WRITER_IDENTITY=$(gcloud logging sinks describe $SINK_GCS --organization=$ORG_ID --format="value(writerIdentity)")
echo " -> Granting Storage Object Creator to $WRITER_IDENTITY"
gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME --member="$WRITER_IDENTITY" --role="roles/storage.objectCreator"

# 4b. BigQuery Sink
echo "[5/9] Creating/Updating Org Sink: $SINK_BQ"
if gcloud logging sinks describe $SINK_BQ --organization=$ORG_ID >/dev/null 2>&1; then
    echo " -> Sink $SINK_BQ already exists, attempting update."
    gcloud logging sinks update $SINK_BQ bigquery.googleapis.com/projects/$PROJECT_ID/datasets/$DATASET_NAME --organization=$ORG_ID --log-filter="severity>=INFO" --use-partitioned-tables --quiet || true
else
    gcloud logging sinks create $SINK_BQ bigquery.googleapis.com/projects/$PROJECT_ID/datasets/$DATASET_NAME --organization=$ORG_ID --include-children --log-filter="severity>=INFO" --use-partitioned-tables --quiet || true
    echo " -> Sink $SINK_BQ created."
fi

# Grant IAM
WRITER_IDENTITY_BQ=$(gcloud logging sinks describe $SINK_BQ --organization=$ORG_ID --format="value(writerIdentity)")
echo " -> Granting BigQuery Data Editor to $WRITER_IDENTITY_BQ"
bq add-iam-policy-binding --member="$WRITER_IDENTITY_BQ" --role="roles/bigquery.dataEditor" "$PROJECT_ID:$DATASET_NAME"

# 4c. Pub/Sub Sink (Alerts)
echo "[6/9] Creating/Updating Org Sink: $SINK_PUBSUB"
if gcloud logging sinks describe $SINK_PUBSUB --organization=$ORG_ID >/dev/null 2>&1; then
    echo " -> Sink $SINK_PUBSUB already exists, attempting update."
    gcloud logging sinks update $SINK_PUBSUB pubsub.googleapis.com/projects/$PROJECT_ID/topics/$TOPIC_NAME --organization=$ORG_ID --log-filter="severity>=ERROR" --quiet || true
else
    gcloud logging sinks create $SINK_PUBSUB pubsub.googleapis.com/projects/$PROJECT_ID/topics/$TOPIC_NAME --organization=$ORG_ID --include-children --log-filter="severity>=ERROR" --quiet || true
    echo " -> Sink $SINK_PUBSUB created."
fi

# Grant IAM
WRITER_IDENTITY_PS=$(gcloud logging sinks describe $SINK_PUBSUB --organization=$ORG_ID --format="value(writerIdentity)")
echo " -> Granting Pub/Sub Publisher to $WRITER_IDENTITY_PS"
gcloud pubsub topics add-iam-policy-binding $TOPIC_NAME --project=$PROJECT_ID --member="$WRITER_IDENTITY_PS" --role="roles/pubsub.publisher"

# 5. Build and Deploy Cloud Run Service
echo "[7/9] Building and Deploying Cloud Run Service: $SERVICE_NAME"
# Generate a unique build ID
BUILD_ID=$(date +%s)
# Build container image (unified FastAPI service at repo root)
gcloud builds submit . --tag gcr.io/$PROJECT_ID/$SERVICE_NAME:$BUILD_ID --project=$PROJECT_ID

# Deploy to Cloud Run
# This single service serves:
# - UI routes (/)
# - log APIs (/api/logs, /api/stats/*)
# - agent streaming endpoint (/api/chat)
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME:$BUILD_ID \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --project=$PROJECT_ID \
    --set-env-vars PROJECT_ID_LOGS=$PROJECT_ID,PROJECT_ID_AGENT=$PROJECT_ID,PROJECT_ID_FINOPS=$PROJECT_ID,BQ_LOCATION=US,VERTEX_ENABLED=true,VERTEX_REGION=$REGION,GOOGLE_GENAI_USE_VERTEXAI=true,CANONICAL_VIEW=org_observability.logs_canonical_v2 \
    --cpu=1 \
    --memory=512Mi \
    --timeout=300 \
    --min-instances=0 \
    --max-instances=2 \
    --port=8080

echo "[8/9] Deploying Log Processor Cloud Function"
gcloud functions deploy log-processor \
  --trigger-topic=$TOPIC_NAME \
  --runtime=python312 \
  --entry-point=process_log_entry \
  --source=functions/log-processor \
  --region=$REGION \
  --project=$PROJECT_ID \
  --memory=128Mi \
  --timeout=60s


echo "[9/9] Waiting for Cloud Run URL..."
CLOUD_RUN_URL="$(gcloud run services describe $SERVICE_NAME --project=$PROJECT_ID --region=$REGION --format='value(status.url)')"
echo "Cloud Run URL: $CLOUD_RUN_URL"

echo "==================================================="
echo "Scaffold Complete. Check IAM, Logs and Cloud Run URL."
echo "==================================================="
