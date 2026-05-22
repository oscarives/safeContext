// api/auth/logout/route.ts — Clears the session cookie and redirects to /login

import { NextResponse } from 'next/server'
import { clearSessionCookie } from '@/lib/session'

export async function GET(request: Request) {
  // Use the Host/X-Forwarded-Host header to reconstruct the public origin.
  // request.url uses the server's internal bind address (http://0.0.0.0:3000
  // in Docker standalone mode) — same fix as auth/callback/route.ts.
  const host =
    request.headers.get('x-forwarded-host') ||
    request.headers.get('host') ||
    'localhost:3000'
  const proto =
    request.headers.get('x-forwarded-proto') ||
    (host.includes('localhost') ? 'http' : 'https')
  const publicOrigin = `${proto}://${host}`

  const cookie = clearSessionCookie()
  const response = NextResponse.redirect(`${publicOrigin}/login`)
  response.cookies.set(cookie.name, cookie.value, cookie.options as Parameters<typeof response.cookies.set>[2])
  return response
}
