# GitHub Actions Automated Deployment Setup

## Summary

Successfully configured automated deployment of the GCP Logging application from GitHub to Google Cloud Run using GitHub Actions.

## Configuration Completed

### 1. GitHub Environment
- **Environment**: `production`
- **Created**: 2025-12-15
- **Protection rules**: None (can be added for approval requirements)

### 2. GitHub Secrets
| Secret Name | Purpose |
|------------|---------|
| `GCP_PROJECT_ID` | GCP project identifier (diatonic-ai-gcp) |
| `GCP_SA_KEY` | Service account JSON key for deployment authentication |

### 3. GitHub Variables
| Variable Name | Value | Purpose |
|--------------|-------|---------|
| `GCP_REGION` | us-central1 | Target GCP region for deployment |
| `SERVICE_NAME` | glass-pane | Cloud Run service name |
| `SERVICE_ACCOUNT` | agent-sa@diatonic-ai-gcp.iam.gserviceaccount.com | Service account for running the Cloud Run service |
| `CANONICAL_VIEW` | org_observability.logs_canonical_v2 | BigQuery canonical view name |

### 4. GCP IAM Permissions
The following permissions were granted to `agent-sa@diatonic-ai-gcp.iam.gserviceaccount.com`:
- `roles/storage.admin` - For GCR image storage
- `roles/artifactregistry.writer` - For pushing to Artifact Registry
- `roles/run.admin` - For Cloud Run deployments
- `roles/iam.serviceAccountUser` - To act as itself during deployment
- `roles/bigquery.user` - For BigQuery access (already configured)
- `roles/aiplatform.user` - For Vertex AI access (already configured)
- `roles/logging.viewAccessor` - For log viewing (already configured)

### 5. GitHub Actions Workflow
- **File**: `.github/workflows/deploy-production.yml`
- **Triggers**:
  - Push to `main` branch (automatic)
  - Manual workflow dispatch
- **Jobs**:
  1. **Run Tests**: Installs dependencies, compiles Python, runs pytest
  2. **Build and Deploy to Cloud Run**: Builds Docker image, pushes to GCR, deploys to Cloud Run

## Deployment Process

### Automatic Deployment
Every push to the `main` branch triggers:
1. Automated testing
2. Docker image build
3. Push to Google Container Registry
4. Deployment to Cloud Run

### Manual Deployment
```bash
gh workflow run deploy-production.yml
```

## Service Information

- **Service URL**: https://glass-pane-yzv4l7gkja-uc.a.run.app
- **Region**: us-central1
- **Health Endpoint**: https://glass-pane-yzv4l7gkja-uc.a.run.app/health
- **Min Instances**: 0
- **Max Instances**: 2
- **CPU**: 1
- **Memory**: 512Mi
- **Timeout**: 300s

## Environment Variables (Cloud Run)
The following environment variables are automatically set during deployment:
```
PROJECT_ID_LOGS=diatonic-ai-gcp
PROJECT_ID_AGENT=diatonic-ai-gcp
PROJECT_ID_FINOPS=diatonic-ai-gcp
CANONICAL_VIEW=org_observability.logs_canonical_v2
BQ_LOCATION=US
VERTEX_ENABLED=true
VERTEX_REGION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true
```

## Code Changes Made

### 1. Fixed BigQuery Client Initialization (src/agent/tools/bq.py)
- Changed from module-level client initialization to lazy loading via `get_client()`
- This allows tests to run without GCP credentials
- Added `__getattr__` for backwards compatibility

### 2. Updated Tests (tests/unit/test_bq_tools.py)
- Updated mocks to patch `get_client` instead of the module-level `client`
- Tests now pass in CI/CD environment

## Testing the Deployment

### Health Check
```bash
curl https://glass-pane-yzv4l7gkja-uc.a.run.app/health
# Expected: {"status":"ok"}
```

### View Logs
```bash
curl "https://glass-pane-yzv4l7gkja-uc.a.run.app/api/logs?limit=10"
```

### Monitor Deployment
```bash
# View latest workflow run
gh run list --limit 5

# Watch a specific run
gh run watch <run-id>

# View run details
gh run view <run-id>
```

## Security Considerations

1. **Service Account Key**: Stored as GitHub secret, rotatable at any time
2. **IAM Permissions**: Least-privilege principle applied where possible
3. **Public Access**: Service is currently `--allow-unauthenticated` for demo purposes
   - For production, consider adding IAP (Identity-Aware Proxy)
4. **Secret Rotation**: Create new service account key and update GitHub secret periodically

## Future Improvements

1. **Workload Identity Federation**: Migrate from service account keys to Workload Identity Federation for keyless authentication
2. **Branch Protection**: Add required status checks on `main` branch
3. **Deployment Environments**: Add staging environment for pre-production testing
4. **Rollback Strategy**: Implement automated rollback on deployment failures
5. **Monitoring**: Add alerting for deployment failures
6. **Cost Optimization**: Review Cloud Run instance scaling and pricing

## Troubleshooting

### Deployment Fails at Docker Push
- Verify `GCP_SA_KEY` secret is correctly configured
- Check service account has `artifactregistry.writer` role

### Deployment Fails at Cloud Run Deploy
- Verify service account has `run.admin` role
- Check service account has `iam.serviceAccountUser` on itself

### Tests Fail in CI
- Ensure dependencies in `requirements.txt` are up to date
- Check that mocks are properly configured

## References

- Workflow runs: https://github.com/iamdrewfortini/GCP_LOGGING/actions
- Cloud Run console: https://console.cloud.google.com/run?project=diatonic-ai-gcp
- Service account: https://console.cloud.google.com/iam-admin/serviceaccounts?project=diatonic-ai-gcp
