import type { Metadata } from 'next'
import './globals.css'
import NavBar from '@/components/NavBar'
import { ToastProvider } from '@/components/ToastProvider'

export const metadata: Metadata = {
  title: 'SafeContext',
  description: 'Document sanitization and governance for AI pipelines',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 min-h-screen">
        <ToastProvider>
          <NavBar />
          {children}
        </ToastProvider>
      </body>
    </html>
  )
}
