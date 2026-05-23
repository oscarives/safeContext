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
  // In production the ingress routes /api/v1/* to the backend directly.
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    return [
      {
        source: '/api/v1/:path*',
        destination: `${apiUrl}/api/v1/:path*`,
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
