/**
 * request-utils.ts — Server-side request helpers for Next.js Route Handlers.
 *
 * These utilities are safe to import in Route Handlers and Server Components.
 * Do NOT import in 'use client' files — they rely on server-only Request objects.
 */

/**
 * Reconstruct the public-facing origin from request headers.
 *
 * In Next.js standalone (Docker), request.url uses the internal bind address
 * (http://0.0.0.0:3000). Use the Host / X-Forwarded-Host header instead so that:
 *   - redirect_uri matches what the browser originally sent to Keycloak
 *   - error redirects go back to the browser-accessible URL
 *
 * nginx forwards `Host: localhost:8088` via `proxy_set_header Host $http_host`
 * (note: $http_host preserves the port, $host does not).
 */
export function getPublicOrigin(request: Request): string {
  const host =
    request.headers.get('x-forwarded-host') ||
    request.headers.get('host') ||
    'localhost:3000'
  const proto =
    request.headers.get('x-forwarded-proto') ||
    (host.includes('localhost') ? 'http' : 'https')
  return `${proto}://${host}`
}
