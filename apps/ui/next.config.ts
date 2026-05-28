import type { NextConfig } from 'next'

/**
 * SafeContext UI — Next.js configuration.
 *
 * Security headers are set in middleware.ts (CSP with per-request nonce)
 * and here (static headers like X-Frame-Options, HSTS, etc.).
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,

  // Proxy API calls to the FastAPI backend to avoid CORS in development.
  // Client code calls /api/<resource> (e.g. /api/operations).
  // This rewrite strips the /api prefix and adds /v1 to match FastAPI's router prefix.
  // Next.js applies afterFiles rewrites AFTER checking route handlers, so /api/auth/*
  // route handlers are NOT intercepted by this rule.
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    return [
      // /health → backend /health (Docker healthcheck endpoint, no /v1 prefix)
      {
        source: '/health',
        destination: `${apiUrl}/health`,
      },
      // /api/<resource> → backend /v1/<resource>
      // Next.js applies afterFiles rewrites AFTER route handlers, so /api/auth/*
      // route handlers (e.g. /api/auth/token) are NOT intercepted by this rule.
      {
        source: '/api/:path*',
        destination: `${apiUrl}/v1/:path*`,
      },
    ]
  },

  // Static security headers applied to all responses.
  // CSP is handled in middleware.ts with a per-request nonce.
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on',
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), interest-cohort=()',
          },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=31536000; includeSubDomains',
          },
        ],
      },
    ]
  },
}

export default nextConfig
