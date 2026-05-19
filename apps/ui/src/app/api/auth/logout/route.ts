// api/auth/logout/route.ts — Clears the session cookie and redirects to /login

import { NextResponse } from 'next/server'
import { clearSessionCookie } from '@/lib/session'

export async function GET(request: Request) {
  const cookie = clearSessionCookie()
  const response = NextResponse.redirect(new URL('/login', request.url))
  response.cookies.set(cookie.name, cookie.value, cookie.options as Parameters<typeof response.cookies.set>[2])
  return response
}
