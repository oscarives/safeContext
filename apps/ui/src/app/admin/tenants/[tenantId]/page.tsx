'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { apiClient, TenantListItem, PolicyConfig, SIEMConfig } from '@/lib/api-client'
import { LoadingSpinner } from '@/components'
import { useToast } from '@/components/useToast'

const ENTITY_TYPES = [
  'EMAIL_ADDRESS', 'PHONE_NUMBER', 'PERSON', 'API_KEY', 'PASSWORD',
  'CREDIT_CARD', 'SSN', 'IBAN_CODE', 'IP_ADDRESS', 'MEDICAL_RECORD',
] as const

const DEFAULT_THRESHOLDS: Record<string, number> = {
  EMAIL_ADDRESS: 0.85, PHONE_NUMBER: 0.80, PERSON: 0.90, API_KEY: 0.95,
  PASSWORD: 0.95, CREDIT_CARD: 0.90, SSN: 0.85, IBAN_CODE: 0.85,
  IP_ADDRESS: 0.75, MEDICAL_RECORD: 0.85,
}

const DEFAULT_SEVERITIES: Record<string, string> = {
  EMAIL_ADDRESS: 'medium', PHONE_NUMBER: 'medium', PERSON: 'medium', API_KEY: 'critical',
  PASSWORD: 'critical', CREDIT_CARD: 'high', SSN: 'critical', IBAN_CODE: 'high',
  IP_ADDRESS: 'low', MEDICAL_RECORD: 'critical',
}

const SEVERITIES = ['low', 'medium', 'high', 'critical'] as const
const TABS = ['General', 'Policies', 'SIEM'] as const
type Tab = typeof TABS[number]

