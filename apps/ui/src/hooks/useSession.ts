'use client'
// useSession.ts — Client-side hook for reading the current user profile.
// Fetches /api/auth/session (which reads httpOnly cookie server-side).
// On 401 (expired or missing session) redirects to /login automatically.

import { useEffect, useState } from 'react'

export interface SessionUser {
  sub: string
  name: string
  email: string
  roles: string[]
  expiresAt: number
}

interface UseSessionResult {
  user: SessionUser | null
  isLoading: boolean
  hasRole: (role: string) => boolean
}

export function useSession(): UseSessionResult {
  const [user, setUser] = useState<SessionUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function fetchSession() {
      try {
        const res = await fetch('/api/auth/session', { credentials: 'same-origin' })

        if (res.status === 401) {
          // Session expired or missing — redirect to login.
          // Guard: don't redirect if already on /login (avoids infinite loop
          // since login page has no session by definition).
          if (window.location.pathname !== '/login') {
            window.location.href = '/login'
          }
          if (!cancelled) setIsLoading(false)
          return
        }

        if (!res.ok) {
          // Unexpected server error — treat as unauthenticated to be safe
          if (!cancelled) setUser(null)
          return
        }

        const data: SessionUser = await res.json()
        if (!cancelled) setUser(data)
      } catch {
        // Network error — keep loading false so UI can show an error state
        if (!cancelled) setUser(null)
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    fetchSession()
    return () => { cancelled = true }
  }, [])

  function hasRole(role: string): boolean {
    return user?.roles.includes(role) ?? false
  }

  return { user, isLoading, hasRole }
}
