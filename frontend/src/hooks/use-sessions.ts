import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  createSession,
  fetchSessions,
  fetchSession,
  archiveSession,
} from "@/lib/api"
import type { CreateSessionRequest, SessionStatus } from "@/types/api"

// ============================================
// QUERY KEYS
// ============================================

export const sessionKeys = {
  all: ["sessions"] as const,
  lists: () => [...sessionKeys.all, "list"] as const,
  list: (status: SessionStatus) => [...sessionKeys.lists(), status] as const,
  details: () => [...sessionKeys.all, "detail"] as const,
  detail: (id: string) => [...sessionKeys.details(), id] as const,
}

// ============================================
// HOOKS
// ============================================

export function useSessions(status: SessionStatus = "active", enabled = true) {
  return useQuery({
    queryKey: sessionKeys.list(status),
    queryFn: () => fetchSessions(status),
    enabled,
    staleTime: 30_000, // 30 seconds
  })
}

export function useSession(sessionId: string) {
  return useQuery({
    queryKey: sessionKeys.detail(sessionId),
    queryFn: () => fetchSession(sessionId),
    enabled: !!sessionId,
    staleTime: 10_000, // 10 seconds
  })
}

export function useCreateSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: CreateSessionRequest) => createSession(request),
    onSuccess: () => {
      // Invalidate sessions list
      queryClient.invalidateQueries({
        queryKey: sessionKeys.lists(),
      })
    },
  })
}

export function useArchiveSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (sessionId: string) => archiveSession(sessionId),
    onSuccess: (_data, sessionId) => {
      // Invalidate this session and list
      queryClient.invalidateQueries({
        queryKey: sessionKeys.detail(sessionId),
      })
      queryClient.invalidateQueries({
        queryKey: sessionKeys.lists(),
      })
    },
  })
}
