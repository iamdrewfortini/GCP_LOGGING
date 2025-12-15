# Deployment Configuration Reference

**Last Updated:** 2025-12-15  
**Status:** ✅ Production Ready

## Overview

This document describes the secure credential management system for the GCP_LOGGING Cloud Run deployment.

---

## GitHub Actions Configuration

### Secrets (Sensitive)

Stored in GitHub repository settings → Secrets and variables → Actions → Secrets

| Secret Name | Purpose | Used By |
|------------|---------|---------|
| `GCP_PROJECT_ID` | GCP project identifier | GitHub Actions, Cloud Run |
| `GCP_SA_KEY` | Service account JSON key for deployment | GitHub Actions auth |
| `REDIS_PASSWORD` | Redis Cloud authentication | GCP Secret Manager → Cloud Run |
| `QDRANT_API_KEY` | Qdrant Cloud authentication | GCP Secret Manager → Cloud Run |

### Variables (Non-Sensitive)

Stored in GitHub repository settings → Secrets and variables → Actions → Variables

| Variable Name | Value | Purpose |
|--------------|-------|---------|
| `GCP_REGION` | `us-central1` | Deployment region |
| `SERVICE_NAME` | `glass-pane` | Cloud Run service name |
| `SERVICE_ACCOUNT` | `agent-sa@diatonic-ai-gcp.iam.gserviceaccount.com` | Runtime service account |
| `CANONICAL_VIEW` | `org_observability.logs_canonical_v2` | BigQuery view reference |
| `REDIS_HOST` | `redis-12863.crce197.us-east-2-1.ec2.cloud.redislabs.com` | Redis Cloud endpoint |
| `REDIS_PORT` | `12863` | Redis Cloud port |
| `QDRANT_URL` | `https://94e1737f-81c2-4e1e-bf36-5e67888d1e07.us-east-1-1.aws.cloud.qdrant.io` | Qdrant Cloud endpoint |

---

## Secret Management Flow

```
┌─────────────────────┐
│  GitHub Actions     │
│     Secrets         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  GCP Secret Manager │  ← Created/updated during deployment
│  - REDIS_PASSWORD   │
│  - QDRANT_API_KEY   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Cloud Run         │  ← Secrets mounted as env vars at runtime
│   Service           │
└─────────────────────┘
```

### Workflow Steps

1. **GitHub Actions** reads secrets from repository settings
2. **Setup Secret Manager** step creates/updates secrets in GCP Secret Manager
3. **Grant Access** step ensures service account has `secretAccessor` role
4. **Cloud Run Deploy** mounts secrets using `--set-secrets` flag

---

## Cloud Run Environment Variables

### Set via `--set-env-vars`

```bash
PROJECT_ID=$GCP_PROJECT_ID
PROJECT_ID_LOGS=$GCP_PROJECT_ID
PROJECT_ID_AGENT=$GCP_PROJECT_ID
PROJECT_ID_FINOPS=$GCP_PROJECT_ID
CANONICAL_VIEW=$CANONICAL_VIEW
BQ_LOCATION=US
VERTEX_ENABLED=true
VERTEX_REGION=$GCP_REGION
GOOGLE_GENAI_USE_VERTEXAI=true
FIREBASE_ENABLED=true
REDIS_HOST=$REDIS_HOST
REDIS_PORT=$REDIS_PORT
REDIS_USERNAME=default
QDRANT_URL=$QDRANT_URL
```

### Set via `--set-secrets` (Secret Manager)

```bash
REDIS_PASSWORD=REDIS_PASSWORD:latest
QDRANT_API_KEY=QDRANT_API_KEY:latest
```

---

## Local Development

For local development, create a `.env` file (never commit this):

```bash
# Copy from .env.prod.template and fill in actual values
PROJECT_ID_AGENT=your-project-id
PROJECT_ID_LOGS=your-project-id
PROJECT_ID_FINOPS=your-project-id
REGION=us-central1
BQ_LOCATION=US

# BigQuery
MAX_BQ_BYTES_ESTIMATE=53687091200
MAX_ROWS_RETURNED=1000
REQUIRE_PARTITION_FILTERS=true

# Security
PII_REDACTION_ENABLED=true

# Vertex AI
VERTEX_ENABLED=true

# Redis (get from GitHub secrets or ops team)
REDIS_HOST=redis-12863.crce197.us-east-2-1.ec2.cloud.redislabs.com
REDIS_PORT=12863
REDIS_USERNAME=default
REDIS_PASSWORD=<ask ops team>

# Qdrant (get from GitHub secrets or ops team)
QDRANT_URL=https://94e1737f-81c2-4e1e-bf36-5e67888d1e07.us-east-1-1.aws.cloud.qdrant.io
QDRANT_API_KEY=<ask ops team>
```

**Note:** Use Firebase emulators for local development when possible to avoid production credentials.

---

## Credential Rotation

### When to Rotate

- ✅ Immediately after any suspected exposure
- ✅ Quarterly as part of security hygiene
- ✅ When team members with access leave

### How to Rotate

#### Redis Password

1. Generate new password in Redis Cloud console
2. Update GitHub secret:
   ```bash
   gh secret set REDIS_PASSWORD --body "NEW_PASSWORD" --repo iamdrewfortini/GCP_LOGGING
   ```
3. Trigger deployment (push to main or manual workflow dispatch)
4. Verify service health after deployment

#### Qdrant API Key

1. Generate new API key in Qdrant Cloud console
2. Update GitHub secret:
   ```bash
   gh secret set QDRANT_API_KEY --body "NEW_API_KEY" --repo iamdrewfortini/GCP_LOGGING
   ```
3. Trigger deployment
4. Verify service health after deployment

---

## Security Notes

1. **Never commit credentials** to git history
2. **Secrets are automatically synced** from GitHub → Secret Manager on every deployment
3. **Service account IAM** is automatically granted during deployment
4. **Cloud Run runtime** mounts secrets as environment variables (not visible in logs)
5. **Secret Manager versions** are tagged with `:latest` for automatic updates

---

## Troubleshooting

### Secret Not Found in Cloud Run

```bash
# Check if secret exists in Secret Manager
gcloud secrets describe REDIS_PASSWORD --project=diatonic-ai-gcp

# Check service account has access
gcloud secrets get-iam-policy REDIS_PASSWORD --project=diatonic-ai-gcp
```

### Service Account Permission Issues

```bash
# Grant secretAccessor role manually if needed
gcloud secrets add-iam-policy-binding REDIS_PASSWORD \
  --member="serviceAccount:agent-sa@diatonic-ai-gcp.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=diatonic-ai-gcp
```

### Verify Cloud Run Environment

```bash
# Get running service config
gcloud run services describe glass-pane \
  --region=us-central1 \
  --project=diatonic-ai-gcp \
  --format=yaml
```

---

## Related Documentation

- [GitHub Actions Workflow](.github/workflows/deploy-production.yml)
- [Environment Template](.env.prod.template)
- [Next 10 Commits Checklist](docs/research/ai-stack/next_10_commits.md)
- [Frontend Architecture](docs/FRONTEND_ARCHITECTURE.md)