export default function TenantDetailPage() {
  const params = useParams()
  const tenantId = params.tenantId as string
  const [tenant, setTenant] = useState<TenantListItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('General')
  const { addToast } = useToast()

  // ── Form state ──
  const [name, setName] = useState('')
  const [plan, setPlan] = useState('free')
  const [email, setEmail] = useState('')
  const [isActive, setIsActive] = useState(true)
  const [scansPerDay, setScansPerDay] = useState('')
  const [docSize, setDocSize] = useState('')
  const [storageMb, setStorageMb] = useState('')
  const [rateLimitRpm, setRateLimitRpm] = useState('')
  const [retentionDays, setRetentionDays] = useState('')

  // Policy config
  const [confidenceOverrides, setConfidenceOverrides] = useState<Record<string, number>>({})
  const [severityOverrides, setSeverityOverrides] = useState<Record<string, string>>({})
  const [blockedTypes, setBlockedTypes] = useState<string[]>([])

  // SIEM config
  const [siemEnabled, setSiemEnabled] = useState(false)
  const [siemFormat, setSiemFormat] = useState<'cef' | 'leef' | 'json'>('cef')
  const [webhookUrl, setWebhookUrl] = useState('')
  const [webhookToken, setWebhookToken] = useState('')
  const [syslogHost, setSyslogHost] = useState('')
  const [syslogPort, setSyslogPort] = useState('514')
  const [syslogProtocol, setSyslogProtocol] = useState<'udp' | 'tcp'>('udp')
  const [siemTesting, setSiemTesting] = useState(false)

  const loadTenant = useCallback(async () => {
    try {
      setLoading(true)
      const t = await apiClient.getTenant(tenantId)
      setTenant(t)
      // Populate form
      setName(t.name)
      setPlan(t.plan)
      setEmail(t.contact_email ?? '')
      setIsActive(t.is_active)
      setScansPerDay(t.max_scans_per_day?.toString() ?? '')
      setDocSize(t.max_document_size?.toString() ?? '')
      setStorageMb(t.max_storage_mb?.toString() ?? '')
      setRateLimitRpm(t.rate_limit_rpm?.toString() ?? '')
      setRetentionDays(t.retention_days?.toString() ?? '365')
      // Policy
      const pc = t.policy_config
      setConfidenceOverrides(pc?.confidence_overrides ?? {})
      setSeverityOverrides(pc?.severity_overrides ?? {})
      setBlockedTypes(pc?.blocked_entity_types ?? [])
      // SIEM
      const sc = t.siem_config
      setSiemEnabled(sc?.enabled ?? false)
      setSiemFormat((sc?.format as 'cef' | 'leef' | 'json') ?? 'cef')
      setWebhookUrl(sc?.webhook_url ?? '')
      setWebhookToken(sc?.webhook_token ?? '')
      setSyslogHost(sc?.syslog_host ?? '')
      setSyslogPort(sc?.syslog_port?.toString() ?? '514')
      setSyslogProtocol((sc?.syslog_protocol as 'udp' | 'tcp') ?? 'udp')
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Failed to load tenant' })
    } finally {
      setLoading(false)
    }
  }, [tenantId, addToast])

  useEffect(() => { loadTenant() }, [loadTenant])

  const saveGeneral = async () => {
    setSaving(true)
    try {
      await apiClient.updateTenant(tenantId, {
        name,
        plan,
        contact_email: email || undefined,
        max_scans_per_day: scansPerDay ? parseInt(scansPerDay, 10) : null,
        max_document_size: docSize ? parseInt(docSize, 10) : null,
        max_storage_mb: storageMb ? parseInt(storageMb, 10) : null,
        rate_limit_rpm: rateLimitRpm ? parseInt(rateLimitRpm, 10) : null,
        retention_days: retentionDays ? parseInt(retentionDays, 10) : null,
      })
      addToast({ type: 'success', message: 'General settings saved' })
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Save failed' })
    } finally {
      setSaving(false)
    }
  }

  const savePolicy = async () => {
    setSaving(true)
    try {
      await apiClient.updateTenant(tenantId, {
        policy_config: {
          confidence_overrides: confidenceOverrides,
          severity_overrides: severityOverrides,
          blocked_entity_types: blockedTypes,
        },
      })
      addToast({ type: 'success', message: 'Policy configuration saved' })
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Save failed' })
    } finally {
      setSaving(false)
    }
  }

  const saveSIEM = async () => {
    setSaving(true)
    try {
      await apiClient.updateTenant(tenantId, {
        siem_config: {
          enabled: siemEnabled,
          format: siemFormat,
          webhook_url: webhookUrl || null,
          webhook_token: webhookToken || null,
          syslog_host: syslogHost || null,
          syslog_port: parseInt(syslogPort, 10) || 514,
          syslog_protocol: syslogProtocol,
        },
      })
      addToast({ type: 'success', message: 'SIEM configuration saved' })
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'Save failed' })
    } finally {
      setSaving(false)
    }
  }

  const testSIEM = async () => {
    setSiemTesting(true)
    try {
      const result = await apiClient.testSIEMConfig(tenantId)
      const parts = []
      if (result.webhook) parts.push('Webhook: OK')
      else parts.push('Webhook: Failed')
      if (result.syslog) parts.push('Syslog: OK')
      else parts.push('Syslog: Failed')
      addToast({
        type: result.webhook || result.syslog ? 'success' : 'error',
        message: `SIEM Test — ${parts.join(', ')}`,
      })
    } catch (err) {
      addToast({ type: 'error', message: err instanceof Error ? err.message : 'SIEM test failed' })
    } finally {
      setSiemTesting(false)
    }
  }

  if (loading) return <LoadingSpinner message="Loading tenant..." />
  if (!tenant) return <div className="text-red-600">Tenant not found</div>

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <a href="/admin/tenants" className="text-sm text-gray-500 hover:text-gray-700">&larr; Back</a>
        <h1 className="text-2xl font-bold text-gray-900">{tenant.name}</h1>
        <span className="text-sm text-gray-400 font-mono">{tenant.slug}</span>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="flex gap-6">
          {TABS.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        {activeTab === 'General' && (
          <GeneralTab
            name={name} setName={setName}
            plan={plan} setPlan={setPlan}
            email={email} setEmail={setEmail}
            isActive={isActive}
            scansPerDay={scansPerDay} setScansPerDay={setScansPerDay}
            docSize={docSize} setDocSize={setDocSize}
            storageMb={storageMb} setStorageMb={setStorageMb}
            rateLimitRpm={rateLimitRpm} setRateLimitRpm={setRateLimitRpm}
            retentionDays={retentionDays} setRetentionDays={setRetentionDays}
            saving={saving}
            onSave={saveGeneral}
          />
        )}

        {activeTab === 'Policies' && (
          <PolicyTab
            confidenceOverrides={confidenceOverrides} setConfidenceOverrides={setConfidenceOverrides}
            severityOverrides={severityOverrides} setSeverityOverrides={setSeverityOverrides}
            blockedTypes={blockedTypes} setBlockedTypes={setBlockedTypes}
            saving={saving}
            onSave={savePolicy}
          />
        )}

        {activeTab === 'SIEM' && (
          <SIEMTab
            enabled={siemEnabled} setEnabled={setSiemEnabled}
            format={siemFormat} setFormat={setSiemFormat}
            webhookUrl={webhookUrl} setWebhookUrl={setWebhookUrl}
            webhookToken={webhookToken} setWebhookToken={setWebhookToken}
            syslogHost={syslogHost} setSyslogHost={setSyslogHost}
            syslogPort={syslogPort} setSyslogPort={setSyslogPort}
            syslogProtocol={syslogProtocol} setSyslogProtocol={setSyslogProtocol}
            saving={saving}
            testing={siemTesting}
            onSave={saveSIEM}
            onTest={testSIEM}
          />
        )}
      </div>
    </div>
  )
}

