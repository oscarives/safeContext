import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Use Redis as cache backend (ADR-002: Redis as ephemeral cache, not disk)
  cacheHandler: require.resolve('./cache-handler'),
  cacheMaxMemorySize: 0,  // disable in-memory cache entirely for multi-instance

  // API rewrites so UI can call /api/* → FastAPI
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? 'http://api:8000'}/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
