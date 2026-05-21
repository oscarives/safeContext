'use client'

import { useState } from 'react'
import Link from 'next/link'
import { apiClient, NotFoundError, type AuditExportResponse, type OperationItem } from '@/lib/api-client'
import {
  SeverityBadge,
  StatusBadge,
  LoadingSpinner,
  EmptyState,
  CopyButton,
} from '@/components'
import { truncateDigest, formatDate, processingTime } from '@/lib/format'

// ─── Types ────────────────────────────────────────────────────────────────────

// Operation detail extends OperationItem with the document_id field from the audit export.
type OperationDetail = OperationItem & { document_id?: string }

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionHeader({
  title,
  count,
  expanded,
  onToggle,
}: {
  title: string
  count: number
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between text-left font-semibold text-gray-800 mb-2 focus:outline-none"
    >
      <span>
        {title}{' '}
        <span className="text-sm font-normal text-gray-500">({count})</span>
      </span>
      <span className="text-gray-400 text-sm">{expanded ? '▲' : '▼'}</span>
    </button>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function AuditPage() {
  const [traceId, setTraceId] = useState('')
  const [result, setResult] = useState<AuditExportResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Collapsible panel state — Set of section keys that are collapsed.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  function toggleSection(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    const id = traceId.trim()
    if (!id) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await apiClient.getAuditExport(id)
      setResult(data)
    } catch (err: unknown) {
      if (err instanceof NotFoundError) {
        setError('Trace ID no encontrado')
      } else {
        const msg = err instanceof Error ? err.message : String(err)
        setError(`Error al buscar: ${msg}`)
      }
    } finally {
      setLoading(false)
    }
  }

  function handleDownload() {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `safecontext_audit_${result.trace_id}.json`
    a.click()
    // Revoke after a short delay so the browser has time to initiate the download.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  const op = result ? (result.operation as OperationDetail) : null

  // Build a set of finding_ids that have at least one redaction
  const redactedFindingIds = new Set(
    result?.redactions.map((r) => r.finding_id) ?? []
  )

  return (
    <main className="p-8 max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-brand">Audit Trail Export</h1>

      {/* ── Search form ── */}
      <form onSubmit={handleSearch} className="flex gap-3">
        <input
          type="text"
          value={traceId}
          onChange={(e) => setTraceId(e.target.value)}
          placeholder="Introduce el trace_id (UUID completo o parcial)"
          className="flex-1 border rounded-lg px-4 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-brand"
        />
        <button
          type="submit"
          disabled={loading || !traceId.trim()}
          className="px-4 py-2 bg-brand text-white rounded-lg font-medium hover:bg-brand-light disabled:opacity-50 transition-colors"
        >
          {loading ? 'Buscando...' : 'Buscar'}
        </button>
      </form>

      {/* ── Loading ── */}
      {loading && (
        <div className="flex justify-center py-10">
          <LoadingSpinner />
        </div>
      )}

      {/* ── Error ── */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* ── No result yet (and not loading) ── */}
      {!loading && !error && !result && (
        <EmptyState title="Buscar por Trace ID" description="Introduce un trace_id para exportar el registro de auditoría." />
      )}

      {/* ── Results ── */}
      {result && op && (
        <div className="space-y-4">
          {/* Escalated banner */}
          {op.status === 'escalated' && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 flex items-center justify-between">
              <span className="text-amber-800 text-sm font-medium">
                Esta operación tiene hallazgos pendientes de revisión humana.
              </span>
              <Link
                href="/review"
                className="ml-4 text-sm font-semibold text-amber-700 underline hover:text-amber-900 whitespace-nowrap"
              >
                Ir a Revisión →
              </Link>
            </div>
          )}

          {/* ── Operation summary ── */}
          <div className="border rounded-lg p-5 bg-white shadow-sm">
            <h2 className="font-semibold text-gray-800 mb-3">Resumen de operación</h2>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
              <dt className="text-gray-400 font-medium">Status</dt>
              <dd>
                <StatusBadge status={op.status as 'pending' | 'completed' | 'escalated' | 'rejected'} />
              </dd>

              <dt className="text-gray-400 font-medium">Actor type</dt>
              <dd className="text-gray-800">{op.actor_type || '—'}</dd>

              <dt className="text-gray-400 font-medium">Policy version</dt>
              <dd className="font-mono text-gray-800">{op.policy_version || '—'}</dd>

              <dt className="text-gray-400 font-medium">Artifact digest</dt>
              <dd className="flex items-center">
                <span className="font-mono text-gray-800">
                  {op.artifact_digest ? truncateDigest(op.artifact_digest) : '—'}
                </span>
                {op.artifact_digest && <CopyButton text={op.artifact_digest} />}
              </dd>

              <dt className="text-gray-400 font-medium">Created at</dt>
              <dd className="text-gray-800">{formatDate(op.created_at)}</dd>

              <dt className="text-gray-400 font-medium">Completed at</dt>
              <dd className="text-gray-800">{formatDate(op.completed_at)}</dd>

              <dt className="text-gray-400 font-medium">Tiempo de procesamiento</dt>
              <dd className="text-gray-800">
                {processingTime(op.created_at, op.completed_at)}
              </dd>
            </dl>
          </div>

          {/* ── Findings ── */}
          {result.findings.length > 0 && (
            <div className="border rounded-lg p-5 bg-white shadow-sm">
              <SectionHeader
                title="Hallazgos detectados"
                count={result.findings.length}
                expanded={!collapsed.has('findings')}
                onToggle={() => toggleSection('findings')}
              />
              {!collapsed.has('findings') && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-gray-400 border-b">
                        <th className="pb-2 pr-4 font-medium">Severidad</th>
                        <th className="pb-2 pr-4 font-medium">Detector</th>
                        <th className="pb-2 pr-4 font-medium">Confianza</th>
                        <th className="pb-2 pr-4 font-medium">Span</th>
                        <th className="pb-2 font-medium">Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.findings.map((f) => (
                        <tr key={f.id} className="border-b last:border-0">
                          <td className="py-2 pr-4">
                            <SeverityBadge
                              severity={f.severity as 'low' | 'medium' | 'high' | 'critical'}
                            />
                          </td>
                          <td className="py-2 pr-4 font-mono text-xs text-gray-700">
                            {f.detector}
                          </td>
                          <td className="py-2 pr-4 text-gray-700">
                            {(f.confidence * 100).toFixed(0)}%
                          </td>
                          <td className="py-2 pr-4 font-mono text-xs text-gray-700">
                            [{f.span_start}:{f.span_end}]
                          </td>
                          <td className="py-2">
                            {redactedFindingIds.has(f.id) ? (
                              <span className="text-green-700 font-medium text-xs">
                                ✓ Redactado
                              </span>
                            ) : (
                              <span className="text-gray-400 text-xs">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ── Redactions ── */}
          {result.redactions.length > 0 && (
            <div className="border rounded-lg p-5 bg-white shadow-sm">
              <SectionHeader
                title="Redacciones aplicadas"
                count={result.redactions.length}
                expanded={!collapsed.has('redactions')}
                onToggle={() => toggleSection('redactions')}
              />
              {!collapsed.has('redactions') && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-gray-400 border-b">
                        <th className="pb-2 pr-4 font-medium">Tipo</th>
                        <th className="pb-2 pr-4 font-medium">Policy version</th>
                        <th className="pb-2 pr-4 font-medium">Applied at</th>
                        <th className="pb-2 font-medium">Approved by</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.redactions.map((r) => (
                        <tr key={r.id} className="border-b last:border-0">
                          <td className="py-2 pr-4">
                            <span className="inline-block px-2 py-0.5 rounded bg-gray-100 text-gray-700 text-xs font-mono">
                              {r.redaction_type}
                            </span>
                          </td>
                          <td className="py-2 pr-4 font-mono text-xs text-gray-700">
                            {r.policy_version}
                          </td>
                          <td className="py-2 pr-4 text-gray-700">
                            {formatDate(r.applied_at)}
                          </td>
                          <td className="py-2 text-gray-700 font-mono text-xs">
                            {r.approved_by
                              ? truncateDigest(r.approved_by)
                              : 'Automático'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ── Artifacts ── */}
          {result.artifacts.length > 0 && (
            <div className="border rounded-lg p-5 bg-white shadow-sm">
              <SectionHeader
                title="Artefactos"
                count={result.artifacts.length}
                expanded={!collapsed.has('artifacts')}
                onToggle={() => toggleSection('artifacts')}
              />
              {!collapsed.has('artifacts') && (
                <ul className="space-y-2">
                  {result.artifacts.map((a) => (
                    <li
                      key={a.id}
                      className="flex flex-wrap items-center gap-3 text-sm border-b last:border-0 py-2"
                    >
                      <span className="inline-block px-2 py-0.5 rounded bg-blue-100 text-blue-800 text-xs font-semibold">
                        {a.artifact_type}
                      </span>
                      <span className="font-mono text-xs text-gray-700">
                        {truncateDigest(a.digest)}
                      </span>
                      <span
                        className={`text-xs font-medium ${
                          a.worm_locked ? 'text-green-700' : 'text-gray-400'
                        }`}
                        title="WORM locked"
                      >
                        {a.worm_locked ? '✓ WORM' : '✗ WORM'}
                      </span>
                      <span className="text-xs text-gray-500 ml-auto">
                        {formatDate(a.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* ── HMAC Signature ── */}
          <div className="border rounded-lg p-5 bg-white shadow-sm">
            <p className="text-xs text-gray-400 mb-1 font-medium">
              HMAC-SHA256 Signature
            </p>
            <p className="font-mono text-xs break-all text-green-700">
              {result.hmac_signature}
            </p>
            <p className="mt-2 text-xs text-gray-400">
              Para verificar la integridad de este registro, usa el comando en
              la documentación o el endpoint{' '}
              <span className="font-mono">GET /v1/audit/verification-key</span>
            </p>
          </div>

          {/* ── Actions ── */}
          <div className="flex gap-3">
            <button
              onClick={handleDownload}
              className="px-4 py-2 border border-brand text-brand rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              Descargar JSON
            </button>
          </div>
        </div>
      )}
    </main>
  )
}
