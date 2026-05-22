'use strict'
// Redis-backed Next.js cache handler (ADR-002)
// CommonJS format required by Next.js cacheHandler option (runs in Node.js, not Edge).
//
// Next.js 16 CacheHandler v2 API:
//   get(key)  → { lastModified: number, value: <data> } | null   (wrapping required)
//   set(key, data, ctx) → void
//   revalidateTag(tag)  → void
//
// Previous (Next.js 14) API returned raw data from get() without wrapping.
// Next.js 16 accesses entry.value — returning raw data causes "invalid cache entry undefined".

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
 * Next.js 16 App Router passes different data shapes depending on the entry type.
 * The `shouldCache` check operates on the inner `value` field (not the wrapper).
 *
 * @param {string} key   - The cache key (route path)
 * @param {unknown} data - The inner value Next.js wants to cache (not the wrapper)
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
  /**
   * Retrieve a cached entry.
   *
   * Next.js 16 expects: { lastModified: number, value: <data> } | null
   * (NOT the raw data — accessing .value on raw data gives undefined → invariant error)
   */
  async get(key) {
    try {
      const c = await getClient()
      if (!c) return null
      const raw = await c.get(`nextjs:${key}`)
      if (!raw) return null
      const stored = JSON.parse(raw)
      // Detect Next.js 16 format (already wrapped) vs legacy Next.js 14 format (raw data)
      if (
        stored !== null &&
        typeof stored === 'object' &&
        'value' in stored &&
        'lastModified' in stored
      ) {
        return stored  // already in { lastModified, value } format
      }
      // Legacy entry — wrap it so Next.js 16 can access .value correctly
      return { lastModified: Date.now(), value: stored }
    } catch { return null }
  }

  /**
   * Store a cache entry.
   *
   * `data` is the inner value (APP_PAGE, APP_ROUTE, FETCH, etc.).
   * We wrap it in { lastModified, value } for Next.js 16 compatibility.
   */
  async set(key, data, ctx) {
    try {
      if (!shouldCache(key, data)) return
      const c = await getClient()
      if (!c) return
      const ttl = typeof ctx?.revalidate === 'number' ? ctx.revalidate : 3600
      await c.setEx(`nextjs:${key}`, ttl, JSON.stringify({
        lastModified: Date.now(),
        value: data,
      }))
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
