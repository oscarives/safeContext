// middleware.ts — Route protection for SafeContext
// Public routes: /login, /auth/*, /api/auth/*
// All other routes require a valid (non-expired) sc_session cookie.
// Role-based access control is enforced in individual pages/actions, not here.

import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { decodeJwt } from 'jose'
import { SESSION_COOKIE_NAME } from '@/lib/session'

const PUBLIC_PATHS = ['/login', '/auth/', '/api/auth/']

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(prefix => pathname === prefix || pathname.startsWith(prefix))
}

function isSessionValid(cookieValue: string): boolean {
  try {
    // Cookie value is <accessToken>||<refreshToken>
    const idx = cookieValue.indexOf('||')
    if (idx === -1) return false
    const accessToken = cookieValue.slice(0, idx)
    const payload = decodeJwt(accessToken)
    const exp = typeof payload.exp === 'number' ? payload.exp : 0
    // Allow up to 0 seconds clock skew — if expired, treat as invalid
    return exp > Math.floor(Date.now() / 1000)
  } catch {
    return false
  }
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Allow public paths without any auth check
  if (isPublicPath(pathname)) {
    return NextResponse.next()
  }

  const cookieValue = request.cookies.get(SESSION_COOKIE_NAME)?.value

  if (!cookieValue || !isSessionValid(cookieValue)) {
    // Use request.nextUrl.clone() — NOT request.url — to build the redirect.
    // request.url uses the server's internal bind address (0.0.0.0:3000 in Docker).
    // request.nextUrl is correctly rewritten with the public host/protocol by Next.js.
    const loginUrl = request.nextUrl.clone()
    loginUrl.pathname = '/login'
    loginUrl.search = ''
    loginUrl.searchParams.set('next', pathname)
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
