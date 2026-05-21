// auth/callback/route.ts — Keycloak OIDC callback handler
// Keycloak redirects here with ?code=XXX after successful login.
// We exchange the code for tokens, set the session cookie, then redirect to /dashboard.

import { NextResponse } from 'next/server'
import { createSessionCookie } from '@/lib/session'

// KEYCLOAK_INTERNAL_URL is used server-side (token exchange inside Docker network).
// Falls back to the public URL for local dev without Docker.
const KEYCLOAK_URL =
  process.env.KEYCLOAK_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_KEYCLOAK_URL ??
  'http://localhost:8080'
const REALM = process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? 'safecontext'
const CLIENT_ID = process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? 'safecontext-ui'

/**
 * Reconstruct the public-facing origin from request headers.
 *
 * In Next.js standalone (Docker), request.url uses the internal bind
 * address (http://0.0.0.0:3000). We must use the Host header instead
 * so that redirect_uri matches what the browser originally sent to Keycloak,
 * and so error redirects go back to the browser-accessible URL.
 */
function getPublicOrigin(request: Request): string {
  const host =
    request.headers.get('x-forwarded-host') ||
    request.headers.get('host') ||
    'localhost:3000'
  const proto =
    request.headers.get('x-forwarded-proto') ||
    (host.includes('localhost') ? 'http' : 'https')
  return `${proto}://${host}`
}

export async function GET(request: Request) {
  const url = new URL(request.url)
  const code = url.searchParams.get('code')
  const publicOrigin = getPublicOrigin(request)

  if (!code) {
    // Keycloak returned an error or the user cancelled — send back to login
    return NextResponse.redirect(`${publicOrigin}/login?error=auth_cancelled`)
  }

  // The redirect_uri must exactly match what was sent in the initial auth request.
  // It is built from the public origin so it matches the browser's URL.
  const redirectUri = `${publicOrigin}/auth/callback`

  try {
    const tokenUrl = `${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token`

    const tokenResponse = await fetch(tokenUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        code,
        redirect_uri: redirectUri,
        client_id: CLIENT_ID,
      }),
    })

    if (!tokenResponse.ok) {
      const detail = await tokenResponse.text()
      console.error('[auth/callback] Token exchange failed:', tokenResponse.status, detail)
      return NextResponse.redirect(`${publicOrigin}/login?error=auth_failed`)
    }

    const tokens = (await tokenResponse.json()) as {
      access_token: string
      refresh_token: string
    }

    const sessionCookie = createSessionCookie(tokens.access_token, tokens.refresh_token)

    const response = NextResponse.redirect(`${publicOrigin}/dashboard`)
    response.cookies.set(sessionCookie.name, sessionCookie.value, sessionCookie.options)

    return response
  } catch (err) {
    console.error('[auth/callback] Unexpected error:', err)
    return NextResponse.redirect(`${publicOrigin}/login?error=auth_failed`)
  }
}
