// api/auth/logout/route.ts — Clears the session cookie and redirects to /login

import { NextResponse } from 'next/server'
import { clearSessionCookie } from '@/lib/session'
import { getPublicOrigin } from '@/lib/request-utils'

export async function GET(request: Request) {
  const publicOrigin = getPublicOrigin(request)
  const cookie = clearSessionCookie()
  const response = NextResponse.redirect(`${publicOrigin}/login`)
  response.cookies.set(cookie.name, cookie.value, cookie.options as Parameters<typeof response.cookies.set>[2])
  return response
}
