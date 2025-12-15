# Edge Deployment

## Environment Variables
### Backend (.env)
- Existing: `PROJECT_ID`, `REGION`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `FIREBASE_PROJECT_ID`, etc.
- Added: None required, /graphql endpoint is relative.

### Frontend (.env.production)
- `VITE_GRAPHQL_ENDPOINT`: Base URL for GraphQL API (e.g., `https://glass-pane-api-xxx.run.app/graphql`)
- Existing: Firebase config vars.

## Env Validation (Backend)
- **Startup Check**: In `main.py`, ensure Redis and Qdrant ping succeed.
- **GraphQL**: Schema validation on import.

## Deployment Manifests
### Cloud Run Services
- **glass-pane**: Frontend service, build from `frontend/` with Vite.
- **glass-pane-agent**: Backend API service, build from `.` with Dockerfile.

### Updated Commands
```bash
# Deploy backend
gcloud run deploy glass-pane-agent \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "PROJECT_ID=$PROJECT_ID,REGION=$REGION,..." \
  --port 8080

# Deploy frontend
cd frontend
gcloud run deploy glass-pane \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "VITE_GRAPHQL_ENDPOINT=https://glass-pane-agent-xxx.run.app/graphql"
```

## Edge Strategy
- **Redis Cache**: Provides edge-like latency for reads.
- **Firebase Realtime**: Sync writes for low-latency updates.
- **Cloud Run**: Global routing for low latency.

## CORS Settings
- Updated `ALLOWED_ORIGINS` in backend to include frontend Cloud Run URL.
- Frontend assumes GraphQL at same origin or configured endpoint.

## Per-Env Config
- Dev: Local Redis/Qdrant, localhost CORS.
- Staging/Prod: Cloud Redis, Firebase, restricted CORS.