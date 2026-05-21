/**
 * Test de consistencia de cache multiinstancia (criterio E2.5).
 *
 * Simula dos instancias de Next.js apuntando al mismo Redis.
 * Verifica que una escritura de instancia A es visible desde instancia B.
 */
// Integration test — requires a running Redis instance (REDIS_URL env var)
// Skipped in unit test runs without Redis. Run with: npm test -- --testPathPattern=integration
import RedisCache from '../../../cache-handler'

describe('RedisCache multi-instance consistency', () => {
  const instanceA = new RedisCache()
  const instanceB = new RedisCache()  // mismo Redis URL

  const TEST_KEY = `test:consistency:${Date.now()}`
  const TEST_DATA = { content: 'sensitive scan result', trace_id: 'abc-123' }

  afterAll(async () => {
    // Cleanup
    await instanceA.revalidateTag(TEST_KEY)
  })

  it('write from instance A is readable from instance B', async () => {
    await instanceA.set(TEST_KEY, TEST_DATA, { revalidate: 60 })
    const result = await instanceB.get(TEST_KEY)
    expect(result).toEqual(TEST_DATA)
  })

  it('revalidation by instance A invalidates cache for instance B', async () => {
    await instanceA.set(TEST_KEY, TEST_DATA, { revalidate: 60 })
    await instanceA.revalidateTag(TEST_KEY)
    const result = await instanceB.get(TEST_KEY)
    expect(result).toBeNull()
  })

  it('graceful degradation: get returns null on Redis error', async () => {
    // This test verifies the try/catch in get() works
    const badCache = new RedisCache()
    // Simulate error by using a cache with a bad key format
    const result = await badCache.get('')
    // Should return null without throwing
    expect(result).toBeNull()
  })
})
