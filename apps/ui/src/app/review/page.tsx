'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ConfirmModal,
  EmptyState,
  FindingCard,
  LoadingSpinner,
  useToast,
} from '@/components'
import { apiClient, ForbiddenError, type PendingFinding } from '@/lib/api-client'
import { useSession } from '@/hooks/useSession'
import { pluralHallazgos } from '@/lib/format'

// ── Types ─────────────────────────────────────────────────────────────────────

interface PendingDecision {
  findingId: string
  action: 'approve' | 'reject'
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ReviewPage() {
  const { showToast } = useToast()
  const { user } = useSession()

  const [findings, setFindings] = useState<PendingFinding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterText, setFilterText] = useState('')
  const [pendingDecision, setPendingDecision] = useState<PendingDecision | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const loadFindings = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiClient.getPendingReviews()
      setFindings(data.items ?? [])
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadFindings()
  }, [loadFindings])

  // ── Derived: filtered list ────────────────────────────────────────────────

  const filteredFindings = useMemo(() => {
    const q = filterText.trim().toLowerCase()
    if (!q) return findings
    return findings.filter((f) => f.trace_id.toLowerCase().includes(q))
  }, [findings, filterText])

  // ── Handlers ─────────────────────────────────────────────────────────────

  function openApprove(findingId: string) {
    setPendingDecision({ findingId, action: 'approve' })
  }

  function openReject(findingId: string) {
    setPendingDecision({ findingId, action: 'reject' })
  }

  function cancelDecision() {
    if (!isSubmitting) setPendingDecision(null)
  }

  async function confirmDecision(justification: string) {
    if (!pendingDecision) return

    const { findingId, action } = pendingDecision
    setIsSubmitting(true)

    try {
      await apiClient.postReviewDecision(findingId, action, justification)

      setFindings((prev) => prev.filter((f) => f.finding_id !== findingId))

      const label = action === 'approve' ? 'aprobado' : 'rechazado'
      showToast(`Hallazgo ${label} correctamente.`, 'success')
      setPendingDecision(null)
    } catch (err) {
      if (err instanceof ForbiddenError) {
        showToast(
          'No tienes permiso para revisar esta operación (segregación de funciones).',
          'error'
        )
      } else {
        showToast(
          err instanceof Error ? err.message : 'Error al procesar la decisión.',
          'error'
        )
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  // ── Render states ─────────────────────────────────────────────────────────

  if (loading) {
    return (
      <main className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner />
      </main>
    )
  }

  if (error) {
    return (
      <main className="p-8 max-w-4xl mx-auto">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
          <p className="text-red-700 mb-4">{error}</p>
          <button
            onClick={loadFindings}
            className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 transition-colors"
          >
            Reintentar
          </button>
        </div>
      </main>
    )
  }

  if (findings.length === 0) {
    return (
      <main className="p-8 max-w-4xl mx-auto">
        <EmptyState
          title="Sin revisiones pendientes"
          description="Todos los documentos han sido revisados."
        />
      </main>
    )
  }

  // ── Active decision context (for modal title/description) ─────────────────

  const activeAction = pendingDecision?.action ?? 'approve'
  const modalTitle =
    activeAction === 'approve' ? 'Aprobar hallazgo' : 'Rechazar hallazgo'
  const modalDescription =
    activeAction === 'approve'
      ? 'Confirma que este hallazgo ha sido evaluado y puede aprobarse. Escribe una justificación.'
      : 'Confirma que este hallazgo debe ser rechazado. Escribe una justificación.'

  // ── Main render ───────────────────────────────────────────────────────────

  return (
    <main className="p-8 max-w-4xl mx-auto">
      {/* Header */}
      <h1 className="text-2xl font-bold mb-1">Revisión humana pendiente</h1>
      <p className="text-gray-500 mb-6">
        {pluralHallazgos(findings.length)} pendiente{findings.length !== 1 ? 's' : ''} de revisión
        {user ? (
          <span className="ml-2 text-xs text-gray-400">
            (usuario: <code className="bg-gray-100 px-1 rounded">{user.sub}</code>)
          </span>
        ) : null}
      </p>

      {/* Trace ID filter */}
      <div className="mb-6">
        <input
          type="text"
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          placeholder="Filtrar por Trace ID..."
          className="w-full max-w-sm px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand/30"
        />
        {filterText.trim() && (
          <p className="mt-1 text-xs text-gray-400">
            {pluralHallazgos(filteredFindings.length)} de {pluralHallazgos(findings.length)} coincide{filteredFindings.length !== 1 ? 'n' : ''}
          </p>
        )}
      </div>

      {/* Findings list */}
      {filteredFindings.length === 0 ? (
        <p className="text-gray-500 text-sm">
          Ningún hallazgo coincide con el filtro.
        </p>
      ) : (
        <div className="space-y-4">
          {filteredFindings.map((f) => (
            <div key={f.finding_id}>
              {/* Operation ID metadata (SoD transparency) */}
              <div className="text-xs text-gray-400 mb-1 px-1">
                Operación:{' '}
                <code className="bg-gray-100 px-1 rounded">{f.operation_id}</code>
              </div>
              <FindingCard
                finding={f}
                onApprove={openApprove}
                onReject={openReject}
              />
            </div>
          ))}
        </div>
      )}

      {/* Confirm modal */}
      <ConfirmModal
        isOpen={pendingDecision !== null}
        title={modalTitle}
        description={modalDescription}
        action={activeAction}
        onConfirm={confirmDecision}
        onCancel={cancelDecision}
        isLoading={isSubmitting}
      />
    </main>
  )
}
