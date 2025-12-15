import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  fetchLogs,
  fetchSeverityStats,
  fetchServiceStats,
  saveQuery,
  fetchSavedQueries,
} from "@/lib/api"
import type { LogQueryParams, SaveQueryRequest } from "@/types/api"

// ============================================
// QUERY KEYS
// ============================================

export const logKeys = {
  all: ["logs"] as const,
  lists: () => [...logKeys.all, "list"] as const,
  list: (params: Partial<LogQueryParams>) => [...logKeys.lists(), params] as const,
  severityStats: (hours: number) => [...logKeys.all, "severity", hours] as const,
  serviceStats: (hours: number) => [...logKeys.all, "services", hours] as const,
}

export const savedQueryKeys = {
  all: ["savedQueries"] as const,
  lists: () => [...savedQueryKeys.all, "list"] as const,
  list: () => [...savedQueryKeys.lists()] as const,
}

// ============================================
// HOOKS
// ============================================

export function useLogs(params: Partial<LogQueryParams> = {}) {
  return useQuery({
    queryKey: logKeys.list(params),
    queryFn: () => fetchLogs(params),
    staleTime: 30_000, // 30 seconds
  })
}

export function useSeverityStats(hours = 24) {
  return useQuery({
    queryKey: logKeys.severityStats(hours),
    queryFn: () => fetchSeverityStats(hours),
    staleTime: 60_000, // 1 minute
  })
}

export function useServiceStats(hours = 24) {
  return useQuery({
    queryKey: logKeys.serviceStats(hours),
    queryFn: () => fetchServiceStats(hours),
    staleTime: 60_000, // 1 minute
  })
}

export function useSavedQueries(enabled = true) {
  return useQuery({
    queryKey: savedQueryKeys.list(),
    queryFn: () => fetchSavedQueries(),
    enabled,
    staleTime: 60_000, // 1 minute
  })
}

export function useSaveQuery() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: SaveQueryRequest) => saveQuery(request),
    onSuccess: () => {
      // Invalidate saved queries list
      queryClient.invalidateQueries({
        queryKey: savedQueryKeys.list(),
      })
    },
  })
}

// ============================================
// REFETCH HELPERS
// ============================================

export function useRefreshLogs() {
  const queryClient = useQueryClient()

  return () => {
    queryClient.invalidateQueries({ queryKey: logKeys.all })
  }
}
