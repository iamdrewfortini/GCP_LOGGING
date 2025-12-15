# Validation Report

## Backend Validation
### Unit Tests for Resolvers
```bash
cd /home/daclab-ai/GCP_LOGGING
python -m pytest tests/unit/test_graphql_resolvers.py -v
```
**Expected Output**: All tests pass, e.g., `5 passed, 0 failed`.

### Integration Test for /graphql
```bash
curl -s -X POST http://localhost:8000/graphql \
  -H 'content-type: application/json' \
  -H 'Authorization: Bearer <valid_firebase_token>' \
  -d '{"query":"query{health{ok version}}"}' | jq
```
**Expected Output**:
```json
{
  "data": {
    "health": {
      "ok": true,
      "version": "2.0.0",
      "services": {
        "redis": "connected",
        "qdrant": "connected",
        "firebase": "connected",
        "bigquery": "connected"
      }
    }
  }
}
```

### Auth Test (Missing Token)
```bash
curl -s -X POST http://localhost:8000/graphql \
  -H 'content-type: application/json' \
  -d '{"query":"query{logs(filter:{hours:1}){totalCount}}"}' | jq
```
**Expected Output**: Error with "Authentication required".

### Auth Test (Invalid Token)
```bash
curl -s -X POST http://localhost:8000/graphql \
  -H 'content-type: application/json' \
  -H 'Authorization: Bearer invalid_token' \
  -d '{"query":"query{logs(filter:{hours:1}){totalCount}}"}' | jq
```
**Expected Output**: Error with "Authentication required".

## Frontend Validation
### Smoke Test: Logs Page
```bash
cd frontend
npm run test:e2e:smoke  # Assuming test script for /logs page
```
**Expected**: Page loads, GraphQL query to /graphql, displays logs.

### Realtime Test
- Load /logs page.
- Update a log in Firebase.
- **Expected**: UI refreshes automatically via TanStack invalidation.

### Network Calls Check
- Open browser dev tools on /logs page.
- **Expected**: Requests to /graphql, not to REST endpoints.

## Performance Validation
### Cache Hit Ratio
```bash
# Check Redis keys for logs
redis-cli keys "logs:*" | wc -l
# Expected: >0 keys after queries
```

### Query Latency Logs
- Run queries, check app logs for latency metrics.
- **Expected**: <500ms for cached, <2s for uncached.

## Commands Summary
- Backend: `python -m pytest -q`, `uvicorn src.api.main:app --reload`, `curl` for health.
- Frontend: `cd frontend && npm install && npm run dev`, open /logs, verify network.
- Deployment: `gcloud run services describe glass-pane --region us-central1`, check /graphql endpoint.