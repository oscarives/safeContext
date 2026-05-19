'use client'

import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { apiClient } from '@/lib/api-client'
import type { AuditExportResponse, FindingAudit } from '@/lib/api-client'
import {
  LoadingSpinner,
  FindingCard,
  DocumentViewer,
} from '@/components'
import type { Finding as FindingCardFinding } from '@/components'

// ─── Types ────────────────────────────────────────────────────────────────────

type PageState = 'idle' | 'scanning' | 'result' | 'error'

interface ScanResult {
  traceId: string
  policyVersion: string
  requiresHumanReview: boolean
  findings: FindingAudit[]
  documentText: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function toFindingCardShape(
  f: FindingAudit,
  documentText: string,
  traceId: string
): FindingCardFinding {
  return {
    finding_id: f.id,
    detector: f.detector,
    rule_id: f.rule_id,
    confidence: f.confidence,
    severity: f.severity as FindingCardFinding['severity'],
    span_start: f.span_start,
    span_end: f.span_end,
    explanation: f.explanation,
    document_preview: documentText,
    trace_id: traceId,
  }
}

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS = 30000

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ScanPage() {
  const [pageState, setPageState] = useState<PageState>('idle')
  const [documentText, setDocumentText] = useState('')
  const [policyName] = useState('default')
  const [result, setResult] = useState<ScanResult | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [copied, setCopied] = useState(false)

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollStartRef = useRef<number>(0)

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current !== null) {
        clearInterval(pollIntervalRef.current)
      }
    }
  }, [])

  function stopPolling() {
    if (pollIntervalRef.current !== null) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
  }

  function startPolling(traceId: string, docText: string) {
    pollStartRef.current = Date.now()

    pollIntervalRef.current = setInterval(async () => {
      const elapsed = Date.now() - pollStartRef.current
      if (elapsed >= POLL_TIMEOUT_MS) {
        stopPolling()
        setPageState('error')
        setErrorMessage(
          'Tiempo de espera agotado. El sistema está ocupado, intenta de nuevo.'
        )
        return
      }

      try {
        const audit: AuditExportResponse = await apiClient.getAuditExport(traceId)
        const operation = audit.operation as Record<string, unknown>
        const status = operation.status as string | undefined

        if (status !== 'pending') {
          stopPolling()
          const requiresHumanReview =
            typeof operation.requires_human_review === 'boolean'
              ? operation.requires_human_review
              : false
          const policyVersion =
            typeof operation.policy_version === 'string'
              ? operation.policy_version
              : ''

          setResult({
            traceId,
            policyVersion,
            requiresHumanReview,
            findings: audit.findings,
            documentText: docText,
          })
          setPageState('result')
        }
      } catch (err: unknown) {
        stopPolling()
        setPageState('error')
        setErrorMessage(
          err instanceof Error ? err.message : 'Error desconocido al obtener resultados.'
        )
      }
    }, POLL_INTERVAL_MS)
  }

  async function handleScan() {
    if (!documentText.trim()) return

    setPageState('scanning')
    setErrorMessage('')
    setResult(null)

    try {
      const scanResponse = await apiClient.postScan({
        document: documentText,
        policy_name: policyName,
        document_encoding: 'text',
      })

      startPolling(scanResponse.trace_id, documentText)
    } catch (err: unknown) {
      setPageState('error')
      setErrorMessage(
        err instanceof Error ? err.message : 'Error desconocido al iniciar el scan.'
      )
    }
  }

  function handleReset() {
    stopPolling()
    setPageState('idle')
    setDocumentText('')
    setResult(null)
    setErrorMessage('')
    setCopied(false)
  }

  async function handleCopyTraceId(traceId: string) {
    try {
      await navigator.clipboard.writeText(traceId)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API not available — silently ignore
    }
  }

  const isScanning = pageState === 'scanning'

  return (
    <main className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Escanear documento</h1>

      {/* ── Form ── */}
      {(pageState === 'idle' || pageState === 'scanning') && (
        <section className="bg-white rounded-lg shadow-sm border p-6 mb-6">
          <div className="mb-4">
            <label
              htmlFor="document-input"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Documento
            </label>
            <textarea
              id="document-input"
              rows={12}
              className="w-full border rounded-md p-3 text-sm font-mono text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400 resize-y"
              placeholder="Pega el texto o documento a escanear..."
              value={documentText}
              onChange={(e) => setDocumentText(e.target.value)}
              disabled={isScanning}
            />
          </div>

          <div className="mb-5">
            <label
              htmlFor="policy-select"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Política de escaneo
            </label>
            <select
              id="policy-select"
              className="border rounded-md px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
              value={policyName}
              disabled={isScanning}
              onChange={() => {/* fixed policy — no change */}}
            >
              <option value="default">default</option>
            </select>
          </div>

          <button
            onClick={handleScan}
            disabled={!documentText.trim() || isScanning}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm font-medium rounded-md transition-colors disabled:cursor-not-allowed"
          >
            {isScanning ? (
              <>
                <LoadingSpinner size="sm" />
                Escaneando...
              </>
            ) : (
              'Escanear'
            )}
          </button>
        </section>
      )}

      {/* ── Scanning / polling ── */}
      {pageState === 'scanning' && (
        <div className="flex flex-col items-center justify-center py-12 text-gray-500">
          <LoadingSpinner size="lg" message="Analizando documento..." />
        </div>
      )}

      {/* ── Result: clean ── */}
      {pageState === 'result' && result && result.findings.length === 0 && (
        <section className="space-y-4">
          <div className="rounded-lg bg-green-50 border border-green-200 px-5 py-4 flex items-start gap-3">
            <span className="text-green-600 text-xl mt-0.5" aria-hidden="true">
              ✓
            </span>
            <div>
              <p className="text-green-800 font-semibold">
                Documento limpio — no se detectaron datos sensibles
              </p>
            </div>
          </div>

          <div className="bg-white border rounded-lg p-4 text-sm text-gray-600 space-y-1">
            <div>
              <span className="font-medium text-gray-700">Trace ID: </span>
              <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">
                {result.traceId}
              </code>
            </div>
            <div>
              <span className="font-medium text-gray-700">Versión de política: </span>
              <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">
                {result.policyVersion}
              </code>
            </div>
          </div>

          <button
            onClick={handleReset}
            className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium rounded-md transition-colors"
          >
            Escanear otro documento
          </button>
        </section>
      )}

      {/* ── Result: findings ── */}
      {pageState === 'result' && result && result.findings.length > 0 && (
        <section className="space-y-5">
          {/* Human review banner */}
          {result.requiresHumanReview && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 px-5 py-4 flex items-start gap-3">
              <span className="text-amber-500 text-xl mt-0.5" aria-hidden="true">
                ⚠
              </span>
              <div className="flex-1">
                <p className="text-amber-800 font-semibold mb-1">
                  Este documento requiere revisión humana antes de continuar.
                </p>
                <p className="text-amber-700 text-sm">
                  Trace ID:{' '}
                  <code className="bg-amber-100 px-1.5 py-0.5 rounded text-xs">
                    {result.traceId}
                  </code>
                </p>
                <Link
                  href="/review"
                  className="inline-block mt-2 text-sm text-amber-700 underline hover:text-amber-900"
                >
                  Ir a revisión pendiente →
                </Link>
              </div>
            </div>
          )}

          {/* Trace ID row */}
          <div className="flex items-center gap-3 text-sm text-gray-600">
            <span className="font-medium text-gray-700">Trace ID:</span>
            <code className="bg-gray-100 px-2 py-0.5 rounded text-xs">
              {result.traceId}
            </code>
            <button
              onClick={() => handleCopyTraceId(result.traceId)}
              className="text-xs text-blue-600 hover:text-blue-800 underline transition-colors"
              title="Copiar trace ID"
            >
              {copied ? 'Copiado' : 'Copiar'}
            </button>
            <span className="text-gray-400">·</span>
            <span className="font-medium text-gray-700">Política:</span>
            <code className="bg-gray-100 px-2 py-0.5 rounded text-xs">
              {result.policyVersion}
            </code>
          </div>

          {/* Document viewer */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-2">
              Documento con hallazgos resaltados
            </h2>
            <DocumentViewer
              text={result.documentText}
              findings={result.findings.map((f) => ({
                span_start: f.span_start,
                span_end: f.span_end,
                severity: f.severity as 'low' | 'medium' | 'high' | 'critical',
                detector: f.detector,
              }))}
            />
          </div>

          {/* Findings list */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              Hallazgos ({result.findings.length})
            </h2>
            <div className="space-y-3">
              {result.findings.map((f) => (
                <FindingCard
                  key={f.id}
                  finding={toFindingCardShape(f, result.documentText, result.traceId)}
                />
              ))}
            </div>
          </div>

          <button
            onClick={handleReset}
            className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium rounded-md transition-colors"
          >
            Escanear otro documento
          </button>
        </section>
      )}

      {/* ── Error ── */}
      {pageState === 'error' && (
        <section className="space-y-4">
          <div className="rounded-lg bg-red-50 border border-red-200 px-5 py-4 flex items-start gap-3">
            <span className="text-red-500 text-xl mt-0.5" aria-hidden="true">
              ✕
            </span>
            <div className="flex-1">
              <p className="text-red-800 font-semibold mb-1">Error al escanear el documento</p>
              <p className="text-red-700 text-sm">{errorMessage}</p>
            </div>
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleScan}
              disabled={!documentText.trim()}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm font-medium rounded-md transition-colors disabled:cursor-not-allowed"
            >
              Reintentar
            </button>
            <button
              onClick={handleReset}
              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium rounded-md transition-colors"
            >
              Nuevo escaneo
            </button>
          </div>

          {/* Show the form again so the user can edit */}
          <div className="bg-white rounded-lg shadow-sm border p-6">
            <label
              htmlFor="document-input-retry"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Documento
            </label>
            <textarea
              id="document-input-retry"
              rows={8}
              className="w-full border rounded-md p-3 text-sm font-mono text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
              placeholder="Pega el texto o documento a escanear..."
              value={documentText}
              onChange={(e) => setDocumentText(e.target.value)}
            />
          </div>
        </section>
      )}
    </main>
  )
}