// ── General Tab ─────────────────────────────────────────────────────────────

function GeneralTab(props: {
  name: string; setName: (v: string) => void
  plan: string; setPlan: (v: string) => void
  email: string; setEmail: (v: string) => void
  isActive: boolean
  scansPerDay: string; setScansPerDay: (v: string) => void
  docSize: string; setDocSize: (v: string) => void
  storageMb: string; setStorageMb: (v: string) => void
  rateLimitRpm: string; setRateLimitRpm: (v: string) => void
  retentionDays: string; setRetentionDays: (v: string) => void
  saving: boolean
  onSave: () => void
}) {
  const inputCls = "w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
  return (
    <div className="space-y-4 max-w-lg">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
        <input type="text" value={props.name} onChange={e => props.setName(e.target.value)} className={inputCls} />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Plan</label>
        <select value={props.plan} onChange={e => props.setPlan(e.target.value)} className={inputCls}>
          <option value="free">Free</option>
          <option value="starter">Starter</option>
          <option value="enterprise">Enterprise</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Contact Email</label>
        <input type="email" value={props.email} onChange={e => props.setEmail(e.target.value)} className={inputCls} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Max Scans/Day</label>
          <input type="number" value={props.scansPerDay} onChange={e => props.setScansPerDay(e.target.value)} min="1" className={inputCls} placeholder="Unlimited" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Max Doc Size (bytes)</label>
          <input type="number" value={props.docSize} onChange={e => props.setDocSize(e.target.value)} min="1" className={inputCls} placeholder="Unlimited" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Max Storage (MB)</label>
          <input type="number" value={props.storageMb} onChange={e => props.setStorageMb(e.target.value)} min="1" className={inputCls} placeholder="Unlimited" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Rate Limit (RPM)</label>
          <input type="number" value={props.rateLimitRpm} onChange={e => props.setRateLimitRpm(e.target.value)} min="1" className={inputCls} placeholder="Unlimited" />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">GDPR Retention (days)</label>
        <input type="number" value={props.retentionDays} onChange={e => props.setRetentionDays(e.target.value)} min="1" max="3650" className={inputCls} />
      </div>
      <button onClick={props.onSave} disabled={props.saving} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
        {props.saving ? 'Saving...' : 'Save General Settings'}
      </button>
    </div>
  )
}

// ── Policy Tab ──────────────────────────────────────────────────────────────

