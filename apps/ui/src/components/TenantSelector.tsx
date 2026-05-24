'use client'
// TenantSelector.tsx — Dropdown for switching between tenants.
// Only rendered when the user has access to multiple tenants.
// Falls back to showing the tenant name as a static badge in single-tenant mode.

import { useTenant } from '@/hooks/useTenant'

export function TenantSelector() {
  const { tenant, tenants, isLoading, switchTenant } = useTenant()

  if (isLoading) {
    return <div className="h-8 w-32 bg-gray-200 rounded animate-pulse" />
  }

  if (!tenant) return null

  // Single tenant — show as a static badge
  if (tenants.length <= 1) {
    return (
      <span className="text-xs px-2 py-1 rounded bg-gray-100 text-gray-600 font-medium">
        {tenant.name}
      </span>
    )
  }

  // Multiple tenants — show selector dropdown
  return (
    <select
      value={tenant.id}
      onChange={(e) => switchTenant(e.target.value)}
      className="text-sm px-2 py-1 rounded border border-gray-300 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-brand/50"
      aria-label="Select tenant"
    >
      {tenants.map((t) => (
        <option key={t.id} value={t.id}>
          {t.name} ({t.plan})
        </option>
      ))}
    </select>
  )
}
