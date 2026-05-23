'use client'
// NavBar.tsx — Top navigation bar with auth state.
// Items are shown to all authenticated users; role checks happen inside each page.

import { useSession } from '@/hooks/useSession'

const NAV_ITEMS = [
  { label: 'Dashboard', href: '/dashboard' },
  { label: 'Scan', href: '/scan' },
  { label: 'Review', href: '/review' },
  { label: 'Audit', href: '/audit' },
  // External link — opens in new tab; rel noopener for security
  { label: 'Grafana', href: 'http://localhost:3001', external: true },
] as const

function UserBadge() {
  const { user, isLoading } = useSession()

  if (isLoading) {
    // Minimal skeleton — avoids layout shift while session loads
    return (
      <div className="flex items-center gap-3 ml-auto">
        <div className="h-4 w-32 bg-gray-200 rounded animate-pulse" />
        <div className="h-8 w-20 bg-gray-200 rounded animate-pulse" />
      </div>
    )
  }

  if (!user) {
    // No session — middleware should have redirected; show nothing as fallback
    return null
  }

  // Display the user's highest-privilege role as a readable label.
  // Order matters: admin-equivalent users will typically have all roles.
  const ROLE_PRIORITY = ['policy_editor', 'reviewer', 'admin', 'viewer']
  const displayRole =
    ROLE_PRIORITY.find(r => user.roles.includes(r)) ??
    user.roles[0] ??
    'viewer'

  function handleLogout(e: React.MouseEvent) {
    e.preventDefault()
    window.location.href = '/api/auth/logout'
  }

  return (
    <div className="flex items-center gap-3 ml-auto">
      <div className="text-right">
        <p className="text-sm font-medium text-gray-800 leading-tight">{user.name || user.email}</p>
        <p className="text-xs text-gray-500 capitalize leading-tight">{displayRole}</p>
      </div>
      <button
        onClick={handleLogout}
        className="text-sm px-3 py-1.5 rounded-md border border-gray-300 text-gray-600 hover:bg-gray-100 transition-colors"
        aria-label="Sign out"
      >
        Sign out
      </button>
    </div>
  )
}

export default function NavBar() {
  return (
    <nav className="bg-white border-b px-8 py-3 flex items-center gap-6" aria-label="Main navigation">
      <a href="/" className="font-bold text-brand mr-2">SafeContext</a>
      {NAV_ITEMS.map(item =>
        'external' in item && item.external ? (
          <a
            key={item.href}
            href={item.href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-gray-600 hover:text-brand"
          >
            {item.label} ↗
          </a>
        ) : (
          <a key={item.href} href={item.href} className="text-sm text-gray-600 hover:text-brand">
            {item.label}
          </a>
        )
      )}
      <UserBadge />
    </nav>
  )
}
