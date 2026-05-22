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

  // Redis cache backend (ADR-002) — DESHABILITADO temporalmente.
  // El cache handler fue escrito para Next.js 14. Next.js 16 cambió
  // el formato de los cache entries (nueva API de CacheHandler).
  // Error: "Invariant app-page handler received invalid cache entry undefined"
  // TODO: actualizar cache-handler.js a la nueva API de Next.js 16 (CacheHandler v2)
  // antes de re-habilitar en producción multi-instancia.

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
