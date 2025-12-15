# Incident Report: Glass-Pane /api/sessions HTTP 500

## Incident Summary
- **What**: glass-pane service returning HTTP 500 for /api/sessions endpoint
- **When**: 2025-12-15 08:48:34.025996+00:00
- **Impact**: Sessions retrieval failing, potential user session issues
- **Status**: Active, under investigation

## Evidence
- Event Timestamp: 2025-12-15 08:48:34.025996+00:00
- Service: glass-pane
- Source Table: run_requests
- Request URL: https://glass-pane-845772051724.us-central1.run.app/api/sessions?user_id=test-user
- Status: 500
- Trace: projects/diatonic-ai-gcp/traces/7fc2b7e17e6a5c559cb588b6d2c19a05
- Span ID: 87cbccc3026ab980

## Hypotheses
1. **Firestore query/index missing or permission denied**: When listing sessions for user_id, Firestore access fails.
2. **Session storage schema mismatch**: Null/undefined values causing server exception.
3. **Missing env var in latest revision**: DB collection name, project ID, or credentials missing.
4. **CORS/auth middleware mis-parsing user_id**: Triggers internal crash.
5. **Response serialization error**: Circular reference or list concatenation bug in sessions response.

## Next Actions
- Execute investigation plan tool calls to gather more data.
- Analyze trace spans for failing handler.
- Check recent deployments for regressions.
- Review code for /api/sessions handler.