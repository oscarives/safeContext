'use client'

import { useState } from 'react'

interface AuditExport {
  trace_id: string
  exported_at: string
  operation: Record<string, unknown>
  findings: Array<Record<string, unknown>>
  redactions: Array<Record<string, unknown>>
  artifacts: Array<Record<string, unknown>>
  hmac_signature: string
}

export default function AuditPage() {
  const [traceId, setTraceId] = useState('')
  const [result, setResult] = useState<AuditExport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!traceId.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const resp = await fetch(`/api/audit/${traceId.trim()}`)
      if (resp.status === 404) { setError('Trace ID not found'); return }
      if (!resp.ok) { setError(`Error ${resp.status}`); return }
      setResult(await resp.json())
    } catch {
      setError('Failed to reach API')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-brand mb-6">Audit Trail Export</h1>

      <form onSubmit={handleSearch} className="flex gap-3 mb-6">
        <input
          type="text"
          value={traceId}
          onChange={e => setTraceId(e.target.value)}
          placeholder="Enter trace_id (UUID)"
          className="flex-1 border rounded-lg px-4 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-brand"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 bg-brand text-white rounded-lg font-medium hover:bg-brand-light disabled:opacity-50"
        >
          {loading ? 'Searching...' : 'Export'}
        </button>
      </form>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      {result && (
        <div className="space-y-4">
          {/* Summary */}
          <div className="border rounded-lg p-4 bg-white shadow-sm">
            <h2 className="font-semibold mb-2">Operation</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              {['status', 'actor_type', 'policy_version', 'artifact_digest'].map(k => (
                <div key={k} className="contents">
                  <dt className="text-gray-400">{k}</dt>
                  <dd className="font-mono truncate">{String((result.operation as Record<string, unknown>)[k] ?? '—')}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* Counts */}
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Findings', count: result.findings.length },
              { label: 'Redactions', count: result.redactions.length },
              { label: 'Artifacts', count: result.artifacts.length },
            ].map(({ label, count }) => (
              <div key={label} className="border rounded-lg p-4 bg-white shadow-sm text-center">
                <p className="text-3xl font-bold text-brand">{count}</p>
                <p className="text-sm text-gray-500 mt-1">{label}</p>
              </div>
            ))}
          </div>

          {/* HMAC */}
          <div className="border rounded-lg p-4 bg-white shadow-sm">
            <p className="text-xs text-gray-400 mb-1">HMAC-SHA256 Signature</p>
            <p className="font-mono text-xs break-all text-green-700">{result.hmac_signature}</p>
          </div>

          {/* Raw JSON download */}
          <button
            onClick={() => {
              const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `audit-${result.trace_id}.json`
              a.click()
            }}
            className="px-4 py-2 border border-brand text-brand rounded-lg hover:bg-gray-50"
          >
            Download JSON
          </button>
        </div>
      )}
    </main>
  )
}
