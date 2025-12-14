# Glass Pane Runbook

## Overview
This runbook covers the operation, verification, and troubleshooting of the Glass Pane logging platform and Gemini Agent.

## Verification Checklist (Post-Deployment)

1.  **Traffic Generation**
    *   Run `./scripts/generate_traffic.sh` to populate BigQuery with sample logs (Text, JSON, and GCS Audit logs).
    *   Wait ~1-2 minutes for BigQuery streaming buffer availability.

2.  **Frontend Availability**
    *   Access the Cloud Run URL (or `localhost:8080`).
    *   Verify the dashboard loads without errors and facet filters (Severity, Service) are populated.

3.  **Data Visibility & Filtering**
    *   Check that the table populates with the latest 50 logs.
    *   **Filter Test:** Select "ERROR" severity from the dropdown. Ensure only error logs appear.
    *   **Service Filter Test:** Select a specific service. Verify logs are filtered correctly.
    *   **Search Test:** Ensure the search functionality (though basic in current UI) can still filter logs if implemented server-side.

4.  **Log Details & Deep Inspection**
    *   Click any log row to open the Detail Drawer.
    *   Verify that the full log details (including `resource_type`, `project_id`, `operation`, etc.) are correctly displayed by fetching from `/api/logs/:id`.
    *   Ensure the JSON payload is formatted correctly.

5.  **Real-time Tailing**
    *   Click the **"⚪ Tail Logs"** button. It should change to "🔴 Tailing...".
    *   Run `./scripts/generate_traffic.sh` again (or continuously). 
    *   Verify new logs appear at the top of the table in real-time without manual refresh.
    *   Click the button again to stop tailing.

6.  **Agent Functionality**
    *   With the Detail Drawer open, click the **"🤖 Analyze with Gemini"** button.
    *   Verify the button changes to "Thinking..." and an AI-generated analysis appears below the payload.
    *   *Note: Requires valid Vertex AI credentials in the environment the Flask app is running in.*

## Common Issues

### "BigQuery client not initialized"
*   **Cause:** Missing GCP credentials or `PROJECT_ID` env var.
*   **Fix:** Ensure `GOOGLE_APPLICATION_CREDENTIALS` is set or the metadata server is reachable for your Cloud Run service account.

### "Agent failed: 500 Internal Server Error"
*   **Cause:** Vertex AI API quota exceeded or service account missing `roles/aiplatform.user`.
*   **Fix:** Check Cloud Logging for the backend traceback. Ensure the service account running the Flask app has the necessary Vertex AI permissions.

### Logs not appearing in real-time tail
*   **Cause:** BigQuery streaming ingestion latency (can be a few seconds to minutes) or `event_ts` filter issue in `/api/tail`.
*   **Fix:** Wait a bit longer or verify the `from` timestamp being sent to `/api/tail` is correct.

## Architecture & Schemas
Refer to `docs/LOGGING_POSTURE.md` and `docs/ARCHITECTURE.md` for schema definitions and ADRs.
