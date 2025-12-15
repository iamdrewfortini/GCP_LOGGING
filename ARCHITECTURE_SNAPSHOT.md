# Architecture Snapshot

## Tech Stack
- **Backend**: FastAPI (Python), Uvicorn server
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS
- **Database/Cache**: Redis (cache), Firebase (realtime/sync), BigQuery (data lake), Qdrant (vector search)
- **Deployment**: Cloud Run, Docker, Cloud Build
- **Monitoring**: Google Cloud Logging, Tracing

## Monorepo Layout
- `src/api/main.py`: Main FastAPI app with CORS, health endpoint, /api/logs routes
- `src/api/etl_routes.py`: ETL router included
- `src/api/auth.py`: Firebase ID token authentication (get_current_user_uid)
- `src/services/`: firebase_service.py, redis_service.py, qdrant_service.py, bigquery_service.py, dual_write_service.py
- `src/schemas/log_payload_schema.py`: Pydantic models for LogPayloadV1 (severity, log_type, timestamps, etc.)
- `frontend/`: React app with TanStack Query, Firebase SDK, Playwright tests
- `requirements.txt`: Python deps (FastAPI, firebase-admin, redis, qdrant-client, etc.)
- `frontend/package.json`: JS deps (@tanstack/react-query, firebase, but no @apollo/client yet)

## Call Graph Notes
- Main app includes etl_router, uses redis_service.ping() in health
- Auth via Firebase ID tokens in headers
- Data flow: BigQuery -> ETL -> Qdrant/Redis/Firestore
- No existing GraphQL; REST endpoints like /api/logs with query params (hours, limit, severity)

## Existing API Endpoints
- `/health`: Redis/Qdrant status
- `/api/logs`: Query logs with filters
- ETL routes from etl_routes.py

## Firebase/Redis/Qdrant Usage
- Firebase: Realtime sync, admin SDK
- Redis: Cache layer
- Qdrant: Vector embeddings for logs

## Package Managers
- Python: pip (requirements.txt)
- JS: npm/pnpm (package.json)

## Deployment Config
- Dockerfile, cloudbuild.yaml for Cloud Run
- Env vars in .env, .env.example