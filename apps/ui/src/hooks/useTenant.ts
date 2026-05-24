'use client'
// useTenant.ts — Client-side hook for reading and switching the active tenant.
// Fetches the tenant list from /api/tenants and stores the active tenant in
// localStorage + React state. Falls back to the first available tenant.

import { useCallback, useEffect, useState } from 'react'

export interface TenantInfo {
  id: string
  name: string
  slug: string
  plan: string
}

interface UseTenantResult {
  tenant: TenantInfo | null
  tenants: TenantInfo[]
  isLoading: boolean
  switchTenant: (tenantId: string) => void
}

const STORAGE_KEY = 'sc_active_tenant'

export function useTenant(): UseTenantResult {
  const [tenants, setTenants] = useState<TenantInfo[]>([])
  const [tenant, setTenant] = useState<TenantInfo | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function fetchTenants() {
      try {
        const res = await fetch('/api/tenants', { credentials: 'same-origin' })
        if (!res.ok) {
          // If tenant list endpoint doesn't exist yet (single-tenant mode),
          // create a synthetic default tenant entry
          if (!cancelled) {
            const defaultTenant: TenantInfo = {
              id: '00000000-0000-0000-0000-000000000000',
              name: 'Default',
              slug: 'default',
              plan: 'free',
            }
            setTenants([defaultTenant])
            setTenant(defaultTenant)
          }
          return
        }

        const data: TenantInfo[] = await res.json()
        if (cancelled) return

        setTenants(data)

        // Restore last selected tenant from localStorage
        const savedId = localStorage.getItem(STORAGE_KEY)
        const saved = data.find(t => t.id === savedId)
        setTenant(saved ?? data[0] ?? null)
      } catch {
        // Network error — use default tenant
        if (!cancelled) {
          const defaultTenant: TenantInfo = {
            id: '00000000-0000-0000-0000-000000000000',
            name: 'Default',
            slug: 'default',
            plan: 'free',
          }
          setTenants([defaultTenant])
          setTenant(defaultTenant)
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    fetchTenants()
    return () => { cancelled = true }
  }, [])

  const switchTenant = useCallback((tenantId: string) => {
    const found = tenants.find(t => t.id === tenantId)
    if (found) {
      setTenant(found)
      localStorage.setItem(STORAGE_KEY, tenantId)
    }
  }, [tenants])

  return { tenant, tenants, isLoading, switchTenant }
}
