# Frontend Architecture

This document describes the Glass Pane frontend architecture, including the React application, Firebase integration, and development workflow.

## Overview

The Glass Pane frontend is a modern React application that provides a rich user interface for log visualization and AI-powered log analysis. It communicates with the FastAPI backend via REST APIs and uses Firebase for client-side session management and authentication.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Browser                                 │
├─────────────────────────────────────────────────────────────────────┤
│  React Frontend (Vite)                                              │
│  ├── UI Components (Radix UI + Tailwind CSS)                        │
│  ├── State Management (TanStack Query)                              │
│  ├── Routing (TanStack Router)                                      │
│  └── Firebase SDK (Auth, Firestore - client-side)                   │
├─────────────────────────────────────────────────────────────────────┤
│  Vite Dev Server (localhost:5173)                                   │
│  └── Proxy: /api/* → Backend                                        │
├─────────────────────────────────────────────────────────────────────┤
│  FastAPI Backend (Cloud Run / localhost:8080)                       │
│  ├── /api/logs - BigQuery log queries                               │
│  ├── /api/chat - AI agent SSE streaming                             │
│  ├── /api/sessions - Firebase session management                    │
│  └── /api/saved-queries - Firebase query persistence                │
├─────────────────────────────────────────────────────────────────────┤
│  Data Services                                                       │
│  ├── BigQuery (central_logging_v1)                                  │
│  ├── Firestore (sessions, messages, saved_queries)                  │
│  └── Vertex AI (Gemini 2.5 Flash for agent)                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Frontend Framework
- **Vite** - Build tool and dev server with HMR
- **React 19** - UI library
- **TypeScript** - Type-safe JavaScript

### UI Components
- **Radix UI** - Accessible, unstyled components
- **Tailwind CSS 4** - Utility-first styling
- **Lucide React** - Icons
- **shadcn/ui pattern** - Component composition

### State Management
- **TanStack Query** - Server state management with caching
- **TanStack Router** - Type-safe routing

### Firebase
- **Firebase SDK 12** - Client-side Firebase integration
- **Firebase Emulators** - Local development

## Directory Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # Reusable UI components (shadcn pattern)
│   │   ├── layout/          # App layout components
│   │   └── chat/            # AI chat components
│   ├── hooks/
│   │   ├── use-logs.ts      # Log fetching hooks
│   │   ├── use-chat.ts      # AI chat hooks
│   │   └── use-sessions.ts  # Session management hooks
│   ├── lib/
│   │   ├── api.ts           # API client functions
│   │   ├── firebase.ts      # Firebase configuration
│   │   └── utils.ts         # Utility functions
│   ├── routes/
│   │   ├── __root.tsx       # Root layout
│   │   ├── index.tsx        # Dashboard
│   │   ├── logs.tsx         # Log viewer
│   │   ├── chat.tsx         # AI chat page
│   │   └── services/        # Service-specific pages
│   ├── types/
│   │   └── api.ts           # API type definitions with Zod
│   ├── main.tsx             # App entry point
│   └── router.tsx           # Route definitions
├── .env.local               # Local environment (gitignored)
├── .env.example             # Environment template
├── vite.config.ts           # Vite configuration
└── package.json             # Dependencies
```

## Environment Configuration

### Environment Variables

```bash
# API Configuration
VITE_API_URL=http://localhost:8080  # Backend URL (dev: local, prod: Cloud Run)

# Firebase Emulator Settings
VITE_USE_FIREBASE_EMULATORS=true    # Enable local emulators
VITE_FIREBASE_PROJECT_ID=diatonic-ai-gcp

# Emulator Ports (must match firebase.json)
VITE_FIREBASE_AUTH_EMULATOR_HOST=localhost
VITE_FIREBASE_AUTH_EMULATOR_PORT=9099
VITE_FIREBASE_FIRESTORE_EMULATOR_HOST=localhost
VITE_FIREBASE_FIRESTORE_EMULATOR_PORT=8181
VITE_FIREBASE_STORAGE_EMULATOR_HOST=localhost
VITE_FIREBASE_STORAGE_EMULATOR_PORT=9199
```

### Vite Proxy Configuration

The frontend uses Vite's proxy to forward API requests to the backend:

```typescript
// vite.config.ts
server: {
  port: 5173,
  proxy: {
    "/api": {
      target: env.VITE_API_URL || "https://glass-pane-845772051724.us-central1.run.app",
      changeOrigin: true,
      secure: true,
    },
  },
},
```

## Firebase Integration

### Client-Side Firebase

The frontend uses Firebase SDK for:
- **Authentication** - User sign-in/sign-up (optional)
- **Firestore** - Direct reads for session history (optional)

```typescript
// src/lib/firebase.ts
const emulatorConfig = {
  useEmulators: import.meta.env.VITE_USE_FIREBASE_EMULATORS === "true",
  firestoreHost: import.meta.env.VITE_FIREBASE_FIRESTORE_EMULATOR_HOST || "localhost",
  firestorePort: parseInt(import.meta.env.VITE_FIREBASE_FIRESTORE_EMULATOR_PORT || "8181"),
}

// Connect to emulators in development
if (emulatorConfig.useEmulators) {
  connectFirestoreEmulator(db, emulatorConfig.firestoreHost, emulatorConfig.firestorePort)
}
```

### Server-Side Firebase (Backend)

The FastAPI backend uses Firebase Admin SDK for:
- Session creation and management
- Message persistence
- Saved query storage

## Development Workflow

### Local Development

1. **Start Firebase Emulators**:
```bash
firebase emulators:start
```

2. **Start Backend** (in separate terminal):
```bash
export FIRESTORE_EMULATOR_HOST="127.0.0.1:8181"
uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload
```

3. **Start Frontend** (in separate terminal):
```bash
cd frontend
npm run dev
```

4. **Access**:
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8080/api
   - Firebase Emulator UI: http://localhost:4000

### Using the Dev Script

```bash
# Start everything (emulators + backend + frontend)
./scripts/dev_local.sh

# Start only emulators
./scripts/dev_local.sh --emulators-only

# Start only app (assumes emulators running)
./scripts/dev_local.sh --app-only
```

## API Integration

### API Client Pattern

```typescript
// src/lib/api.ts
const API_BASE = "/api"

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {},
  schema?: { parse: (data: unknown) => T }
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  })

  if (!response.ok) {
    throw new ApiError(response.status, response.statusText)
  }

  const data = await response.json()
  return schema ? schema.parse(data) : data
}
```

### Streaming Chat (SSE)

```typescript
// src/lib/api.ts
export async function* streamChat(request: ChatRequest): AsyncGenerator<ChatStreamEvent> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  })

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const chunk = decoder.decode(value, { stream: true })
    // Parse SSE events...
    yield JSON.parse(eventData) as ChatStreamEvent
  }
}
```

## State Management

### TanStack Query Patterns

```typescript
// src/hooks/use-logs.ts
export function useLogs(params: Partial<LogQueryParams> = {}) {
  return useQuery({
    queryKey: ["logs", params],
    queryFn: () => fetchLogs(params),
    staleTime: 1000 * 60, // 1 minute
  })
}

// src/hooks/use-chat.ts
export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])

  const sendMessage = async (message: string) => {
    for await (const event of streamChat({ message })) {
      if (event.type === "on_chat_model_stream") {
        // Update message content incrementally
      }
    }
  }

  return { messages, sendMessage }
}
```

## Routing

### Route Structure

```
/                  - Dashboard with severity stats
/logs              - Log viewer with filters
/chat              - AI chat interface
/costs             - Cost analysis (coming soon)
/services          - GCP services overview
/services/cloud-run - Cloud Run dashboard
/services/functions - Cloud Functions (coming soon)
/settings          - Application settings
```

### Route Definition

```typescript
// src/router.tsx
const routeTree = rootRoute.addChildren([
  indexRoute,      // Dashboard
  logsRoute,       // Log viewer
  chatRoute,       // AI assistant
  costsRoute,      // Cost analysis
  servicesIndexRoute,
  cloudRunRoute,
  // ... more routes
])

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
})
```

## Build and Deployment

### Development Build
```bash
cd frontend
npm run dev
```

### Production Build
```bash
cd frontend
npm run build
```

Output is in `frontend/dist/` - can be served statically or bundled with backend.

### Production Deployment Options

1. **Static Hosting** (Recommended for CDN):
   - Deploy `frontend/dist/` to Firebase Hosting, Cloudflare Pages, or GCS
   - Configure CORS on backend for frontend domain

2. **Bundled with Backend**:
   - Copy `frontend/dist/` to backend static directory
   - Serve from FastAPI at `/`

3. **Separate Cloud Run Services**:
   - Frontend as nginx container
   - Backend as Python container
   - Use Cloud Load Balancer for routing

## Security Considerations

- **CORS**: Backend allows requests from configured frontend origins
- **CSP**: Content Security Policy headers set on all responses
- **Firebase Security Rules**: Firestore rules restrict access by user ID
- **API Validation**: All inputs validated with Zod schemas
- **Sensitive Data**: Log content redacted before AI processing

## Deprecated: Legacy Template UI

The previous Jinja2 template-based UI has been deprecated in favor of this React application:
- ~~`src/glass_pane/templates/index.html`~~ - Old Bootstrap UI
- ~~`src/glass_pane/static/`~~ - Old static assets
- ~~`GET /` route in main.py~~ - Old HTML response

The backend now serves only JSON APIs. The frontend is the sole UI layer.
