'use client'
import { useEffect, useState } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface PendingFinding {
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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ReviewPage() {
  const [findings, setFindings] = useState<PendingFinding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/review/pending')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(d => {
        setFindings(d.items ?? [])
        setLoading(false)
      })
      .catch(err => {
        setError(String(err))
        setLoading(false)
      })
  }, [])

  async function handleDecision(findingId: string, action: 'approve' | 'reject') {
    const justification = prompt(`Justification for ${action}:`)
    if (!justification) return

    const res = await fetch(`/api/review/${findingId}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ justification }),
    })

    if (!res.ok) {
      alert(`Failed to ${action}: HTTP ${res.status}`)
      return
    }

    setFindings(prev => prev.filter(f => f.finding_id !== findingId))
  }

  if (loading) {
    return <div className="p-8 text-gray-500">Loading pending reviews...</div>
  }

  if (error) {
    return (
      <div className="p-8 text-red-600">
        Error loading reviews: {error}
      </div>
    )
  }

  if (findings.length === 0) {
    return (
      <div className="p-8 text-green-600 font-medium">
        No pending reviews — all clear.
      </div>
    )
  }

  return (
    <main className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Pending Human Review</h1>
      <p className="text-gray-500 mb-6">{findings.length} finding(s) require review</p>
      <div className="space-y-4">
        {findings.map(f => (
          <FindingCard key={f.finding_id} finding={f} onDecision={handleDecision} />
        ))}
      </div>
    </main>
  )
}

// ── FindingCard ───────────────────────────────────────────────────────────────

const severityColors: Record<PendingFinding['severity'], string> = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-red-100 text-red-800',
  critical: 'bg-purple-100 text-purple-800',
}

function FindingCard({
  finding,
  onDecision,
}: {
  finding: PendingFinding
  onDecision: (id: string, action: 'approve' | 'reject') => void
}) {
  const preview = finding.document_preview
  const before = preview.slice(0, finding.span_start)
  const highlighted = preview.slice(finding.span_start, finding.span_end)
  const after = preview.slice(finding.span_end)

  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm">
      {/* Header row */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={`inline-block px-2 py-1 rounded text-xs font-semibold ${severityColors[finding.severity]}`}
          >
            {finding.severity.toUpperCase()}
          </span>
          <span className="font-mono text-sm text-gray-700">{finding.detector}</span>
          <span className="text-xs text-gray-400">rule: {finding.rule_id}</span>
        </div>
        <span className="text-sm text-gray-500 whitespace-nowrap ml-2">
          {Math.round(finding.confidence * 100)}% confidence
        </span>
      </div>

      {/* Document preview with highlighted span */}
      <div className="font-mono text-sm bg-gray-50 p-2 rounded mb-3 overflow-x-auto whitespace-pre-wrap break-words">
        {before}
        <mark className="bg-yellow-200 px-0.5 rounded">{highlighted}</mark>
        {after}
      </div>

      {/* Meta */}
      <div className="text-xs text-gray-400 mb-3 space-y-0.5">
        <div>
          Trace: <code className="bg-gray-100 px-1 rounded">{finding.trace_id}</code>
        </div>
        <div>
          Span [{finding.span_start}:{finding.span_end}] &middot; Created:{' '}
          {new Date(finding.created_at).toLocaleString()}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={() => onDecision(finding.finding_id, 'approve')}
          className="px-3 py-1.5 bg-green-600 text-white text-sm rounded hover:bg-green-700 transition-colors"
        >
          Approve
        </button>
        <button
          onClick={() => onDecision(finding.finding_id, 'reject')}
          className="px-3 py-1.5 bg-red-600 text-white text-sm rounded hover:bg-red-700 transition-colors"
        >
          Reject
        </button>
      </div>
    </div>
  )
}
