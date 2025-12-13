#!/bin/bash
# GCP Logging Infrastructure Scaffold
# Author: Gemini Agent for Diatonic AI
# Date: 2025-12-13

set -e

# Configuration
ORG_ID="93534264368"
PROJECT_ID="diatonic-ai-gcp"
REGION="us-central1"

# Naming Conventions
BUCKET_NAME="dacvisuals-central-logs-archive-v1"
DATASET_NAME="central_logging_v1"
TOPIC_NAME="logging-critical-alerts"
SINK_GCS="org-central-sink-gcs"
SINK_BQ="org-central-sink-bq"
SINK_PUBSUB="org-central-sink-alerts"

echo "==================================================="
echo "Starting GCP Logging Infrastructure Scaffold Deployment"
echo "Org: $ORG_ID | Project: $PROJECT_ID"
echo "==================================================="

# 1. Create/Verify GCS Archive Bucket
echo "[1/6] Configuring GCS Archive Bucket: gs://$BUCKET_NAME"
if ! gsutil ls -b gs://$BUCKET_NAME >/dev/null 2>&1; then
    gcloud storage buckets create gs://$BUCKET_NAME --project=$PROJECT_ID --location=$REGION --uniform-bucket-level-access
    echo " -> Bucket created."
else
    echo " -> Bucket exists."
fi
# Apply Lifecycle
gcloud storage buckets update gs://$BUCKET_NAME --lifecycle-file=../config/gcs_lifecycle.json
echo " -> Lifecycle policy applied."

# 2. Create/Verify BigQuery Dataset
echo "[2/6] Configuring BigQuery Dataset: $DATASET_NAME"
if ! bq show "$PROJECT_ID:$DATASET_NAME" >/dev/null 2>&1; then
    bq mk --dataset --description "Centralized Organization Logging" --location=US "$PROJECT_ID:$DATASET_NAME"
    echo " -> Dataset created."
else
    echo " -> Dataset exists."
fi

# 3. Create/Verify Pub/Sub Topic
echo "[3/6] Configuring Pub/Sub Topic: $TOPIC_NAME"
if ! gcloud pubsub topics describe $TOPIC_NAME --project=$PROJECT_ID >/dev/null 2>&1; then
    gcloud pubsub topics create $TOPIC_NAME --project=$PROJECT_ID
    echo " -> Topic created."
else
    echo " -> Topic exists."
fi

# 4. Create Organization Logging Sinks
# Note: Unique Writer Identity must be granted permissions.

# 4a. GCS Sink
echo "[4/6] Creating/Updating Org Sink: $SINK_GCS"
gcloud logging sinks create $SINK_GCS \
    storage.googleapis.com/$BUCKET_NAME \
    --organization=$ORG_ID \
    --include-children \
    --log-filter="severity>=INFO" \
    --quiet || echo " -> Sink likely exists, attempting update..."

# Grant IAM
WRITER_IDENTITY=$(gcloud logging sinks describe $SINK_GCS --organization=$ORG_ID --format="value(writerIdentity)")
echo " -> Granting Storage Object Creator to $WRITER_IDENTITY"
gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME --member="$WRITER_IDENTITY" --role="roles/storage.objectCreator" >/dev/null

# 4b. BigQuery Sink
echo "[5/6] Creating/Updating Org Sink: $SINK_BQ"
gcloud logging sinks create $SINK_BQ \
    bigquery.googleapis.com/projects/$PROJECT_ID/datasets/$DATASET_NAME \
    --organization=$ORG_ID \
    --include-children \
    --log-filter="severity>=INFO" \
    --use-partitioned-tables \
    --quiet || echo " -> Sink likely exists, attempting update..."

# Grant IAM
WRITER_IDENTITY_BQ=$(gcloud logging sinks describe $SINK_BQ --organization=$ORG_ID --format="value(writerIdentity)")
echo " -> Granting BigQuery Data Editor to $WRITER_IDENTITY_BQ"
bq add-iam-policy-binding --member="$WRITER_IDENTITY_BQ" --role="roles/bigquery.dataEditor" "$PROJECT_ID:$DATASET_NAME" >/dev/null

# 4c. Pub/Sub Sink (Alerts)
echo "[6/6] Creating/Updating Org Sink: $SINK_PUBSUB"
gcloud logging sinks create $SINK_PUBSUB \
    pubsub.googleapis.com/projects/$PROJECT_ID/topics/$TOPIC_NAME \
    --organization=$ORG_ID \
    --include-children \
    --log-filter="severity>=ERROR" \
    --quiet || echo " -> Sink likely exists, attempting update..."

# Grant IAM
WRITER_IDENTITY_PS=$(gcloud logging sinks describe $SINK_PUBSUB --organization=$ORG_ID --format="value(writerIdentity)")
echo " -> Granting Pub/Sub Publisher to $WRITER_IDENTITY_PS"
gcloud pubsub topics add-iam-policy-binding $TOPIC_NAME --project=$PROJECT_ID --member="$WRITER_IDENTITY_PS" --role="roles/pubsub.publisher" >/dev/null

echo "==================================================="
echo "Scaffold Complete. Check IAM and Logs."
echo "==================================================="
