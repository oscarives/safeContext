import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Required for Docker multi-stage build (copies only what's needed)
  output: 'standalone',

  // Use Redis as cache backend (ADR-002: Redis as ephemeral cache, not disk)
  // cache-handler.js is CommonJS — required by Next.js cacheHandler (runs in Node.js context).
  // cache-handler.ts was removed; .js is the authoritative runtime version.
  cacheHandler: require.resolve('./cache-handler'),
  cacheMaxMemorySize: 0,  // disable in-memory cache entirely for multi-instance

  // API rewrites so UI can call /api/* → FastAPI
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://api:8000'
    return [
      // Health check lives at /health on the backend (no /v1 prefix)
      {
        source: '/health',
        destination: `${apiBase}/health`,
      },
      // Note: /api/auth/* Route Handlers take precedence over this rewrite
      // because Next.js resolves file-system routes before applying rewrites.
      {
        source: '/api/:path*',
        destination: `${apiBase}/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
