/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for Docker multi-stage build
  output: 'standalone',

  // Use Redis as cache backend (ADR-002)
  // cache-handler.js is compiled from cache-handler.ts during build
  cacheHandler: require.resolve('./cache-handler.js'),
  cacheMaxMemorySize: 0,

  // API rewrites: /api/* → FastAPI
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://api:8000'}/v1/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
