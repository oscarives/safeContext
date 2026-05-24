'use client'

import { useState, useEffect, useCallback } from 'react'
import { apiClient, TenantListItem, CertificateSummary, PurgeResult } from '@/lib/api-client'
import { LoadingSpinner, EmptyState } from '@/components'
import { useToast } from '@/components/useToast'
import { SimpleConfirmModal as ConfirmModal } from '@/components/SimpleConfirmModal'
import { RelativeTime } from '@/components/RelativeTime'

export default function RetentionPage() {
  const [tenants, setTenants] = useState<TenantListItem[]>([])
  const [selectedTenant, setSelectedTenant] = useState<string>('')
  const [retentionDays, setRetentionDays] = useState('')
  const [certificates, setCertificates] = useState<CertificateSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingCerts, setLoadingCerts] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showPurgeConfirm, setShowPurgeConfirm] = useState(false)
  const [purgeResult, setPurgeResult] = useState<PurgeResult | null>(null)
  const [certDetail, setCertDetail] = useState<Record<string, unknown> | null>(null)
  const { addToast } = useToast()

  const loadTenants = useCallback(async () => {
    try {
      setLoading(true)
      const data = await apiClient.listTenants()
      setTenants(data)
      if (data.length > 0) {
        setSelectedTenant(data[0].id)
        setRetentionDays(data[0].retention_days?.toString() ?? '365')
      }
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Failed to load tenants' })
    } finally {
      setLoading(false)
    }
  }, [addToast])

  useEffect(() => { loadTenants() }, [loadTenants])

  const loadCertificates = useCallback(async () => {
    if (!selectedTenant) return
    try {
      setLoadingCerts(true)
      const data = await apiClient.listCertificates(selectedTenant)
      setCertificates(data)
    } catch {
      setCertificates([])
    } finally {
      setLoadingCerts(false)
    }
  }, [selectedTenant])

  useEffect(() => { loadCertificates() }, [loadCertificates])

  const handleTenantChange = (tenantId: string) => {
    setSelectedTenant(tenantId)
    const t = tenants.find(t => t.id === tenantId)
    setRetentionDays(t?.retention_days?.toString() ?? '365')
    setPurgeResult(null)
    setCertDetail(null)
  }

  const saveRetention = async () => {
    setSaving(true)
    try {
      await apiClient.updateTenant(selectedTenant, {
        retention_days: parseInt(retentionDays, 10) || 365,
      })
      addToast({ type: 'success', message: 'Retention period saved' })
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Save failed' })
    } finally {
      setSaving(false)
    }
  }

  const executePurge = async () => {
    setShowPurgeConfirm(false)
    try {
      const result = await apiClient.triggerPurge(selectedTenant)
      setPurgeResult(result)
      if (result.purged) {
        addToast({ type: 'success', message: `Purge complete: ${result.operations_deleted} operations deleted` })
        loadCertificates()
      } else {
        addToast({ type: 'success', message: 'No expired operations found — nothing to purge' })
      }
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Purge failed' })
    }
  }

  const viewCertificate = async (certId: string) => {
    try {
      const detail = await apiClient.getCertificate(selectedTenant, certId)
      setCertDetail(detail.data)
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Failed to load certificate' })
    }
  }

  if (loading) return <LoadingSpinner message="Loading..." />

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">GDPR Retention</h1>
      <p className="text-sm text-gray-500 mb-6">Configure data retention periods and manage deletion certificates</p>

      {/* Tenant selector */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-1">Tenant</label>
        <select
          value={selectedTenant}
          onChange={e => handleTenantChange(e.target.value)}
          className="w-64 px-3 py-2 border border-gray-300 rounded-md text-sm"
        >
          {tenants.map(t => (
            <option key={t.id} value={t.id}>{t.name} ({t.slug})</option>
          ))}
        </select>
      </div>

      {/* Configuration */}
      <div className="bg-white rounded-lg border border-gray-200 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Retention Configuration</h2>
        <div className="flex items-end gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Retention Period (days)</label>
            <input
              type="number"
              value={retentionDays}
              onChange={e => setRetentionDays(e.target.value)}
              min="1"
              max="3650"
              className="w-32 px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
          <button
            onClick={saveRetention}
            disabled={saving}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          Operations older than {retentionDays || 365} days will be eligible for purge.
        </p>
      </div>

      {/* Manual Purge */}
      <div className="bg-white rounded-lg border border-gray-200 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-2">Manual Purge</h2>
        <p className="text-sm text-gray-500 mb-4">
          Trigger a manual GDPR purge for this tenant. This will permanently delete expired operations
          and generate a signed deletion certificate.
        </p>
        <button
          onClick={() => setShowPurgeConfirm(true)}
          className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700"
        >
          Execute Purge
        </button>

        {purgeResult && (
          <div className={`mt-4 p-4 rounded-lg border ${purgeResult.purged ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'}`}>
            <h3 className="text-sm font-semibold mb-2">{purgeResult.purged ? 'Purge Completed' : 'Nothing to Purge'}</h3>
            {purgeResult.purged && (
              <div className="text-sm text-gray-700 space-y-1">
                <p>Operations deleted: <strong>{purgeResult.operations_deleted}</strong></p>
                <p>Findings deleted: <strong>{purgeResult.findings_deleted}</strong></p>
                <p>Redactions deleted: <strong>{purgeResult.redactions_deleted}</strong></p>
                <p>Artifacts deleted: <strong>{purgeResult.artifacts_deleted}</strong></p>
                {purgeResult.certificate_id && (
                  <p>Certificate ID: <code className="text-xs bg-gray-100 px-1 rounded">{purgeResult.certificate_id}</code></p>
                )}
                <p>Certificate stored in WORM: {purgeResult.certificate_stored ? 'Yes' : 'No'}</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Certificates */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Deletion Certificates</h2>

        {loadingCerts ? (
          <LoadingSpinner message="Loading certificates..." />
        ) : certificates.length === 0 ? (
          <EmptyState title="No deletion certificates found for this tenant" />
        ) : (
          <div className="space-y-2">
            {certificates.map(cert => (
              <div key={cert.certificate_id} className="flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50">
                <div>
                  <span className="text-sm font-mono text-gray-800">{cert.certificate_id}</span>
                  <span className="text-xs text-gray-400 ml-3">
                    {cert.last_modified && <RelativeTime ts={new Date(cert.last_modified).getTime()} />}
                  </span>
                  <span className="text-xs text-gray-400 ml-2">({cert.size} bytes)</span>
                </div>
                <button
                  onClick={() => viewCertificate(cert.certificate_id)}
                  className="text-sm text-indigo-600 hover:text-indigo-800"
                >
                  View
                </button>
              </div>
            ))}
          </div>
        )}

        {certDetail && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-gray-700">Certificate Detail</h3>
              <button onClick={() => setCertDetail(null)} className="text-xs text-gray-400 hover:text-gray-600">Close</button>
            </div>
            <pre className="bg-gray-900 text-green-400 text-xs p-4 rounded-lg overflow-auto max-h-80">
              {JSON.stringify(certDetail, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {showPurgeConfirm && (
        <ConfirmModal
          title="Confirm GDPR Purge"
          message={`This will permanently delete all operations older than ${retentionDays || 365} days for this tenant. This action cannot be undone. A signed deletion certificate will be generated and stored in WORM storage.`}
          confirmLabel="Execute Purge"
          onConfirm={executePurge}
          onCancel={() => setShowPurgeConfirm(false)}
        />
      )}
    </div>
  )
}
