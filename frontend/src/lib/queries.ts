import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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

export function useMemories(status?: string) {
  return useQuery({
    queryKey: ['memories', status ?? 'all'],
    queryFn: () => api.listMemories(status),
  })
}

export function useMemory(memoryId: string | undefined) {
  return useQuery({
    queryKey: ['memory', memoryId],
    queryFn: () => api.getMemory(memoryId!),
    enabled: !!memoryId,
  })
}

export function useMemoryHistory(memoryId: string | undefined) {
  return useQuery({
    queryKey: ['memory-history', memoryId],
    queryFn: () => api.getMemoryHistory(memoryId!),
    enabled: !!memoryId,
  })
}