function PolicyTab(props: {
  confidenceOverrides: Record<string, number>; setConfidenceOverrides: (v: Record<string, number>) => void
  severityOverrides: Record<string, string>; setSeverityOverrides: (v: Record<string, string>) => void
  blockedTypes: string[]; setBlockedTypes: (v: string[]) => void
  saving: boolean
  onSave: () => void
}) {
  const addConfidence = (entity: string) => {
    props.setConfidenceOverrides({ ...props.confidenceOverrides, [entity]: DEFAULT_THRESHOLDS[entity] ?? 0.85 })
  }
  const removeConfidence = (entity: string) => {
    const next = { ...props.confidenceOverrides }
    delete next[entity]
    props.setConfidenceOverrides(next)
  }
  const addSeverity = (entity: string) => {
    props.setSeverityOverrides({ ...props.severityOverrides, [entity]: DEFAULT_SEVERITIES[entity] ?? 'medium' })
  }
  const removeSeverity = (entity: string) => {
    const next = { ...props.severityOverrides }
    delete next[entity]
    props.setSeverityOverrides(next)
  }
  const toggleBlocked = (entity: string) => {
    if (props.blockedTypes.includes(entity)) {
      props.setBlockedTypes(props.blockedTypes.filter(e => e !== entity))
    } else {
      props.setBlockedTypes([...props.blockedTypes, entity])
    }
  }

  const unusedForConfidence = ENTITY_TYPES.filter(e => !(e in props.confidenceOverrides))
  const unusedForSeverity = ENTITY_TYPES.filter(e => !(e in props.severityOverrides))

  return (
    <div className="space-y-8">
      {/* Confidence Overrides */}
      <section>
        <h3 className="text-sm font-semibold text-gray-800 mb-2">Confidence Threshold Overrides</h3>
        <p className="text-xs text-gray-500 mb-3">Override the minimum confidence score required for detection. Default values shown in parentheses.</p>
        {Object.entries(props.confidenceOverrides).map(([entity, value]) => (
          <div key={entity} className="flex items-center gap-3 mb-2">
            <span className="text-sm font-mono w-40">{entity}</span>
            <input
              type="range" min="0" max="1" step="0.05" value={value}
              onChange={e => props.setConfidenceOverrides({ ...props.confidenceOverrides, [entity]: parseFloat(e.target.value) })}
              className="flex-1"
            />
            <span className="text-sm w-12 text-right">{value.toFixed(2)}</span>
            <span className="text-xs text-gray-400">(default: {DEFAULT_THRESHOLDS[entity] ?? '?'})</span>
            <button onClick={() => removeConfidence(entity)} className="text-red-500 text-xs hover:text-red-700">Remove</button>
          </div>
        ))}
        {unusedForConfidence.length > 0 && (
          <select onChange={e => { if (e.target.value) addConfidence(e.target.value); e.target.value = '' }} className="text-sm border rounded px-2 py-1 mt-1">
            <option value="">+ Add override...</option>
            {unusedForConfidence.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
        )}
      </section>

      {/* Severity Overrides */}
      <section>
        <h3 className="text-sm font-semibold text-gray-800 mb-2">Severity Overrides</h3>
        <p className="text-xs text-gray-500 mb-3">Override the base severity for entity types. Default values shown in parentheses.</p>
        {Object.entries(props.severityOverrides).map(([entity, sev]) => (
          <div key={entity} className="flex items-center gap-3 mb-2">
            <span className="text-sm font-mono w-40">{entity}</span>
            <select
              value={sev}
              onChange={e => props.setSeverityOverrides({ ...props.severityOverrides, [entity]: e.target.value })}
              className="text-sm border rounded px-2 py-1"
            >
              {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <span className="text-xs text-gray-400">(default: {DEFAULT_SEVERITIES[entity] ?? '?'})</span>
            <button onClick={() => removeSeverity(entity)} className="text-red-500 text-xs hover:text-red-700">Remove</button>
          </div>
        ))}
        {unusedForSeverity.length > 0 && (
          <select onChange={e => { if (e.target.value) addSeverity(e.target.value); e.target.value = '' }} className="text-sm border rounded px-2 py-1 mt-1">
            <option value="">+ Add override...</option>
            {unusedForSeverity.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
        )}
      </section>

      {/* Blocked Entity Types */}
      <section>
        <h3 className="text-sm font-semibold text-gray-800 mb-2">Blocked Entity Types</h3>
        <p className="text-xs text-gray-500 mb-3">These entity types will always be blocked regardless of confidence score.</p>
        <div className="grid grid-cols-2 gap-2">
          {ENTITY_TYPES.map(entity => (
            <label key={entity} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={props.blockedTypes.includes(entity)}
                onChange={() => toggleBlocked(entity)}
                className="rounded border-gray-300"
              />
              <span className="font-mono text-xs">{entity}</span>
            </label>
          ))}
        </div>
      </section>

      <button onClick={props.onSave} disabled={props.saving} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
        {props.saving ? 'Saving...' : 'Save Policy Configuration'}
      </button>
    </div>
  )
}

// ── SIEM Tab ────────────────────────────────────────────────────────────────

function SIEMTab(props: {
  enabled: boolean; setEnabled: (v: boolean) => void
  format: 'cef' | 'leef' | 'json'; setFormat: (v: 'cef' | 'leef' | 'json') => void
  webhookUrl: string; setWebhookUrl: (v: string) => void
  webhookToken: string; setWebhookToken: (v: string) => void
  syslogHost: string; setSyslogHost: (v: string) => void
  syslogPort: string; setSyslogPort: (v: string) => void
  syslogProtocol: 'udp' | 'tcp'; setSyslogProtocol: (v: 'udp' | 'tcp') => void
  saving: boolean
  testing: boolean
  onSave: () => void
  onTest: () => void
}) {
  const inputCls = "w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
  return (
    <div className="space-y-6 max-w-lg">
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700">SIEM Integration</label>
        <button
          onClick={() => props.setEnabled(!props.enabled)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${props.enabled ? 'bg-indigo-600' : 'bg-gray-300'}`}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${props.enabled ? 'translate-x-6' : 'translate-x-1'}`} />
        </button>
        <span className="text-sm text-gray-500">{props.enabled ? 'Enabled' : 'Disabled'}</span>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Event Format</label>
        <select value={props.format} onChange={e => props.setFormat(e.target.value as 'cef' | 'leef' | 'json')} className={inputCls}>
          <option value="cef">CEF (Splunk, ArcSight)</option>
          <option value="leef">LEEF (QRadar)</option>
          <option value="json">JSON (Generic)</option>
        </select>
      </div>

      <fieldset className="border border-gray-200 rounded-lg p-4">
        <legend className="text-sm font-medium text-gray-700 px-2">Webhook</legend>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">URL</label>
            <input type="url" value={props.webhookUrl} onChange={e => props.setWebhookUrl(e.target.value)} className={inputCls} placeholder="https://siem.corp.net/api/events" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Bearer Token (optional)</label>
            <input type="password" value={props.webhookToken} onChange={e => props.setWebhookToken(e.target.value)} className={inputCls} placeholder="secret-token" />
          </div>
        </div>
      </fieldset>

      <fieldset className="border border-gray-200 rounded-lg p-4">
        <legend className="text-sm font-medium text-gray-700 px-2">Syslog</legend>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Host</label>
            <input type="text" value={props.syslogHost} onChange={e => props.setSyslogHost(e.target.value)} className={inputCls} placeholder="127.0.0.1" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Port</label>
              <input type="number" value={props.syslogPort} onChange={e => props.setSyslogPort(e.target.value)} min="1" max="65535" className={inputCls} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Protocol</label>
              <select value={props.syslogProtocol} onChange={e => props.setSyslogProtocol(e.target.value as 'udp' | 'tcp')} className={inputCls}>
                <option value="udp">UDP</option>
                <option value="tcp">TCP</option>
              </select>
            </div>
          </div>
        </div>
      </fieldset>

      <div className="flex gap-3">
        <button onClick={props.onSave} disabled={props.saving} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
          {props.saving ? 'Saving...' : 'Save SIEM Configuration'}
        </button>
        <button onClick={props.onTest} disabled={props.testing || !props.enabled} className="px-4 py-2 border border-indigo-300 text-indigo-600 rounded-lg text-sm font-medium hover:bg-indigo-50 disabled:opacity-50">
          {props.testing ? 'Testing...' : 'Test Connection'}
        </button>
      </div>
    </div>
  )
}
