#!/bin/bash
set -e

# Configuration
SERVICE_NAME="${SERVICE_NAME:-glass-pane}"
JOB_NAME="${JOB_NAME:-finops-nightly-rollup}"
REGION="${REGION:-us-central1}"
# GCP project to deploy into (required)
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
if [[ -z "${PROJECT_ID}" ]]; then
  echo "ERROR: PROJECT_ID is not set. Example: export PROJECT_ID=example-project-id" >&2
  exit 1
fi
SERVICE_ACCOUNT="agent-sa@${PROJECT_ID}.iam.gserviceaccount.com"

echo "🚀 Starting Production Deployment for Project: ${PROJECT_ID}"

# 1. Enable APIs
echo "Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    bigquery.googleapis.com \
    logging.googleapis.com \
    cloudscheduler.googleapis.com \
    secretmanager.googleapis.com \
    aiplatform.googleapis.com

# 2. Create Service Account if not exists
if ! gcloud iam service-accounts describe ${SERVICE_ACCOUNT} > /dev/null 2>&1; then
    echo "Creating service account ${SERVICE_ACCOUNT}..."
    gcloud iam service-accounts create agent-sa --display-name "Glass Pane Agent Service Account"
else
    echo "Service account ${SERVICE_ACCOUNT} already exists."
fi

# 3. Grant Permissions (Simplified - strictly should be more granular)
echo "Granting permissions..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/bigquery.user" > /dev/null

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/bigquery.dataEditor" > /dev/null

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/logging.viewAccessor" > /dev/null

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/aiplatform.user" > /dev/null

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
IMAGE_TAG="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:${TIMESTAMP}"

# 4. Build Container
echo "Building container image..."
gcloud builds submit --tag ${IMAGE_TAG} .

# 5. Deploy API Service
echo "Deploying Cloud Run Service: ${SERVICE_NAME}..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_TAG} \
    --platform managed \
    --region ${REGION} \
    --service-account ${SERVICE_ACCOUNT} \
    --allow-unauthenticated \
    --set-env-vars PROJECT_ID_AGENT=${PROJECT_ID} \
    --set-env-vars PROJECT_ID_LOGS=${PROJECT_ID} \
    --set-env-vars PROJECT_ID_FINOPS=${PROJECT_ID} \
    --set-env-vars CANONICAL_VIEW=org_observability.logs_canonical_v2 \
    --set-env-vars BQ_LOCATION=US \
    --set-env-vars VERTEX_ENABLED=true \
    --set-env-vars VERTEX_REGION=${REGION} \
    --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true

# 6. Deploy FinOps Job
echo "Deploying Cloud Run Job: ${JOB_NAME}..."
gcloud run jobs deploy ${JOB_NAME} \
    --image ${IMAGE_TAG} \
    --region ${REGION} \
    --service-account ${SERVICE_ACCOUNT} \
    --command "python" \
    --args="-m,src.finops.materialize_jobs" \
    --set-env-vars PROJECT_ID_AGENT=${PROJECT_ID} \
    --set-env-vars PROJECT_ID_LOGS=${PROJECT_ID} \
    --set-env-vars PROJECT_ID_FINOPS=${PROJECT_ID} \
    --set-env-vars BQ_LOCATION=US

# 7. Configure Cloud Scheduler
echo "Configuring Cloud Scheduler..."
if gcloud scheduler jobs describe ${JOB_NAME}-trigger --location ${REGION} > /dev/null 2>&1; then
    gcloud scheduler jobs update http ${JOB_NAME}-trigger \
        --location ${REGION} \
        --schedule "0 2 * * *" \
        --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
        --http-method POST \
        --oauth-service-account-email ${SERVICE_ACCOUNT}
else
    gcloud scheduler jobs create http ${JOB_NAME}-trigger \
        --location ${REGION} \
        --schedule "0 2 * * *" \
        --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
        --http-method POST \
        --oauth-service-account-email ${SERVICE_ACCOUNT}
fi

echo "✅ Deployment Complete!"
echo "API URL: $(gcloud run services describe ${SERVICE_NAME} --platform managed --region ${REGION} --format 'value(status.url)')"
