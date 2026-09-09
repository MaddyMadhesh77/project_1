import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ChatRequest } from './api'

export function useChat() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: ChatRequest) => api.chat(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
    },
  })
}

export function useMemories(status?: string, limit = 50, offset = 0) {
  return useQuery({
    queryKey: ['memories', status ?? 'all', limit, offset],
    queryFn: () => api.listMemories(status, limit, offset),
    placeholderData: keepPreviousData,
  })
}

export function useMemory(memoryId: string | undefined) {
  return useQuery({
    queryKey: ['memory', memoryId],
    queryFn: () => api.getMemory(memoryId!),
    enabled: !!memoryId,
  })
}

export function useMemoryHistory(memoryId: string | undefined, limit = 50, offset = 0) {
  return useQuery({
    queryKey: ['memory-history', memoryId, limit, offset],
    queryFn: () => api.getMemoryHistory(memoryId!, limit, offset),
    enabled: !!memoryId,
    placeholderData: keepPreviousData,
  })
}

export function useMemoryGraph(memoryId: string | undefined) {
  return useQuery({
    queryKey: ['memory-graph', memoryId],
    queryFn: () => api.getMemoryGraph(memoryId!),
    enabled: !!memoryId,
  })
}

export function useVerifyIntegrity() {
  // GET /integrity/verify (bugs.md #12/#20) is read-only, so it belongs in
  // TanStack Query's query half (cacheable, auto-retried) rather than the
  // mutation half -- previously a useMutation here, matching the backend's
  // old (semantically wrong) POST. Verification is still user-triggered via
  // a button, not run on mount: enabled: false + an explicit refetch().
  return useQuery({
    queryKey: ['integrity-verify'],
    queryFn: () => api.verifyIntegrity(),
    enabled: false,
  })
}

export function useIntegrityHistory() {
  return useQuery({
    queryKey: ['integrity-history'],
    queryFn: () => api.getIntegrityHistory(),
  })
}

export function useTamperDb() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: api.tamperDb,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
    },
  })
}

export function useInjectPoison() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: api.injectPoison,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
    },
  })
}

export function useTriggerRollback() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ versionId, triggeredBy }: { versionId: string; triggeredBy?: string }) =>
      api.triggerRollback(versionId, triggeredBy),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
      queryClient.invalidateQueries({ queryKey: ['integrity-history'] })
    },
  })
}

export function useRetrainModel() {
  return useMutation({
    mutationFn: () => api.retrainModel(),
  })
}

export function useResetDemo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.resetDemo(),
    onSuccess: () => {
      // A reset touches every table this UI reads from -- invalidate
      // everything rather than enumerate each query key individually.
      queryClient.invalidateQueries()
    },
  })
}

export function useAnalyticsSummary() {
  return useQuery({
    queryKey: ['analytics-summary'],
    queryFn: () => api.getAnalyticsSummary(),
  })
}

export function useLogs(limit: number, offset: number) {
  return useQuery({
    queryKey: ['logs', limit, offset],
    queryFn: () => api.getLogs(limit, offset),
    placeholderData: keepPreviousData,
  })
}

export function useSearch(q: string) {
  return useQuery({
    queryKey: ['search', q],
    queryFn: () => api.search(q),
    enabled: q.trim().length > 0,
    placeholderData: keepPreviousData,
  })
}
