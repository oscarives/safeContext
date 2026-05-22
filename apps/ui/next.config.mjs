// next.config.mjs — ES module format, compatible with Next.js 14+ without TypeScript runtime.
// Source of truth for Next.js configuration. next.config.ts removed for Docker build compatibility.
import { createRequire } from 'module'
const require = createRequire(import.meta.url)

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for Docker multi-stage build (copies only what's needed)
  output: 'standalone',

  // ESLint runs in CI (lint-python job). Skip during Docker build to avoid
  // dependency resolution differences between environments.
  eslint: { ignoreDuringBuilds: true },

  // Redis cache backend (ADR-002) — activo en todos los entornos.
  // Actualizado a CacheHandler v2 (Next.js 16): get() retorna { lastModified, value }
  // en lugar del dato crudo. Backward compatible con entradas Next.js 14 en Redis.
  cacheHandler: require.resolve('./cache-handler'),
  cacheMaxMemorySize: 0,  // Redis es la única fuente — sin caché en memoria

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
