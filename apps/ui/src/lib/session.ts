// session.ts — Server-side session utilities (never imported in client components)
// The raw access_token is stored as the cookie value. We decode it locally
// (no signature verification) because the backend FastAPI verifies signatures
// on every API call. Decoding here is only to extract claims for the UI.

import { decodeJwt } from 'jose'
import { cookies } from 'next/headers'

export const SESSION_COOKIE_NAME = 'sc_session'

export interface SafeContextSession {
  sub: string           // Keycloak user ID
  name: string          // display name from token
  email: string
  roles: string[]       // realm_access.roles from JWT
  accessToken: string   // raw JWT — passed as Authorization: Bearer header
  refreshToken: string
  expiresAt: number     // unix timestamp (seconds)
}

// Decode the access token and build a SafeContextSession.
// Returns null if the token is missing, malformed, or expired.
function parseAccessToken(accessToken: string, refreshToken: string): SafeContextSession | null {
  try {
    const payload = decodeJwt(accessToken)

    const exp = typeof payload.exp === 'number' ? payload.exp : 0
    // Treat as expired if exp is in the past
    if (exp > 0 && exp < Math.floor(Date.now() / 1000)) {
      return null
    }

    const roles = (payload.realm_access as { roles?: string[] } | undefined)?.roles ?? []

    return {
      sub: typeof payload.sub === 'string' ? payload.sub : '',
      name: typeof payload.name === 'string' ? payload.name : (typeof payload.preferred_username === 'string' ? payload.preferred_username : ''),
      email: typeof payload.email === 'string' ? payload.email : '',
      roles,
      accessToken,
      refreshToken,
      expiresAt: exp,
    }
  } catch {
    // Malformed JWT — treat as no session
    return null
  }
}

// The cookie value is `<accessToken>.<refreshToken>` (dot-separated).
// We use a single cookie to keep the implementation simple; the access token
// itself already contains a dot, so we split on the LAST occurrence.
function encodeCookieValue(accessToken: string, refreshToken: string): string {
  // Separator is '||' (not present in base64url-encoded JWTs)
  return `${accessToken}||${refreshToken}`
}

function decodeCookieValue(value: string): { accessToken: string; refreshToken: string } | null {
  const idx = value.indexOf('||')
  if (idx === -1) return null
  return {
    accessToken: value.slice(0, idx),
    refreshToken: value.slice(idx + 2),
  }
}

// Read the sc_session cookie and return a parsed session, or null.
// Accepts an optional Request to read cookies from (useful in middleware);
// when omitted, reads from next/headers (Route Handlers & Server Components).
export async function getSession(request?: Request): Promise<SafeContextSession | null> {
  let cookieValue: string | undefined

  if (request) {
    cookieValue = request.headers
      .get('cookie')
      ?.split(';')
      .map(c => c.trim())
      .find(c => c.startsWith(`${SESSION_COOKIE_NAME}=`))
      ?.split('=')
      .slice(1)
      .join('=')
  } else {
    const cookieStore = await cookies()   // Next.js 15+: cookies() is async
    cookieValue = cookieStore.get(SESSION_COOKIE_NAME)?.value
  }

  if (!cookieValue) return null

  const parts = decodeCookieValue(decodeURIComponent(cookieValue))
  if (!parts) return null

  return parseAccessToken(parts.accessToken, parts.refreshToken)
}

const COOKIE_OPTIONS = {
  httpOnly: true,
  secure: process.env.NODE_ENV === 'production',
  sameSite: 'lax' as const,
  maxAge: 8 * 60 * 60, // 8 hours in seconds
  path: '/',
}

// Build a Set-Cookie descriptor for createing the session.
export function createSessionCookie(
  accessToken: string,
  refreshToken: string
): { name: string; value: string; options: typeof COOKIE_OPTIONS } {
  return {
    name: SESSION_COOKIE_NAME,
    value: encodeCookieValue(accessToken, refreshToken),
    options: COOKIE_OPTIONS,
  }
}

// Build a Set-Cookie descriptor that clears the session cookie.
export function clearSessionCookie(): { name: string; value: string; options: object } {
  return {
    name: SESSION_COOKIE_NAME,
    value: '',
    options: {
      ...COOKIE_OPTIONS,
      maxAge: 0,
    },
  }
}
