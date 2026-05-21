'use strict'
// Redis-backed Next.js cache handler (ADR-002)
// CommonJS format required by Next.js cacheHandler option

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
      // Never cache auth routes — they must render fresh on every request
      if (key === '/login' || key.startsWith('/auth') || key.startsWith('/api/auth')) return
      // Never cache 404 responses — stale not-found entries poison the cache
      if (data && data.status === 404) return
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
