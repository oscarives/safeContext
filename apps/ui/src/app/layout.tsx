import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'SafeContext',
  description: 'Document sanitization and governance for AI pipelines',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
