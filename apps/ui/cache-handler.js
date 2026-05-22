'use strict'
// Redis-backed Next.js cache handler (ADR-002)
// CommonJS format required by Next.js cacheHandler option (runs in Node.js, not Edge).

const { createClient } = require('redis')

let client = null

async function getClient() {
  if (!client) {
    client = createClient({ url: process.env.REDIS_URL || 'redis://redis:6379/0' })
    client.on('error', (err) => console.error('[cache-handler] Redis error:', err))
    await client.connect().catch((e) => {
      console.warn('[cache-handler] Redis connect failed, using no-op cache:', e.message)
      client = null
    })
  }
  return client
}

/**
 * Determine whether a cache entry should be stored in Redis.
 *
 * Pure function — no side effects, fully unit-testable without Redis.
 *
 * Next.js 14 App Router passes different data shapes depending on the entry type:
 *   { kind: 'APP_PAGE',  html, rscData, status? }  — App Router pages
 *   { kind: 'APP_ROUTE', body, status, headers }   — App Router route handlers
 *   { kind: 'PAGE',      html, pageData, status? } — Pages Router pages
 *   { kind: 'ROUTE',     body, status, headers }   — Pages Router API routes
 *   { kind: 'FETCH',     data: { status, … }, revalidate } — fetch() cache
 *   { kind: 'REDIRECT',  props }                   — redirect responses
 *   { kind: 'NOT_FOUND' }                          — not-found responses
 *
 * The original check `data.status === 404` only caught ROUTE/APP_ROUTE kinds.
 * NOT_FOUND, REDIRECT, and non-200 statuses on other kinds were missed,
 * causing 404/redirect responses to be cached and poison subsequent requests.
 *
 * @param {string} key   - The cache key (route path)
 * @param {unknown} data - The value Next.js wants to cache
 * @returns {boolean}    - true if the entry should be stored, false to skip
 */
function shouldCache(key, data) {
  // Auth routes must always render fresh — never cache them.
  if (key === '/login' || key.startsWith('/auth') || key.startsWith('/api/auth')) return false

  // Null or non-object data is invalid — nothing to store.
  if (data === null || typeof data !== 'object') return false

  // Explicit not-found kind — do not cache.
  if (data.kind === 'NOT_FOUND') return false

  // Redirect kind (from middleware NextResponse.redirect or redirects()) — do not cache.
  if (data.kind === 'REDIRECT') return false

  // Status-based filtering: cache only 200 responses.
  // Applies to APP_PAGE, APP_ROUTE, PAGE, ROUTE kinds.
  if (typeof data.status === 'number' && data.status !== 200) return false

  // FETCH kind: the HTTP status is nested inside data.data.
  if (data.kind === 'FETCH' && typeof data.data?.status === 'number' && data.data.status !== 200) {
    return false
  }

  return true
}

class RedisCache {
  async get(key) {
    try {
      const c = await getClient()
      if (!c) return null
      const data = await c.get(`nextjs:${key}`)
      return data ? JSON.parse(data) : null
    } catch { return null }
  }

  async set(key, data, ctx) {
    try {
      if (!shouldCache(key, data)) return
      const c = await getClient()
      if (!c) return
      const ttl = typeof ctx?.revalidate === 'number' ? ctx.revalidate : 3600
      await c.setEx(`nextjs:${key}`, ttl, JSON.stringify(data))
    } catch {}
  }

  async revalidateTag(tag) {
    try {
      const c = await getClient()
      if (!c) return
      const keys = await c.keys(`nextjs:*${tag}*`)
      if (keys.length > 0) await c.del(keys)
    } catch {}
  }
}

module.exports = RedisCache
module.exports.shouldCache = shouldCache  // named export for unit tests
