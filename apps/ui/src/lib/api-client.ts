// api-client.ts — HTTP client for SafeContext FastAPI backend
// No business logic here — only transport.
// The access token is fetched server-side via /api/auth/token and cached
// in module memory. It is never written to localStorage or the DOM.
import { decodeJwt } from 'jose'

// En browser las llamadas van por Next.js rewrites (relativas).
// En SSR/Node van directamente al backend.
const API_BASE = typeof window === 'undefined'
  ? (process.env.NEXT_PUBLIC_API_URL ?? 'http://api:8000')
  : ''

// ─── Error types ────────────────────────────────────────────────────────────

export class ForbiddenError extends Error {
  constructor(message = 'You do not have permission to perform this action') {
    super(message)
    this.name = 'ForbiddenError'
  }
}

export class NotImplementedError extends Error {
  constructor(message = 'This feature is not yet available') {
    super(message)
    this.name = 'NotImplementedError'
  }
}

export class NotFoundError extends Error {
  constructor(message = 'Resource not found') {
    super(message)
    this.name = 'NotFoundError'
  }
}

// ─── Request / Response types ────────────────────────────────────────────────

export interface ScanRequest {
  document: string
  document_encoding?: 'text' | 'base64'
  policy_name: string
  policy_version?: string
}

export interface Finding {
  id: string
  detector: string
  rule_id: string
  span_start: number
  span_end: number
  confidence: number
  severity: 'low' | 'medium' | 'high' | 'critical'
  explanation: Record<string, unknown>
}

export interface ScanResponse {
  trace_id: string
  artifact_digest: string
  policy_version: string
  findings: Finding[]
  requires_human_review: boolean
}

export interface PendingFinding {
  operation_id: string
  trace_id: string
  finding_id: string
  detector: string
  rule_id: string
  confidence: number
  severity: 'low' | 'medium' | 'high' | 'critical'
  span_start: number
  span_end: number
  explanation: Record<string, unknown>
  document_preview: string
  created_at: string
}

export interface PendingReviewResponse {
  total: number
  items: PendingFinding[]
}

export interface ReviewDecisionResponse {
  trace_id: string
  status: string
}

export interface FindingAudit {
  id: string
  detector: string
  rule_id: string
  span_start: number
  span_end: number
  confidence: number
  severity: string
  explanation: Record<string, unknown>
}

export interface RedactionAudit {
  id: string
  finding_id: string
  redaction_type: string
  policy_version: string
  applied_at: string
  approved_by: string | null
  approval_trace_id: string | null
}

export interface ArtifactAudit {
  id: string
  artifact_type: string
  minio_key: string
  digest: string
  worm_locked: boolean
  created_at: string
}

export interface AuditExportResponse {
  trace_id: string
  exported_at: string
  operation: Record<string, unknown>
  findings: FindingAudit[]
  redactions: RedactionAudit[]
  artifacts: ArtifactAudit[]
  hmac_signature: string
}

export interface HealthResponse {
  status: string
  postgres: string
  redis: string
  minio: string
}

export interface OperationItem {
  id: string
  trace_id: string
  actor_id: string
  actor_type: string
  artifact_digest: string
  policy_version: string
  status: string
  findings_count: number
  created_at: string
  completed_at: string | null
}

export interface OperationsListResponse {
  total: number
  items: OperationItem[]
}

export interface OperationsQuery {
  status?: string
  limit?: number
  offset?: number
  from_date?: string
  to_date?: string
  actor_id?: string
}

// ─── Token cache ─────────────────────────────────────────────────────────────

interface TokenCache {
  token: string
  // exp is the unix timestamp (seconds) at which the token expires.
  // We evict the cache slightly early (30 s) to avoid race conditions.
  exp: number
}

let cachedToken: TokenCache | null = null

function clearToken(): void {
  cachedToken = null
}

