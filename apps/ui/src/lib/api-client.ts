// api-client.ts — HTTP client for SafeContext FastAPI backend
// No lógica de negocio aquí — solo transporte

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://api:8000'

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

export async function scanDocument(req: ScanRequest): Promise<ScanResponse> {
  const res = await fetch(`${API_BASE}/v1/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`SafeContext scan failed (${res.status}): ${detail}`)
  }
  return res.json() as Promise<ScanResponse>
}
