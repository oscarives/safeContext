'use client'

import { useState, useEffect, useCallback } from 'react'
import { useSession } from '@/hooks/useSession'
import { apiClient, WaiverItem, WaiverCreateRequest } from '@/lib/api-client'
import { LoadingSpinner, EmptyState } from '@/components'
import { useToast } from '@/components/useToast'
import { SimpleConfirmModal as ConfirmModal } from '@/components/SimpleConfirmModal'
import { RelativeTime } from '@/components/RelativeTime'

const PRIVILEGED_ROLES = ['policy_editor', 'admin']

export default function WaiversPage() {
  const { user } = useSession()
  const [waivers, setWaivers] = useState<WaiverItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [revokeId, setRevokeId] = useState<string | null>(null)
  const { addToast } = useToast()

  const canManage = user ? PRIVILEGED_ROLES.some(r => user.roles.includes(r)) : false

  const loadWaivers = useCallback(async () => {
    try {
      setLoading(true)
      const data = await apiClient.listWaivers()
      setWaivers(data)
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Failed to load waivers' })
    } finally {
      setLoading(false)
    }
  }, [addToast])

  useEffect(() => { loadWaivers() }, [loadWaivers])

  const handleCreate = async (data: WaiverCreateRequest) => {
    try {
      await apiClient.createWaiver(data)
      addToast({ type: 'success', message: 'Waiver created successfully' })
      setShowCreate(false)
      loadWaivers()
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Failed to create waiver' })
    }
  }

  const handleRevoke = async () => {
    if (!revokeId) return
    try {
      await apiClient.revokeWaiver(revokeId)
      addToast({ type: 'success', message: 'Waiver revoked' })
      setRevokeId(null)
      loadWaivers()
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Failed to revoke waiver' })
    }
  }

  if (loading) return <LoadingSpinner message="Loading waivers..." />

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Policy Waivers</h1>
          <p className="text-sm text-gray-500 mt-1">Exceptions to detection policies for known false positives</p>
        </div>
        {canManage && (
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
          >
            Create Waiver
          </button>
        )}
      </div>

      {waivers.length === 0 ? (
        <EmptyState title="No active waivers" />
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Rule ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Entity Pattern</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Justification</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Expires</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                {canManage && <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {waivers.map(w => (
                <tr key={w.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-mono text-gray-900">{w.rule_id}</td>
                  <td className="px-4 py-3 text-sm font-mono text-gray-600 max-w-[200px] truncate">{w.entity_pattern}</td>
                  <td className="px-4 py-3 text-sm text-gray-600 max-w-[250px] truncate">{w.justification}</td>
                  <td className="px-4 py-3 text-sm">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                      w.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                    }`}>
                      {w.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {w.expires_at ? <RelativeTime ts={new Date(w.expires_at).getTime()} /> : 'Never'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    <RelativeTime ts={new Date(w.created_at).getTime()} />
                  </td>
                  {canManage && (
                    <td className="px-4 py-3 text-sm">
                      {w.status === 'active' && (
                        <button
                          onClick={() => setRevokeId(w.id)}
                          className="text-red-600 hover:text-red-800 text-xs font-medium"
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && <CreateWaiverModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />}

      {revokeId && (
        <ConfirmModal
          title="Revoke Waiver"
          message="This will revoke the waiver and the associated findings will be detected again in future scans. Continue?"
          confirmLabel="Revoke"
          onConfirm={handleRevoke}
          onCancel={() => setRevokeId(null)}
        />
      )}
    </div>
  )
}

function CreateWaiverModal({
  onClose,
  onCreate,
}: {
  onClose: () => void
  onCreate: (data: WaiverCreateRequest) => void
}) {
  const [ruleId, setRuleId] = useState('')
  const [pattern, setPattern] = useState('')
  const [justification, setJustification] = useState('')
  const [expiresAt, setExpiresAt] = useState('')
  const [regexError, setRegexError] = useState('')

  const validateRegex = (val: string) => {
    setPattern(val)
    try {
      new RegExp(val)
      setRegexError('')
    } catch {
      setRegexError('Invalid regular expression')
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (regexError) return
    onCreate({
      rule_id: ruleId,
      entity_pattern: pattern,
      justification,
      expires_at: expiresAt || undefined,
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Create Waiver</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Rule ID</label>
            <input
              type="text" value={ruleId} onChange={e => setRuleId(e.target.value)} required
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
              placeholder="regex_connection_string"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Entity Pattern (regex)</label>
            <input
              type="text" value={pattern} onChange={e => validateRegex(e.target.value)} required
              className={`w-full px-3 py-2 border rounded-md text-sm font-mono ${regexError ? 'border-red-300' : 'border-gray-300'}`}
              placeholder="localhost.*testdb"
            />
            {regexError && <p className="text-xs text-red-500 mt-1">{regexError}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Justification (min 20 chars)</label>
            <textarea
              value={justification} onChange={e => setJustification(e.target.value)} required minLength={20}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" rows={3}
              placeholder="This connection string is for the local development database only..."
            />
            <p className="text-xs text-gray-400 mt-1">{justification.length}/20 characters minimum</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Expires At (optional)</label>
            <input
              type="datetime-local" value={expiresAt} onChange={e => setExpiresAt(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
          <div className="flex gap-3 justify-end pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50">Cancel</button>
            <button type="submit" disabled={!!regexError || justification.length < 20} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">Create</button>
          </div>
        </form>
      </div>
    </div>
  )
}
