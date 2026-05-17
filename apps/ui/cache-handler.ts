// cache-handler.ts — Redis-backed Next.js cache handler (ADR-002, ADR-011)
// NUNCA usar caché en disco en multi-instancia
import { createClient, RedisClientType } from 'redis'

let client: RedisClientType | null = null

async function getClient(): Promise<RedisClientType> {
  if (!client) {
    client = createClient({ url: process.env.REDIS_URL ?? 'redis://redis:6379/0' }) as RedisClientType
    client.on('error', (err) => console.error('[cache-handler] Redis error:', err))
    await client.connect()
  }
  return client
}

export default class RedisCache {
  async get(key: string) {
    try {
      const c = await getClient()
      const data = await c.get(`nextjs:${key}`)
      return data ? JSON.parse(data) : null
    } catch {
      return null  // graceful degradation
    }
  }

  async set(key: string, data: unknown, ctx: { revalidate?: number | false }) {
    try {
      const c = await getClient()
      const ttl = typeof ctx.revalidate === 'number' ? ctx.revalidate : 3600
      await c.setEx(`nextjs:${key}`, ttl, JSON.stringify(data))
    } catch {
      // graceful degradation — cache miss on next request
    }
  }

  async revalidateTag(tag: string) {
    try {
      const c = await getClient()
      const keys = await c.keys(`nextjs:*${tag}*`)
      if (keys.length > 0) await c.del(keys)
    } catch {
      // non-fatal
    }
  }
}
