# Production Deployment Configuration Guide

This document provides a comprehensive list of all environment variables, secrets, and configurations needed for production deployment of Glass Pane.

## Table of Contents
- [GitHub Secrets (Sensitive)](#github-secrets-sensitive)
- [GitHub Variables (Non-Sensitive)](#github-variables-non-sensitive)
- [GCloud Secret Manager Secrets](#gcloud-secret-manager-secrets)
- [Cloud Run Environment Variables](#cloud-run-environment-variables)
- [Cloud Functions Environment Variables](#cloud-functions-environment-variables)
- [Frontend Environment Variables](#frontend-environment-variables)
- [Firebase Console Configuration](#firebase-console-configuration)
- [Setup Commands](#setup-commands)

---

## GitHub Secrets (Sensitive)

These must be added to GitHub repository settings under **Settings > Secrets and variables > Actions > Secrets**.

| Secret Name | Description | Example/How to Get |
|------------|-------------|---------------------|
| `GCP_PROJECT_ID` | GCP Project ID | `diatonic-ai-gcp` |
| `GCP_SA_KEY` | Service Account JSON key (base64 or raw) | Download from GCP Console > IAM > Service Accounts |
| `REDIS_PASSWORD` | Redis/Memorystore password | Generate secure password or from Redis provider |
| `QDRANT_API_KEY` | Qdrant vector database API key | From Qdrant Cloud dashboard or self-hosted config |
| `FIREBASE_API_KEY` | Firebase Web API key | Firebase Console > Project Settings > General |
| `FIREBASE_APP_ID` | Firebase App ID | Firebase Console > Project Settings > General |
| `FIREBASE_MESSAGING_SENDER_ID` | Firebase Cloud Messaging Sender ID | Firebase Console > Project Settings > Cloud Messaging |

### Creating Service Account Key

```bash
# Create service account
gcloud iam service-accounts create glass-pane-deployer \
    --display-name="Glass Pane Deployer" \
    --project=diatonic-ai-gcp

# Grant required roles
gcloud projects add-iam-policy-binding diatonic-ai-gcp \
    --member="serviceAccount:glass-pane-deployer@diatonic-ai-gcp.iam.gserviceaccount.com" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding diatonic-ai-gcp \
    --member="serviceAccount:glass-pane-deployer@diatonic-ai-gcp.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding diatonic-ai-gcp \
    --member="serviceAccount:glass-pane-deployer@diatonic-ai-gcp.iam.gserviceaccount.com" \
    --role="roles/secretmanager.admin"

gcloud projects add-iam-policy-binding diatonic-ai-gcp \
    --member="serviceAccount:glass-pane-deployer@diatonic-ai-gcp.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"

# Create and download key
gcloud iam service-accounts keys create key.json \
    --iam-account=glass-pane-deployer@diatonic-ai-gcp.iam.gserviceaccount.com

# Use the contents of key.json as GCP_SA_KEY secret
cat key.json
```

---

## GitHub Variables (Non-Sensitive)

These should be added to GitHub repository settings under **Settings > Secrets and variables > Actions > Variables**.

| Variable Name | Description | Example Value |
|--------------|-------------|---------------|
| `GCP_REGION` | GCP deployment region | `us-central1` |
| `SERVICE_NAME` | Cloud Run service name | `glass-pane` |
| `SERVICE_ACCOUNT` | Cloud Run service account email | `glass-pane@diatonic-ai-gcp.iam.gserviceaccount.com` |
| `CANONICAL_VIEW` | BigQuery canonical logs view | `org_observability.logs_canonical_v2` |
| `REDIS_HOST` | Redis/Memorystore host | `10.0.0.3` or `redis.example.com` |
| `REDIS_PORT` | Redis port | `6379` |
| `QDRANT_URL` | Qdrant server URL | `https://your-cluster.qdrant.io:6333` |

---

## GCloud Secret Manager Secrets

These secrets are created automatically by the GitHub Actions workflow, but can also be created manually:

```bash
# Set project
export PROJECT_ID="diatonic-ai-gcp"

# Create Redis password secret
echo -n "your-redis-password" | gcloud secrets create REDIS_PASSWORD \
    --data-file=- \
    --replication-policy=automatic \
    --project=$PROJECT_ID

# Create Qdrant API key secret
echo -n "your-qdrant-api-key" | gcloud secrets create QDRANT_API_KEY \
    --data-file=- \
    --replication-policy=automatic \
    --project=$PROJECT_ID

# Grant Cloud Run service account access
gcloud secrets add-iam-policy-binding REDIS_PASSWORD \
    --member="serviceAccount:glass-pane@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID

gcloud secrets add-iam-policy-binding QDRANT_API_KEY \
    --member="serviceAccount:glass-pane@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID
```

---

## Cloud Run Environment Variables

These are set during deployment via `--set-env-vars`:

### Core Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `PROJECT_ID` | Main GCP project | - | Yes |
| `PROJECT_ID_LOGS` | Project containing logs | Same as PROJECT_ID | Yes |
| `PROJECT_ID_AGENT` | Project for AI agent | Same as PROJECT_ID | Yes |
| `PROJECT_ID_FINOPS` | Project for FinOps data | Same as PROJECT_ID | Yes |
| `BQ_LOCATION` | BigQuery location | `US` | Yes |

### BigQuery Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CANONICAL_VIEW` | Canonical logs view | `org_observability.logs_canonical_v2` |
| `DATASET_ID` | Default dataset | `central_logging_v1` |
| `AGENT_DATASET` | Agent dataset | `org_agent` |
| `MAX_BQ_BYTES_ESTIMATE` | Max query size (bytes) | `50000000000` |
| `MAX_ROWS_RETURNED` | Max rows per query | `1000` |
| `REQUIRE_PARTITION_FILTERS` | Require partitions | `true` |

### Vertex AI Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `VERTEX_ENABLED` | Enable Vertex AI | `true` |
| `VERTEX_REGION` | Vertex AI region | `us-central1` |
| `GOOGLE_GENAI_USE_VERTEXAI` | Use Vertex for GenAI | `true` |

### Firebase Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `FIREBASE_ENABLED` | Enable Firebase | `true` |
| `FIRESTORE_EMULATOR_HOST` | Emulator host (dev only) | Not set in prod |

### Redis Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_HOST` | Redis server host | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `REDIS_USERNAME` | Redis username | `default` |

### Qdrant Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `QDRANT_URL` | Qdrant server URL | `http://localhost:6333` |

### Feature Flags

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_DUAL_WRITE` | Enable dual write (Firestore+BQ) | `true` |
| `ENABLE_FIRESTORE_WRITE` | Enable Firestore writes | `true` |
| `ENABLE_BQ_WRITE` | Enable BigQuery writes | `true` |
| `ENABLE_PUBSUB` | Enable Pub/Sub events | `true` |
| `ENABLE_VECTOR_SEARCH` | Enable vector search | `true` |
| `ENABLE_LOG_EMBEDDINGS` | Enable log embeddings | `true` |
| `ENABLE_RETRIEVAL` | Enable retrieval node | `true` |
| `ENABLE_EMBEDDINGS` | Enable embedding generation | `true` |

### API Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `8080` |
| `ALLOWED_ORIGINS` | CORS allowed origins | `http://localhost:5173,http://localhost:3000` |
| `DEFAULT_LIMIT` | Default query limit | `100` |
| `MAX_LIMIT` | Maximum query limit | `1000` |
| `DEFAULT_TIME_WINDOW_HOURS` | Default time window | `24` |
| `MAX_TIME_WINDOW_HOURS` | Maximum time window | `168` |

---

## Cloud Functions Environment Variables

### Analytics Worker (`functions/analytics-worker`)

| Variable | Description | Default |
|----------|-------------|---------|
| `PROJECT_ID` | GCP project | `diatonic-ai-gcp` |
| `DATASET_ID` | BigQuery dataset | `chat_analytics` |
| `EMBEDDING_JOBS_TOPIC` | Pub/Sub topic for embeddings | `embedding-jobs` |
| `ENABLE_EMBEDDINGS` | Enable embedding triggers | `true` |

### Embedding Worker (`functions/embedding-worker`)

| Variable | Description | Default |
|----------|-------------|---------|
| `PROJECT_ID` | GCP project | `diatonic-ai-gcp` |
| `REGION` | GCP region | `us-central1` |
| `QDRANT_URL` | Qdrant server URL | `http://localhost:6333` |
| `QDRANT_API_KEY` | Qdrant API key | Not set |
| `EMBEDDING_MODEL` | Vertex AI embedding model | `text-embedding-004` |
| `ENABLE_EMBEDDINGS` | Enable embedding processing | `true` |

---

## Frontend Environment Variables

Create `frontend/.env.production` with these values:

```bash
# API Configuration
VITE_API_URL=https://glass-pane-845772051724.us-central1.run.app

# Firebase Configuration (REQUIRED - get from Firebase Console)
VITE_USE_FIREBASE_EMULATORS=false
VITE_FIREBASE_API_KEY=AIzaSy...your-api-key
VITE_FIREBASE_AUTH_DOMAIN=diatonic-ai-gcp.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=diatonic-ai-gcp
VITE_FIREBASE_STORAGE_BUCKET=diatonic-ai-gcp.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=123456789
VITE_FIREBASE_APP_ID=1:123456789:web:abcdef123456
```

### Getting Firebase Configuration Values

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Select your project
3. Click the gear icon > **Project Settings**
4. Scroll to **Your apps** section
5. If no web app exists, click **Add app** > Web
6. Copy the configuration values

---

## Firebase Console Configuration

### 1. Enable Authentication Providers

Go to **Firebase Console > Authentication > Sign-in method**:

- **Google**: Enable, add support email
- **GitHub**: Enable, add Client ID and Secret from [GitHub OAuth Apps](https://github.com/settings/developers)
- **Microsoft**: Enable, add Application ID and Secret from [Azure Portal](https://portal.azure.com)
- **Email/Password**: Enable if needed
- **Anonymous**: Enable for guest access

### 2. Configure Authorized Domains

Go to **Authentication > Settings > Authorized domains**:

Add your production domains:
- `glass-pane-845772051724.us-central1.run.app`
- `your-custom-domain.com`
- `localhost` (for development)

### 3. Configure OAuth Redirect URIs

For each OAuth provider, add the callback URL:
- `https://diatonic-ai-gcp.firebaseapp.com/__/auth/handler`
- `https://your-custom-domain.com/__/auth/handler`

### 4. Firestore Security Rules

Deploy security rules for production:

```bash
firebase deploy --only firestore:rules
```

---

## Setup Commands

### Complete Setup Script

```bash
#!/bin/bash
set -e

# Configuration
export PROJECT_ID="diatonic-ai-gcp"
export REGION="us-central1"
export SERVICE_NAME="glass-pane"
export SERVICE_ACCOUNT="glass-pane@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=== Setting up Glass Pane Production Environment ==="

# 1. Create Cloud Run service account
echo "Creating service account..."
gcloud iam service-accounts create glass-pane \
    --display-name="Glass Pane Service" \
    --project=$PROJECT_ID || true

# 2. Grant required roles
echo "Granting IAM roles..."
ROLES=(
    "roles/bigquery.dataViewer"
    "roles/bigquery.jobUser"
    "roles/aiplatform.user"
    "roles/datastore.user"
    "roles/pubsub.publisher"
    "roles/logging.viewer"
    "roles/cloudtrace.user"
    "roles/secretmanager.secretAccessor"
)

for ROLE in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SERVICE_ACCOUNT" \
        --role="$ROLE" \
        --condition=None || true
done

# 3. Create Pub/Sub topics
echo "Creating Pub/Sub topics..."
gcloud pubsub topics create chat-events --project=$PROJECT_ID || true
gcloud pubsub topics create embedding-jobs --project=$PROJECT_ID || true

# 4. Create Pub/Sub subscriptions
echo "Creating Pub/Sub subscriptions..."
gcloud pubsub subscriptions create chat-events-to-analytics \
    --topic=chat-events \
    --ack-deadline=60 \
    --project=$PROJECT_ID || true

gcloud pubsub subscriptions create embedding-jobs-to-worker \
    --topic=embedding-jobs \
    --ack-deadline=120 \
    --project=$PROJECT_ID || true

# 5. Create Secret Manager secrets (run interactively or with values)
echo "Creating secrets..."
# These will prompt for values or you can pipe them in
# echo -n "your-password" | gcloud secrets create REDIS_PASSWORD --data-file=- --project=$PROJECT_ID
# echo -n "your-api-key" | gcloud secrets create QDRANT_API_KEY --data-file=- --project=$PROJECT_ID

# 6. Provision BigQuery datasets
echo "Provisioning BigQuery..."
python -m src.cli provision-bq --dataset chat_analytics

echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Add GitHub Secrets and Variables (see docs/PRODUCTION_DEPLOYMENT.md)"
echo "2. Configure Firebase OAuth providers"
echo "3. Update frontend/.env.production with Firebase config"
echo "4. Push to main branch to trigger deployment"
```

### Verify Deployment

```bash
# Check Cloud Run service
gcloud run services describe glass-pane --region=us-central1 --format="table(status.url)"

# Check secrets
gcloud secrets list --project=$PROJECT_ID

# Check Pub/Sub topics
gcloud pubsub topics list --project=$PROJECT_ID

# Test health endpoint
curl https://glass-pane-845772051724.us-central1.run.app/health
```

---

## Environment Variable Summary by Component

### Backend (Cloud Run)

```bash
# Required
PROJECT_ID=diatonic-ai-gcp
PROJECT_ID_LOGS=diatonic-ai-gcp
PROJECT_ID_AGENT=diatonic-ai-gcp
PROJECT_ID_FINOPS=diatonic-ai-gcp
CANONICAL_VIEW=org_observability.logs_canonical_v2
BQ_LOCATION=US
VERTEX_ENABLED=true
VERTEX_REGION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true
FIREBASE_ENABLED=true
REDIS_HOST=<your-redis-host>
REDIS_PORT=6379
REDIS_USERNAME=default
QDRANT_URL=<your-qdrant-url>

# Secrets (via Secret Manager)
REDIS_PASSWORD=REDIS_PASSWORD:latest
QDRANT_API_KEY=QDRANT_API_KEY:latest
```

### Frontend

```bash
VITE_API_URL=https://glass-pane-845772051724.us-central1.run.app
VITE_USE_FIREBASE_EMULATORS=false
VITE_FIREBASE_API_KEY=<from-firebase-console>
VITE_FIREBASE_AUTH_DOMAIN=diatonic-ai-gcp.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=diatonic-ai-gcp
VITE_FIREBASE_STORAGE_BUCKET=diatonic-ai-gcp.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=<from-firebase-console>
VITE_FIREBASE_APP_ID=<from-firebase-console>
```

---

## Troubleshooting

### Common Issues

1. **"Permission denied" errors**
   - Ensure service account has all required roles
   - Check Secret Manager IAM bindings

2. **Firebase Auth not working**
   - Verify authorized domains in Firebase Console
   - Check OAuth redirect URIs for each provider

3. **Embedding failures**
   - Verify Qdrant URL and API key
   - Check Vertex AI API is enabled

4. **BigQuery errors**
   - Verify CANONICAL_VIEW exists
   - Check BQ_LOCATION matches dataset location

### Logs

```bash
# View Cloud Run logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=glass-pane" --limit=100

# View Cloud Function logs
gcloud logging read "resource.type=cloud_function AND resource.labels.function_name=analytics-worker" --limit=100
```
