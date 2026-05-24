'use client'

import { useSession } from '@/hooks/useSession'
import { LoadingSpinner } from '@/components'

const ADMIN_ROLES = ['platform_admin', 'admin']

const SIDEBAR_ITEMS = [
  { label: 'Tenants', href: '/admin/tenants', icon: '🏢' },
  { label: 'Waivers', href: '/admin/waivers', icon: '📋' },
  { label: 'Retention', href: '/admin/retention', icon: '🗑️' },
] as const

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useSession()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner message="Loading admin..." />
      </div>
    )
  }

  if (!user || !ADMIN_ROLES.some(r => user.roles.includes(r))) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 max-w-md text-center">
          <h2 className="text-xl font-bold text-red-800 mb-2">Access Denied</h2>
          <p className="text-sm text-red-600 mb-4">
            You need the <strong>admin</strong> or <strong>platform_admin</strong> role to access this section.
          </p>
          <a
            href="/dashboard"
            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm font-medium"
          >
            Back to Dashboard
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-[calc(100vh-56px)]">
      {/* Sidebar */}
      <aside className="w-56 bg-white border-r border-gray-200 px-4 py-6 flex-shrink-0">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4 px-2">
          Administration
        </h2>
        <nav className="space-y-1">
          {SIDEBAR_ITEMS.map(item => (
            <a
              key={item.href}
              href={item.href}
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 rounded-md hover:bg-gray-100 hover:text-gray-900 transition-colors"
            >
              <span>{item.icon}</span>
              {item.label}
            </a>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 p-6 bg-gray-50">
        {children}
      </main>
    </div>
  )
}
