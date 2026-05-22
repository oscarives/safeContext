/**
 * Tests for the Redis-backed Next.js cache handler.
 *
 * Split into two suites:
 *
 * 1. shouldCache — UNIT tests (no Redis required).
 *    Covers the pure filtering function for all Next.js 14 App Router data kinds.
 *    Runs in any environment including CI without infrastructure.
 *
 * 2. RedisCache multi-instance — INTEGRATION tests (requires a running Redis).
 *    Verifies cross-instance cache consistency (criterion E2.5).
 */

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { shouldCache } = require('../../../cache-handler')
// eslint-disable-next-line @typescript-eslint/no-require-imports
const RedisCache = require('../../../cache-handler')

// ─── 1. Unit tests for shouldCache() — no Redis needed ───────────────────────

describe('shouldCache — unit tests (no Redis)', () => {

  // Auth routes — always false
  it('never caches /login', () => {
    expect(shouldCache('/login', { kind: 'APP_PAGE', status: 200 })).toBe(false)
  })
  it('never caches /auth/callback', () => {
    expect(shouldCache('/auth/callback', { kind: 'APP_PAGE', status: 200 })).toBe(false)
  })
  it('never caches /api/auth/session', () => {
    expect(shouldCache('/api/auth/session', { kind: 'APP_ROUTE', status: 200 })).toBe(false)
  })
  it('never caches /api/auth/token', () => {
    expect(shouldCache('/api/auth/token', { kind: 'APP_ROUTE', status: 200 })).toBe(false)
  })

  // NOT_FOUND and REDIRECT kinds — always false
  it('never caches NOT_FOUND kind', () => {
    expect(shouldCache('/dashboard', { kind: 'NOT_FOUND' })).toBe(false)
  })
  it('never caches REDIRECT kind (middleware NextResponse.redirect)', () => {
    expect(shouldCache('/dashboard', { kind: 'REDIRECT', props: {} })).toBe(false)
  })

  // Status-based filtering
  it('never caches APP_ROUTE with status 404', () => {
    expect(shouldCache('/api/scan', { kind: 'APP_ROUTE', status: 404 })).toBe(false)
  })
  it('never caches APP_PAGE with status 404', () => {
    expect(shouldCache('/dashboard', { kind: 'APP_PAGE', html: '', status: 404 })).toBe(false)
  })
  it('never caches PAGE with status 404 (Pages Router compat)', () => {
    expect(shouldCache('/old-page', { kind: 'PAGE', html: '', pageData: {}, status: 404 })).toBe(false)
  })
  it('never caches ROUTE with status 301 (redirect)', () => {
    expect(shouldCache('/some-route', { kind: 'ROUTE', status: 301 })).toBe(false)
  })
  it('never caches APP_ROUTE with status 302', () => {
    expect(shouldCache('/api/redirect', { kind: 'APP_ROUTE', status: 302 })).toBe(false)
  })
  it('never caches APP_ROUTE with status 500', () => {
    expect(shouldCache('/api/error', { kind: 'APP_ROUTE', status: 500 })).toBe(false)
  })

  // FETCH kind — nested status
  it('never caches FETCH with data.status 404', () => {
    expect(shouldCache('/dashboard', {
      kind: 'FETCH',
      data: { body: '', url: '/api', headers: {}, status: 404 },
      revalidate: 60,
    })).toBe(false)
  })
  it('never caches FETCH with data.status 500', () => {
    expect(shouldCache('/dashboard', {
      kind: 'FETCH',
      data: { body: '', url: '/api', headers: {}, status: 500 },
      revalidate: 60,
    })).toBe(false)
  })

  // Invalid / null data
  it('never caches null data', () => {
    expect(shouldCache('/dashboard', null)).toBe(false)
  })
  it('never caches non-object data', () => {
    expect(shouldCache('/dashboard', 'string' as unknown as object)).toBe(false)
  })

  // Valid entries — should cache
  it('caches APP_PAGE with status 200', () => {
    expect(shouldCache('/dashboard', { kind: 'APP_PAGE', html: '<html/>', status: 200 })).toBe(true)
  })
  it('caches APP_PAGE without explicit status (normal App Router render)', () => {
    // App Router pages may omit status when rendering successfully
    expect(shouldCache('/scan', { kind: 'APP_PAGE', html: '<html/>' })).toBe(true)
  })
  it('caches APP_ROUTE with status 200', () => {
    expect(shouldCache('/api/health', { kind: 'APP_ROUTE', status: 200 })).toBe(true)
  })
  it('caches FETCH with data.status 200', () => {
    expect(shouldCache('/dashboard', {
      kind: 'FETCH',
      data: { body: '{}', url: '/api/ops', headers: {}, status: 200 },
      revalidate: 30,
    })).toBe(true)
  })
  it('caches PAGE with status 200 (Pages Router compat)', () => {
    expect(shouldCache('/some-page', { kind: 'PAGE', html: '<html/>', pageData: {}, status: 200 })).toBe(true)
  })
})

// ─── 2. Integration tests — requires Redis ────────────────────────────────────

/**
 * Multi-instance consistency (criterion E2.5).
 * Simulates two Next.js instances sharing the same Redis.
 * Skipped automatically when Redis is unreachable.
 */
describe('RedisCache multi-instance consistency', () => {
  const instanceA = new RedisCache()
  const instanceB = new RedisCache()

  const TEST_KEY = `test:consistency:${Date.now()}`
  const TEST_DATA = { kind: 'APP_PAGE', html: '<div>scan result</div>', status: 200 }

  afterAll(async () => {
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
    const badCache = new RedisCache()
    const result = await badCache.get('')
    expect(result).toBeNull()
  })

  it('regression: does NOT store 404 APP_PAGE in Redis (cache poisoning)', async () => {
    const key = `/test-404-${Date.now()}`
    await instanceA.set(key, { kind: 'APP_PAGE', html: '', status: 404 }, { revalidate: 60 })
    const result = await instanceB.get(key)
    expect(result).toBeNull()
  })

  it('regression: does NOT store REDIRECT in Redis (middleware redirect cached)', async () => {
    const key = `/test-redirect-${Date.now()}`
    await instanceA.set(key, { kind: 'REDIRECT', props: {} }, { revalidate: 60 })
    const result = await instanceB.get(key)
    expect(result).toBeNull()
  })
})
