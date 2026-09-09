export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Backend requires X-API-Key once the operator sets API_KEY (see
// backend/app/core/security.py) -- unset by default, matching the backend's
// unauthenticated local/demo default. Note this is a shared-secret gate, not
// real per-user auth: VITE_ vars are baked into the built bundle and visible
// to anyone who opens dev tools, so this stops casual/opportunistic access
// on a shared network, not a determined attacker with the deployed bundle.
const API_KEY = import.meta.env.VITE_API_KEY as string | undefined

// Every backend data route lives under /v1 (bugs.md #13 / app/main.py) --
// prefixed once here rather than in each endpoint string below, so bumping
// to /v2 later is a one-line change instead of an edit-every-call-site diff.
const API_PREFIX = '/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
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

export interface MemoriesPage {
  items: Memory[]
  total: number
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

export interface MemoryHistoryPage {
  items: MemoryVersion[]
  total: number
}

export interface TrustDetail {
  version_id: string
  trust_score: number
  trust_breakdown: TrustBreakdown
  decision: string
}

export interface RetrainResult {
  n_samples: number
  n_synthetic_samples: number
  n_real_samples: number
  n_safe: number
  n_poisoned: number
  train_accuracy: number
  trained_at: string
  signed: boolean
}

export interface ResetResult {
  truncated_tables: string[]
  seeded_lines: string[]
}

export interface GraphNode {
  version_id: string
  memory_id: string
  text: string
  trust_score: number
  status: string
  is_current: boolean
}

export interface GraphEdge {
  parent_version_id: string
  child_version_id: string
  relation_type: string
}

export interface MemoryGraph {
  root_version_id: string
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface RowMismatch {
  version_id: string
  memory_id: string
}

export interface VerifyResult {
  tampered: boolean
  row_mismatches: RowMismatch[]
  root_mismatch: boolean
  expected_root: string | null
  actual_root: string
  leaf_count: number
}

export interface MerkleRootSnapshot {
  root_id: string
  root_hash: string
  leaf_count: number
  computed_at: string
}

export interface TamperRequest {
  version_id: string
  text?: string
}

export interface TamperResult {
  version_id: string
  old_text: string
  new_text: string
}

export interface InjectPoisonRequest {
  text: string
  memory_id?: string
  forced_trust_score?: number
}

export interface InjectPoisonResult {
  memory_id: string
  version_id: string
  text: string
  trust_score: number
  decision: string
}

export type RollbackOutcome = 'kept' | 'reverted' | 'removed'

export interface RollbackNodeOutcome {
  version_id: string
  memory_id: string
  text: string
  outcome: RollbackOutcome
  new_version_id: string
  trust_score: number
  reason: string
}

export interface RollbackResult {
  rollback_id: string
  root_version_id: string
  affected: RollbackNodeOutcome[]
  triggered_by: string
  started_at: string
  completed_at: string | null
  merkle_root: string
}

export interface TrendPoint {
  date: string
  store: number
  review: number
  reject: number
  rollbacks: number
}

export interface AnalyticsSummary {
  status_counts: Record<string, number>
  decision_counts: Record<string, number>
  total_memories: number
  total_versions: number
  rollback_count: number
  trend: TrendPoint[]
}

export interface LogEntry {
  event_id: string
  memory_id: string
  version_id: string
  text: string
  event_type: string
  decision: string
  trust_score: number | null
  created_at: string
}

export interface LogsPage {
  items: LogEntry[]
  total: number
}

export interface SearchHit {
  memory_id: string
  version_id: string
  text: string
  trust_score: number
  similarity: number
}

// Statuses a memory's denormalized `status` column can take (DESIGN.md 5).
export const MEMORY_STATUSES = ['trusted', 'low_trust', 'quarantined', 'rolled_back'] as const

export const api = {
  chat: (body: ChatRequest) =>
    request<ChatResponse>('/chat', { method: 'POST', body: JSON.stringify(body) }),

  listMemories: (status?: string, limit = 50, offset = 0) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (status) params.set('status', status)
    return request<MemoriesPage>(`/memories?${params.toString()}`)
  },

  getMemory: (memoryId: string) => request<MemoryDetail>(`/memories/${memoryId}`),

  getMemoryHistory: (memoryId: string, limit = 50, offset = 0) =>
    request<MemoryHistoryPage>(`/memories/${memoryId}/history?limit=${limit}&offset=${offset}`),

  getTrust: (versionId: string) => request<TrustDetail>(`/trust/${versionId}`),

  retrainModel: () => request<RetrainResult>('/trust/retrain', { method: 'POST' }),

  resetDemo: () => request<ResetResult>('/admin/reset', { method: 'POST' }),

  getMemoryGraph: (memoryId: string) => request<MemoryGraph>(`/memories/${memoryId}/graph`),

  verifyIntegrity: () => request<VerifyResult>('/integrity/verify'),

  getIntegrityHistory: () => request<MerkleRootSnapshot[]>('/integrity/history'),

  tamperDb: (body: TamperRequest) =>
    request<TamperResult>('/attack/tamper-db', { method: 'POST', body: JSON.stringify(body) }),

  injectPoison: (body: InjectPoisonRequest) =>
    request<InjectPoisonResult>('/attack/inject-poison', { method: 'POST', body: JSON.stringify(body) }),

  triggerRollback: (versionId: string, triggeredBy = 'admin') =>
    request<RollbackResult>(`/rollback/${versionId}`, {
      method: 'POST',
      body: JSON.stringify({ triggered_by: triggeredBy }),
    }),

  getRollback: (rollbackId: string) => request<RollbackResult>(`/rollback/${rollbackId}`),

  getAnalyticsSummary: () => request<AnalyticsSummary>('/analytics/summary'),

  getLogs: (limit = 50, offset = 0) => request<LogsPage>(`/logs?limit=${limit}&offset=${offset}`),

  search: (q: string, topK = 5) =>
    request<SearchHit[]>(`/search?q=${encodeURIComponent(q)}&top_k=${topK}`),
}
