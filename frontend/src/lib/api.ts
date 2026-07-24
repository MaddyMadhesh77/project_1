export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })

  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, body || res.statusText)
  }

  return res.json() as Promise<T>
}

export interface ChatMessageIn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatRequest {
  conversation_id?: string
  message: string
  history: ChatMessageIn[]
}

export interface StoredMemory {
  memory_id: string
  version_id: string
  text: string
  trust_score: number
  decision: string
}

export interface ChatResponse {
  conversation_id: string
  reply: string
  stored_memories: StoredMemory[]
}

export interface Memory {
  memory_id: string
  status: string
  current_version_id: string | null
  text: string | null
  trust_score: number | null
  decision: string | null
  version_count: number
}

export type TrustBreakdown = Record<string, number>

export interface MemoryDetail extends Memory {
  trust_breakdown: TrustBreakdown | null
  content_hash: string | null
}

export interface MemoryVersion {
  version_id: string
  version_number: number
  text: string
  trust_score: number
  trust_breakdown: TrustBreakdown
  decision: string
  content_hash: string
  is_active: boolean
  created_at: string
}

export interface TrustDetail {
  version_id: string
  trust_score: number
  trust_breakdown: TrustBreakdown
  decision: string
}

// Statuses a memory's denormalized `status` column can take (DESIGN.md 5).
export const MEMORY_STATUSES = ['trusted', 'low_trust', 'quarantined', 'rolled_back'] as const

export const api = {
  chat: (body: ChatRequest) =>
    request<ChatResponse>('/chat', { method: 'POST', body: JSON.stringify(body) }),

  listMemories: (status?: string) =>
    request<Memory[]>(`/memories${status ? `?status=${encodeURIComponent(status)}` : ''}`),

  getMemory: (memoryId: string) => request<MemoryDetail>(`/memories/${memoryId}`),

  getMemoryHistory: (memoryId: string) => request<MemoryVersion[]>(`/memories/${memoryId}/history`),

  getTrust: (versionId: string) => request<TrustDetail>(`/trust/${versionId}`),
}
