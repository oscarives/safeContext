// api/auth/logout/route.ts — OIDC-compliant logout
//
// Clears the local session cookie AND terminates the Keycloak SSO session.
// Without the Keycloak logout, the next "Sign in with SSO" click would
// auto-authenticate the user without showing the login form (SSO reuse).

import { NextResponse } from 'next/server'
import { clearSessionCookie, getSession } from '@/lib/session'
import { getPublicOrigin } from '@/lib/request-utils'

export async function GET(request: Request) {
  const publicOrigin = getPublicOrigin(request)
  const session = await getSession(request)

  // Keycloak OIDC end_session endpoint — the browser is redirected here so
  // Keycloak can terminate the SSO session for this user.
  const keycloakUrl = process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? 'http://localhost:8080'
  const realm = process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? 'safecontext'
  const logoutUrl = new URL(
    `${keycloakUrl}/realms/${realm}/protocol/openid-connect/logout`,
  )
  // After Keycloak terminates the session it redirects the browser here
  logoutUrl.searchParams.set('post_logout_redirect_uri', `${publicOrigin}/login`)

  if (session?.idToken) {
    // id_token_hint: precise — terminates only this specific session
    logoutUrl.searchParams.set('id_token_hint', session.idToken)
  } else {
    // Fallback: no id_token stored (v1 cookie) — terminate all sessions for this client
    logoutUrl.searchParams.set('client_id', 'safecontext-ui')
  }

  // Clear local session cookie before redirecting to Keycloak
  const cookie = clearSessionCookie()
  const response = NextResponse.redirect(logoutUrl.toString())
  response.cookies.set(
    cookie.name,
    cookie.value,
    cookie.options as Parameters<typeof response.cookies.set>[2],
  )
  return response
}