async function getToken(): Promise<string> {
  const now = Math.floor(Date.now() / 1000)

  if (cachedToken && cachedToken.exp > now + 30) {
    return cachedToken.token
  }

  const res = await fetch('/api/auth/token', { credentials: 'same-origin' })

  if (res.status === 401) {
    // Session expired — redirect to login and let the page unload
    window.location.href = '/login'
    // Return a dummy value; the page will unload before this is used
    throw new Error('Session expired')
  }

  if (!res.ok) {
    throw new Error(`Failed to retrieve auth token: ${res.status}`)
  }

  const data: { token: string } = await res.json()

  // Decode exp from the JWT payload using jose (already a project dependency).
  let exp = now + 8 * 60 * 60 // default: 8 hours if we can't parse
  try {
    const payload = decodeJwt(data.token)
    if (typeof payload.exp === 'number') exp = payload.exp
  } catch {
    // Non-fatal: keep the default expiry
  }

  cachedToken = { token: data.token, exp }
  return data.token
}

// ─── Base fetch wrapper ───────────────────────────────────────────────────────

async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = await getToken()

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
      Authorization: `Bearer ${token}`,
    },
  })

  if (res.status === 401) {
    // Token was rejected by the backend (e.g. expired mid-flight)
    clearToken()
    window.location.href = '/login'
    throw new Error('Session expired')
  }

  if (res.status === 403) {
    throw new ForbiddenError()
  }

  return res
}

// ─── API methods ──────────────────────────────────────────────────────────────

export const apiClient = {
  async getHealth(): Promise<HealthResponse> {
    const res = await apiFetch('/health')
    if (!res.ok) throw new Error(`Health check failed: ${res.status}`)
    return res.json() as Promise<HealthResponse>
  },

  async postScan(req: ScanRequest): Promise<ScanResponse> {
    const res = await apiFetch('/api/scan', {
      method: 'POST',
      body: JSON.stringify(req),
    })
    if (!res.ok) {
      const detail = await res.text()
      throw new Error(`Scan failed (${res.status}): ${detail}`)
    }
    return res.json() as Promise<ScanResponse>
  },

  async getPendingReviews(): Promise<PendingReviewResponse> {
    const res = await apiFetch('/api/review/pending')
    if (!res.ok) {
      const detail = await res.text()
      throw new Error(`Failed to fetch pending reviews (${res.status}): ${detail}`)
    }
    return res.json() as Promise<PendingReviewResponse>
  },

  async postReviewDecision(
    findingId: string,
    action: 'approve' | 'reject',
    justification: string
  ): Promise<ReviewDecisionResponse> {
    const res = await apiFetch(`/api/review/${encodeURIComponent(findingId)}/${action}`, {
      method: 'POST',
      body: JSON.stringify({ justification }),
    })
    if (!res.ok) {
      const detail = await res.text()
      throw new Error(`Review decision failed (${res.status}): ${detail}`)
    }
    return res.json() as Promise<ReviewDecisionResponse>
  },

  async getAuditExport(traceId: string): Promise<AuditExportResponse> {
    const res = await apiFetch(`/api/audit/${encodeURIComponent(traceId)}`)
    if (res.status === 404) throw new NotFoundError(`Trace ID not found: ${traceId}`)
    if (!res.ok) {
      const detail = await res.text()
      throw new Error(`Audit export failed (${res.status}): ${detail}`)
    }
    return res.json() as Promise<AuditExportResponse>
  },

  async getOperations(query: OperationsQuery = {}): Promise<OperationsListResponse> {
    const params = new URLSearchParams()
    if (query.status) params.set('status', query.status)
    if (query.limit !== undefined) params.set('limit', String(query.limit))
    if (query.offset !== undefined) params.set('offset', String(query.offset))
    if (query.from_date) params.set('from_date', query.from_date)
    if (query.to_date) params.set('to_date', query.to_date)
    if (query.actor_id) params.set('actor_id', query.actor_id)
    const qs = params.toString()
    const res = await apiFetch(`/api/operations${qs ? `?${qs}` : ''}`)
    if (!res.ok) {
      const detail = await res.text()
      throw new Error(`Failed to fetch operations (${res.status}): ${detail}`)
    }
    return res.json() as Promise<OperationsListResponse>
  },
}

// Legacy named export kept for backwards compatibility with existing page components
export async function scanDocument(req: ScanRequest): Promise<ScanResponse> {
  return apiClient.postScan(req)
}

// ─── Path reference (for documentation) ──────────────────────────────────────
// All API calls use /api/* prefix (client-side), which Next.js rewrites to
// http://api:8000/v1/* (server-side proxy). This keeps a single origin for
// both browser and SSR, avoiding CORS and cookie issues.
// Exception: /health (no /v1 prefix on the backend).
