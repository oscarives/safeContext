'use client'

import { useEffect, useState } from 'react'

interface HealthStatus {
  status: string
  postgres: string
  redis: string
  minio: string
}

interface OperationStats {
  total: number
  pending: number
  completed: number
  escalated: number
  rejected: number
}

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/health')
      .then(r => r.json())
      .then(d => { setHealth(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const statusColor = (s: string) =>
    s === 'ok' ? 'text-green-600' : 'text-red-600'

  return (
    <main className="p-8 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-brand mb-6">SafeContext Dashboard</h1>

      {/* System Health */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-3">System Health</h2>
        {loading ? (
          <p className="text-gray-400">Loading...</p>
        ) : health ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {(['postgres', 'redis', 'minio'] as const).map(svc => (
              <div key={svc} className="border rounded-lg p-4 bg-white shadow-sm">
                <p className="text-xs text-gray-400 uppercase">{svc}</p>
                <p className={`text-xl font-bold mt-1 ${statusColor(health[svc])}`}>
                  {health[svc]?.toUpperCase()}
                </p>
              </div>
            ))}
            <div className="border rounded-lg p-4 bg-white shadow-sm">
              <p className="text-xs text-gray-400 uppercase">Overall</p>
              <p className={`text-xl font-bold mt-1 ${statusColor(health.status)}`}>
                {health.status?.toUpperCase()}
              </p>
            </div>
          </div>
        ) : (
          <p className="text-red-500">Unable to reach API</p>
        )}
      </section>

      {/* Quick links */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-3">Operations</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <a href="/review"
            className="border rounded-lg p-4 bg-white shadow-sm hover:bg-gray-50 transition-colors">
            <p className="font-medium">Pending Reviews</p>
            <p className="text-sm text-gray-500 mt-1">Approve or reject escalated findings</p>
          </a>
          <a href="/audit"
            className="border rounded-lg p-4 bg-white shadow-sm hover:bg-gray-50 transition-colors">
            <p className="font-medium">Audit Trail</p>
            <p className="text-sm text-gray-500 mt-1">Export evidence by trace ID</p>
          </a>
          <a href={`${process.env.NEXT_PUBLIC_GRAFANA_URL ?? 'http://localhost:3001'}/d/safecontext-overview`}
            target="_blank" rel="noopener noreferrer"
            className="border rounded-lg p-4 bg-white shadow-sm hover:bg-gray-50 transition-colors">
            <p className="font-medium">Metrics (Grafana)</p>
            <p className="text-sm text-gray-500 mt-1">Latency, recall, error budget</p>
          </a>
        </div>
      </section>
    </main>
  )
}
