# Go-Live Checklist: Vertex AI Integration

## Pre-Flight Checks
- [ ] **Service Account**: Verify `vertex-ai-service` has `roles/aiplatform.user`.
- [ ] **Quotas**: Check Vertex AI "Gemini Pro" quotas in `us-central1`.
- [ ] **Billing**: Verify billing is enabled for the project.

## Deployment Steps
1.  **Deploy Revision**:
    ```bash
    gcloud run deploy glass-pane \
      --image gcr.io/diatonic-ai-gcp/glass-pane:latest \
      --region us-central1 \
      --service-account vertex-ai-service@diatonic-ai-gcp.iam.gserviceaccount.com \
      --set-env-vars="PROJECT_ID=diatonic-ai-gcp,DATASET_ID=central_logging_v1,VERTEX_ENABLED=true,VERTEX_REGION=us-central1"
    ```
2.  **Verify Health**:
    -   Check `https://glass-pane-845772051724.us-central1.run.app/health` returns 200.
    -   Check `/api/tail` returns logs (fixes 500 error).

## Validation (Smoke Test)
- [ ] **Chat API**:
    ```bash
    curl -X POST https://glass-pane-845772051724.us-central1.run.app/api/chat \
      -H "Content-Type: application/json" \
      -d '{"query": "Show me recent errors"}'
    ```
    -   *Expected*: Streaming JSON response with log analysis.
- [ ] **Redaction**: Verify no IPs/secrets in the output.

## Rollback Plan
If 500 errors or high latency occur:
1.  **Disable Feature**:
    ```bash
    gcloud run services update glass-pane --update-env-vars=VERTEX_ENABLED=false
    ```
2.  **Revert Code**: Re-deploy previous revision if crash persists.
