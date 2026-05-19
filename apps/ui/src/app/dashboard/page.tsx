'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { apiClient, NotImplementedError } from '@/lib/api-client'
import { useSession } from '@/hooks/useSession'
import { StatusBadge, LoadingSpinner, EmptyState } from '@/components'

// ─── Types ────────────────────────────────────────────────────────────────────

interface HealthStatus {
  status: string
  postgres: string
  redis: string
  minio: string
}

interface OperationStats {
  total: number
  approved: number
  pending: number
  rejected: number
}

interface OperationRow {
  id: string
  digest: string
  status: 'pending' | 'completed' | 'escalated' | 'rejected'
  findings: number
  date: string
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Maps a roles array to a display label.
 * Priority: admin (all) > policy_editor > reviewer > viewer
 */
function roleLabel(roles: string[]): string {
  if (
    roles.includes('reviewer') &&
    roles.includes('policy_editor') &&
    roles.includes('viewer')
  ) {
    return 'Admin'
  }
  if (roles.includes('policy_editor')) return 'Policy Editor'
  if (roles.includes('reviewer')) return 'Reviewer'
  return 'Viewer'
}

function roleBadgeColor(label: string): string {
  switch (label) {
    case 'Admin':
      return 'bg-purple-100 text-purple-800'
    case 'Policy Editor':
      return 'bg-blue-100 text-blue-800'
    case 'Reviewer':
      return 'bg-amber-100 text-amber-800'
    default:
      return 'bg-gray-100 text-gray-600'
  }
}

function statusColor(s: string): string {
  return s === 'ok' ? 'text-green-600' : 'text-red-600'
}

function statusBg(s: string): string {
  return s === 'ok' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
}

function secondsAgo(ts: number): string {
  const delta = Math.floor((Date.now() - ts) / 1000)
  if (delta < 5) return 'ahora mismo'
  if (delta < 60) return `hace ${delta} seg`
  return `hace ${Math.floor(delta / 60)} min`
}

function truncateDigest(digest: string): string {
  return digest.length > 16 ? `${digest.slice(0, 8)}...${digest.slice(-4)}` : digest
}

const GRAFANA_URL =
  process.env.NEXT_PUBLIC_GRAFANA_URL ?? 'http://localhost:3001'

// ─── Sub-components ───────────────────────────────────────────────────────────

function HealthCard({
  label,
  value,
}: {
  label: string
  value: string | undefined
}) {
  const v = value ?? 'unknown'
  return (
    <div className={`border rounded-lg p-4 shadow-sm ${statusBg(v)}`}>
      <p className="text-xs text-gray-500 uppercase font-medium tracking-wide">{label}</p>
      <p className={`text-xl font-bold mt-1 ${statusColor(v)}`}>{v.toUpperCase()}</p>
    </div>
  )
}

interface StatCardProps {
  label: string
  value: string | number | undefined
  notAvailable: boolean
  highlight?: boolean
  highlightHref?: string
}

function StatCard({ label, value, notAvailable, highlight, highlightHref }: StatCardProps) {
  const bg = highlight && !notAvailable && Number(value) > 0
    ? 'bg-yellow-50 border-yellow-300'
    : 'bg-white border-gray-200'

  const content = (
    <div
      className={`border rounded-lg p-5 shadow-sm flex flex-col gap-1 transition-colors ${bg} ${
        highlight && highlightHref ? 'cursor-pointer hover:border-yellow-400' : ''
      }`}
      title={notAvailable ? 'Disponible próximamente' : undefined}
    >
      <p className="text-xs text-gray-500 uppercase font-medium tracking-wide">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${notAvailable ? 'text-gray-300' : 'text-gray-800'}`}>
        {notAvailable ? '—' : value}
      </p>
      {notAvailable && (
        <p className="text-xs text-gray-400 mt-1">Disponible próximamente</p>
      )}
      {highlight && !notAvailable && Number(value) > 0 && (
        <p className="text-xs text-yellow-700 font-medium mt-1">Requieren atención</p>
      )}
    </div>
  )

  if (highlight && highlightHref && !notAvailable && Number(value) > 0) {
    return <Link href={highlightHref}>{content}</Link>
  }
  return content
}

function QuickLinkCard({
  title,
  description,
  href,
  external,
}: {
  title: string
  description: string
  href: string
  external?: boolean
}) {
  const cls =
    'border rounded-lg p-5 bg-white shadow-sm hover:bg-gray-50 hover:border-brand transition-colors flex flex-col gap-1'
  if (external) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>
        <p className="font-semibold text-gray-800">{title}</p>
        <p className="text-sm text-gray-500">{description}</p>
        <p className="text-xs text-brand mt-auto pt-2">Abrir en nueva ventana &rarr;</p>
      </a>
    )
  }
  return (
    <Link href={href} className={cls}>
      <p className="font-semibold text-gray-800">{title}</p>
      <p className="text-sm text-gray-500">{description}</p>
      <p className="text-xs text-brand mt-auto pt-2">Ir &rarr;</p>
    </Link>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { user, isLoading: sessionLoading } = useSession()

  // Health state
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthError, setHealthError] = useState(false)
  const [healthTimestamp, setHealthTimestamp] = useState<number | null>(null)
  const [, setTick] = useState(0) // forces re-render for "hace X seg"

  // Operations state
  const [stats, setStats] = useState<OperationStats | null>(null)
  const [operations, setOperations] = useState<OperationRow[]>([])
  const [opsNotAvailable, setOpsNotAvailable] = useState(false)
  const [opsLoading, setOpsLoading] = useState(true)

  // ── Health fetch ──────────────────────────────────────────────────────────

  const fetchHealth = useCallback(async () => {
    try {
      const data = await apiClient.getHealth()
      setHealth(data as unknown as HealthStatus)
      setHealthError(false)
      setHealthTimestamp(Date.now())
    } catch {
      setHealthError(true)
    } finally {
      setHealthLoading(false)
    }
  }, [])

  // Initial fetch + 30-second auto-refresh
  useEffect(() => {
    fetchHealth()
    const interval = setInterval(fetchHealth, 30_000)
    return () => clearInterval(interval)
  }, [fetchHealth])

  // Tick every second to keep "hace X seg" fresh
  useEffect(() => {
    const t = setInterval(() => setTick(n => n + 1), 1000)
    return () => clearInterval(t)
  }, [])

  // ── Operations fetch ──────────────────────────────────────────────────────

  useEffect(() => {
    async function fetchOps() {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const data: any = await apiClient.getOperations()
        // If the endpoint ever returns real data, map it here
        setStats({
          total: data.total ?? 0,
          approved: data.approved ?? 0,
          pending: data.pending ?? 0,
          rejected: data.rejected ?? 0,
        })
        setOperations(data.items ?? [])
        setOpsNotAvailable(false)
      } catch (err) {
        if (err instanceof NotImplementedError) {
          setOpsNotAvailable(true)
        }
        // Other errors: also treat as not available to avoid crashes
        else {
          setOpsNotAvailable(true)
        }
      } finally {
        setOpsLoading(false)
      }
    }
    fetchOps()
  }, [])

  // ── Derived values ────────────────────────────────────────────────────────

  const displayRole = user ? roleLabel(user.roles) : null
  const isReviewer = user?.roles.includes('reviewer') ?? false

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <main className="p-8 max-w-6xl mx-auto space-y-10">

      {/* ── Header ── */}
      <section className="flex items-center justify-between flex-wrap gap-4">
        <div>
          {sessionLoading ? (
            <div className="h-8 w-48 bg-gray-100 animate-pulse rounded" />
          ) : (
            <h1 className="text-2xl font-bold text-gray-900">
              Bienvenido,{' '}
              <span className="text-brand">{user?.name ?? user?.email ?? 'Usuario'}</span>
            </h1>
          )}
          <p className="text-sm text-gray-500 mt-1">SafeContext — Gobierno de documentos para IA</p>
        </div>
        {displayRole && (
          <span
            className={`inline-block px-3 py-1 rounded-full text-sm font-semibold ${roleBadgeColor(displayRole)}`}
          >
            {displayRole}
          </span>
        )}
      </section>

      {/* ── System Health ── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-800">Estado del sistema</h2>
          <div className="text-xs text-gray-400 flex items-center gap-2">
            {healthTimestamp && (
              <span>Actualizado {secondsAgo(healthTimestamp)}</span>
            )}
            <button
              onClick={fetchHealth}
              className="text-brand hover:underline"
              aria-label="Refrescar health"
            >
              Refrescar
            </button>
          </div>
        </div>

        {healthLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner message="Comprobando servicios..." />
          </div>
        ) : healthError || !health ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-600 text-sm">
            No se puede conectar con la API. Comprueba que el backend está activo.
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <HealthCard label="Postgres" value={health.postgres} />
            <HealthCard label="Redis" value={health.redis} />
            <HealthCard label="MinIO" value={health.minio} />
            <HealthCard label="Overall" value={health.status} />
          </div>
        )}
      </section>

      {/* ── Stats last 24 h ── */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">
          Actividad — últimas 24 h
        </h2>

        {opsLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner message="Cargando estadísticas..." />
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Total scans"
              value={stats?.total}
              notAvailable={opsNotAvailable}
            />
            <StatCard
              label="Aprobados"
              value={stats?.approved}
              notAvailable={opsNotAvailable}
            />
            <StatCard
              label="Pendientes de revisión"
              value={stats?.pending}
              notAvailable={opsNotAvailable}
              highlight={isReviewer}
              highlightHref="/review"
            />
            <StatCard
              label="Rechazados"
              value={stats?.rejected}
              notAvailable={opsNotAvailable}
            />
          </div>
        )}
      </section>

      {/* ── Recent activity ── */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Actividad reciente</h2>

        {opsLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner message="Cargando operaciones..." />
          </div>
        ) : opsNotAvailable || operations.length === 0 ? (
          <EmptyState
            title="Sin historial disponible"
            description={
              opsNotAvailable
                ? 'El historial de operaciones estará disponible próximamente.'
                : 'Todavía no hay operaciones registradas.'
            }
            action={
              opsNotAvailable ? undefined : { label: 'Escanear documento', href: '/scan' }
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wide">
                  <th className="px-4 py-3 text-left font-medium">Fecha</th>
                  <th className="px-4 py-3 text-left font-medium">Digest</th>
                  <th className="px-4 py-3 text-left font-medium">Estado</th>
                  <th className="px-4 py-3 text-left font-medium">Findings</th>
                  <th className="px-4 py-3 text-left font-medium">Audit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {operations.map(op => (
                  <tr key={op.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{op.date}</td>
                    <td className="px-4 py-3 font-mono text-gray-700">
                      {truncateDigest(op.digest)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={op.status} />
                    </td>
                    <td className="px-4 py-3 text-gray-700">{op.findings}</td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/audit?trace=${op.id}`}
                        className="text-brand hover:underline text-xs"
                      >
                        Ver &rarr;
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Quick links ── */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Accesos rápidos</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <QuickLinkCard
            title="Escanear documento"
            description="Envía un documento para análisis de política"
            href="/scan"
          />
          <QuickLinkCard
            title="Revisiones pendientes"
            description="Aprueba o rechaza hallazgos escalados"
            href="/review"
          />
          <QuickLinkCard
            title="Audit Trail"
            description="Exporta evidencia firmada por trace ID"
            href="/audit"
          />
          <QuickLinkCard
            title="Métricas (Grafana)"
            description="Latencia, recall, error budget"
            href={`${GRAFANA_URL}/d/safecontext-overview`}
            external
          />
        </div>
      </section>

    </main>
  )
}
