import {
  type LogQueryParams,
  type LogsResponse,
  type SeverityStats,
  type ServiceStats,
  type CreateSessionRequest,
  type SessionsListResponse,
  type SessionDetailResponse,
  type SaveQueryRequest,
  type SavedQueriesResponse,
  type ChatRequest,
  type ChatStreamEvent,
  type HealthResponse,
  LogsResponseSchema,
  SeverityStatsSchema,
  ServiceStatsSchema,
  SessionsListResponseSchema,
  SessionDetailResponseSchema,
  SavedQueriesResponseSchema,
  HealthResponseSchema,
} from "@/types/api"
import { getIdToken } from "@/lib/auth"

// Base API URL - use relative path for Vite proxy in dev
const API_BASE = "/api"

// Get auth headers with Firebase ID token
async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await getIdToken()
  if (token) {
    return { Authorization: `Bearer ${token}` }
  }
  return {}
}

// ============================================
// FETCH HELPERS
// ============================================

export class ApiError extends Error {
  status: number
  data?: unknown

  constructor(status: number, message: string, data?: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.data = data
  }
}

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {},
  schema?: { parse: (data: unknown) => T },
  requiresAuth = false
): Promise<T> {
  const url = `${API_BASE}${endpoint}`

  // Get auth headers for authenticated endpoints
  const authHeaders = requiresAuth ? await getAuthHeaders() : {}

  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...options.headers,
    },
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new ApiError(response.status, errorData.message || response.statusText, errorData)
  }

  const data = await response.json()

  if (schema) {
    return schema.parse(data)
  }

  return data as T
}

// ============================================
// LOG API
// ============================================

export async function fetchLogs(params: Partial<LogQueryParams> = {}): Promise<LogsResponse> {
  const searchParams = new URLSearchParams()

  if (params.hours) searchParams.set("hours", String(params.hours))
  if (params.limit) searchParams.set("limit", String(params.limit))
  if (params.severity) searchParams.set("severity", params.severity)
  if (params.service) searchParams.set("service", params.service)
  if (params.search) searchParams.set("search", params.search)
  if (params.source_table) searchParams.set("source_table", params.source_table)

  const query = searchParams.toString()
  const endpoint = query ? `/logs?${query}` : "/logs"

  return fetchApi<LogsResponse>(endpoint, {}, LogsResponseSchema)
}

export async function fetchSeverityStats(hours = 24): Promise<SeverityStats> {
  return fetchApi<SeverityStats>(`/stats/severity?hours=${hours}`, {}, SeverityStatsSchema)
}

export async function fetchServiceStats(hours = 24): Promise<ServiceStats> {
  return fetchApi<ServiceStats>(`/stats/services?hours=${hours}`, {}, ServiceStatsSchema)
}

// ============================================
// SESSION API
// ============================================

export async function createSession(request: CreateSessionRequest): Promise<{ session_id: string }> {
  return fetchApi<{ session_id: string; status: string }>(
    "/sessions",
    {
      method: "POST",
      body: JSON.stringify(request),
    },
    undefined,
    true // requiresAuth
  )
}

export async function fetchSessions(
  status = "active",
  limit = 50
): Promise<SessionsListResponse> {
  const params = new URLSearchParams({
    status,
    limit: String(limit),
  })

  return fetchApi<SessionsListResponse>(`/sessions?${params}`, {}, SessionsListResponseSchema, true)
}

export async function fetchSession(sessionId: string): Promise<SessionDetailResponse> {
  return fetchApi<SessionDetailResponse>(`/sessions/${sessionId}`, {}, SessionDetailResponseSchema, true)
}

export async function archiveSession(sessionId: string): Promise<void> {
  await fetchApi(`/sessions/${sessionId}/archive`, { method: "POST" }, undefined, true)
}

// ============================================
// SAVED QUERIES API
// ============================================

export async function saveQuery(request: SaveQueryRequest): Promise<{ query_id: string }> {
  return fetchApi<{ query_id: string; status: string }>(
    "/saved-queries",
    {
      method: "POST",
      body: JSON.stringify(request),
    },
    undefined,
    true // requiresAuth
  )
}

export async function fetchSavedQueries(limit = 50): Promise<SavedQueriesResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
  })

  return fetchApi<SavedQueriesResponse>(`/saved-queries?${params}`, {}, SavedQueriesResponseSchema, true)
}

// ============================================
// CHAT API (SSE Streaming)
// ============================================

export async function* streamChat(request: ChatRequest): AsyncGenerator<ChatStreamEvent> {
  const authHeaders = await getAuthHeaders()

  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    throw new ApiError(response.status, "Chat request failed")
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error("No response body")
  }

  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split("\n")
    buffer = lines.pop() || ""

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6).trim()
        if (data === "[DONE]") {
          return
        }
        try {
          yield JSON.parse(data) as ChatStreamEvent
        } catch {
          // Skip invalid JSON
        }
      }
    }
  }
}

// ============================================
// HEALTH API
// ============================================

export async function fetchHealth(): Promise<HealthResponse> {
  return fetchApi<HealthResponse>("/health", {}, HealthResponseSchema)
}

