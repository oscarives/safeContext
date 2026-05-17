import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'SafeContext',
  description: 'Document sanitization and governance for AI pipelines',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 min-h-screen">
        <nav className="bg-white border-b px-8 py-3 flex items-center gap-6">
          <a href="/" className="font-bold text-brand">SafeContext</a>
          <a href="/dashboard" className="text-sm text-gray-600 hover:text-brand">Dashboard</a>
          <a href="/review" className="text-sm text-gray-600 hover:text-brand">Review</a>
          <a href="/audit" className="text-sm text-gray-600 hover:text-brand">Audit</a>
        </nav>
        {children}
      </body>
    </html>
  )
}
