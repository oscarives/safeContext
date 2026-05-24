'use client'

import { useState, useEffect, useCallback } from 'react'
import { apiClient, TenantListItem, TenantCreateRequest } from '@/lib/api-client'
import { LoadingSpinner, EmptyState, StatusBadge } from '@/components'
import { useToast } from '@/components/useToast'
import { SimpleConfirmModal as ConfirmModal } from '@/components/SimpleConfirmModal'

export default function TenantsPage() {
  const [tenants, setTenants] = useState<TenantListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [deactivateId, setDeactivateId] = useState<string | null>(null)
  const { addToast } = useToast()

  const loadTenants = useCallback(async () => {
    try {
      setLoading(true)
      const data = await apiClient.listTenants()
      setTenants(data)
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Failed to load tenants' })
    } finally {
      setLoading(false)
    }
  }, [addToast])

  useEffect(() => { loadTenants() }, [loadTenants])

  const handleCreate = async (data: TenantCreateRequest) => {
    try {
      await apiClient.createTenant(data)
      addToast({ type: 'success', message: 'Tenant created successfully' })
      setShowCreate(false)
      loadTenants()
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Failed to create tenant' })
    }
  }

  const handleDeactivate = async () => {
    if (!deactivateId) return
    try {
      await apiClient.deactivateTenant(deactivateId)
      addToast({ type: 'success', message: 'Tenant deactivated' })
      setDeactivateId(null)
      loadTenants()
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Failed to deactivate tenant' })
    }
  }

  if (loading) return <LoadingSpinner message="Loading tenants..." />

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Tenant Management</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
        >
          Create Tenant
        </button>
      </div>

      {tenants.length === 0 ? (
        <EmptyState title="No tenants configured yet" />
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Slug</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Plan</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Scans/Day</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Retention</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {tenants.map(t => (
                <tr key={t.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    <a href={`/admin/tenants/${t.id}`} className="text-indigo-600 hover:text-indigo-800">
                      {t.name}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500 font-mono">{t.slug}</td>
                  <td className="px-4 py-3 text-sm">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                      t.plan === 'enterprise' ? 'bg-purple-100 text-purple-800' :
                      t.plan === 'starter' ? 'bg-blue-100 text-blue-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {t.plan}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                      t.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                    }`}>
                      {t.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">{t.max_scans_per_day ?? 'Unlimited'}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{t.retention_days ?? 365}d</td>
                  <td className="px-4 py-3 text-sm">
                    {t.is_active && (
                      <button
                        onClick={() => setDeactivateId(t.id)}
                        className="text-red-600 hover:text-red-800 text-xs font-medium"
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <CreateTenantModal
          onClose={() => setShowCreate(false)}
          onCreate={handleCreate}
        />
      )}

      {/* Deactivate confirm */}
      {deactivateId && (
        <ConfirmModal
          title="Deactivate Tenant"
          message="This will deactivate the tenant. All associated data will be preserved but the tenant will no longer be accessible. Continue?"
          confirmLabel="Deactivate"
          onConfirm={handleDeactivate}
          onCancel={() => setDeactivateId(null)}
        />
      )}
    </div>
  )
}

function CreateTenantModal({
  onClose,
  onCreate,
}: {
  onClose: () => void
  onCreate: (data: TenantCreateRequest) => void
}) {
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [plan, setPlan] = useState('free')
  const [email, setEmail] = useState('')
  const [scansPerDay, setScansPerDay] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onCreate({
      name,
      slug,
      plan,
      contact_email: email || undefined,
      max_scans_per_day: scansPerDay ? parseInt(scansPerDay, 10) : undefined,
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Create Tenant</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              placeholder="Acme Corp"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Slug</label>
            <input
              type="text"
              value={slug}
              onChange={e => setSlug(e.target.value)}
              required
              pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
              placeholder="acme-corp"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Plan</label>
            <select
              value={plan}
              onChange={e => setPlan(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            >
              <option value="free">Free</option>
              <option value="starter">Starter</option>
              <option value="enterprise">Enterprise</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Contact Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              placeholder="admin@acme.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Max Scans/Day</label>
            <input
              type="number"
              value={scansPerDay}
              onChange={e => setScansPerDay(e.target.value)}
              min="1"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              placeholder="Unlimited"
            />
          </div>
          <div className="flex gap-3 justify-end pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700"
            >
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
