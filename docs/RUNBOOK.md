# Operations Runbook

## Deployment

### Prerequisites
- `gcloud` CLI installed and authenticated.
- Permissions: Organization Administrator (to create Org Sinks) and Project Owner.

### Initial Setup
Run the scaffold script to provision infrastructure:
```bash
cd scripts
./deploy_scaffold.sh
```

### Deploying the App
To update the Glass Pane UI:
```bash
cd app/glass-pane
gcloud builds submit --tag gcr.io/diatonic-ai-gcp/glass-pane
gcloud run deploy glass-pane --image gcr.io/diatonic-ai-gcp/glass-pane --platform managed --allow-unauthenticated
```

## Routine Operations

### Generating Test Traffic
Use the included script to generate various log types (App, JSON, Audit):
```bash
cd scripts
./generate_traffic.sh
```
*Expected output:*
- INFO/WARN/ERROR/CRITICAL logs in `global` or `syslog` tables.
- Audit logs for GCS bucket creation/deletion.

### Verifying Ingestion
1. Wait 2-5 minutes after generating traffic.
2. Open the Cloud Run URL.
3. Refresh to see new entries.
4. **Troubleshooting:**
   - If logs don't appear, check the BigQuery dataset manually: `bq ls central_logging_v1`.
   - Check the `_AllLogs` view if configured (currently using dynamic UNION).

## Incident Response

### "Dataset Not Found" Error
- **Cause:** The `deploy_scaffold.sh` script failed or wasn't run.
- **Fix:** Run the scaffold script. Ensure you have Org Admin permissions.

### "Field Mismatch" in BigQuery
- **Cause:** Two tables have incompatible schemas (e.g., `timestamp` vs `string`).
- **Fix:** The app uses `SAFE_CAST(jsonPayload AS STRING)` to mitigate this. If it persists, check `textPayload` usage in `main.py`.
