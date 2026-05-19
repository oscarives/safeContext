// auth/callback/route.ts — Keycloak OIDC callback handler
// Keycloak redirects here with ?code=XXX after successful login.
// We exchange the code for tokens, set the session cookie, then redirect to /dashboard.

import { NextResponse } from 'next/server'
import { createSessionCookie } from '@/lib/session'

const KEYCLOAK_URL = process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? 'http://localhost:8080'
const REALM = process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? 'safecontext'
const CLIENT_ID = process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? 'safecontext-ui'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const code = url.searchParams.get('code')

  if (!code) {
    // Keycloak returned an error or the user cancelled — send back to login
    return NextResponse.redirect(new URL('/login?error=auth_cancelled', request.url))
  }

  // The redirect_uri must exactly match what was sent in the initial auth request
  const origin = url.origin
  const redirectUri = `${origin}/auth/callback`

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
      return NextResponse.redirect(new URL('/login?error=auth_failed', request.url))
    }

    const tokens = (await tokenResponse.json()) as {
      access_token: string
      refresh_token: string
    }

    const sessionCookie = createSessionCookie(tokens.access_token, tokens.refresh_token)

    const response = NextResponse.redirect(new URL('/dashboard', request.url))
    response.cookies.set(sessionCookie.name, sessionCookie.value, sessionCookie.options)

    return response
  } catch (err) {
    console.error('[auth/callback] Unexpected error:', err)
    return NextResponse.redirect(new URL('/login?error=auth_failed', request.url))
  }
}
