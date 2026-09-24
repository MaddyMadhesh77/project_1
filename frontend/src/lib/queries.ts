import { keepPreviousData, type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ChatRequest } from './api'

// Every query that reads memory-store state. Any write (chat, attack
// simulator, rollback) can change all of them: only invalidating ['memories']
// left the analytics, logs, integrity history, open memory pages and search
// results stale until a remount. integrity-verify is deliberately excluded --
// it's a user-triggered check, re-run on demand, not live state.
const MEMORY_STORE_KEYS = [
  'memories',
  'memory',
  'memory-history',
  'memory-graph',
  'analytics-summary',
  'logs',
  'integrity-history',
  'search',
] as const

function invalidateMemoryStore(queryClient: QueryClient) {
  for (const key of MEMORY_STORE_KEYS) queryClient.invalidateQueries({ queryKey: [key] })
}

export function useChat() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: ChatRequest) => api.chat(body),
    onSuccess: () => invalidateMemoryStore(queryClient),
  })
}

export function useMemories(status?: string, limit = 50, offset = 0) {
  return useQuery({
    queryKey: ['memories', status ?? 'all', limit, offset],
    queryFn: () => api.listMemories(status, limit, offset),
    placeholderData: keepPreviousData,
  })
}

export function useModelStatus() {
  return useQuery({
    queryKey: ['model-status'],
    queryFn: () => api.getModelStatus(),
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
  // GET /integrity/verify is read-only, so it belongs in
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
    onSuccess: () => invalidateMemoryStore(queryClient),
  })
}

export function useInjectPoison() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: api.injectPoison,
    onSuccess: () => invalidateMemoryStore(queryClient),
  })
}

export function useTriggerRollback() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ versionId, triggeredBy }: { versionId: string; triggeredBy?: string }) =>
      api.triggerRollback(versionId, triggeredBy),
    onSuccess: () => invalidateMemoryStore(queryClient),
  })
}

export function useRetrainModel() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.retrainModel(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['model-status'] }),
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
