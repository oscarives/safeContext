// middleware.test.ts
// Tests for route protection middleware

// All jest.mock calls are hoisted to the top of the file by Babel.
// Variables referenced inside mock factories must use jest.fn() inline
// OR be declared with jest.fn() before any imports.

jest.mock('jose', () => ({
  decodeJwt: jest.fn(),
}))

// Mock the session module (it imports next/headers which is server-only)
jest.mock('@/lib/session', () => ({
  SESSION_COOKIE_NAME: 'sc_session',
}))

// Mock next/server: NextResponse.next and NextResponse.redirect are jest.fn()
// defined inside the factory so they're created after hoisting.
jest.mock('next/server', () => {
  const mockNext = jest.fn(() => ({ status: 200, headers: new Map() }))
  const mockRedirect = jest.fn((url: URL) => ({
    status: 307,
    headers: new Map([['location', url.toString()]]),
  }))

  class MockNextRequest {
    url: string
    nextUrl: URL
    cookies: { get: (name: string) => { value: string } | undefined }

    constructor(url: string, options?: { cookies?: Record<string, string> }) {
      this.url = url
      this.nextUrl = new URL(url)
      const cookieStore: Record<string, string> = (options as { cookies?: Record<string, string> } | undefined)?.cookies ?? {}
      this.cookies = {
        get: (name: string) =>
          cookieStore[name] !== undefined ? { value: cookieStore[name] } : undefined,
      }
    }
  }

  return {
    NextResponse: {
      next: mockNext,
      redirect: mockRedirect,
    },
    NextRequest: MockNextRequest,
  }
})

import { NextResponse } from 'next/server'
import { decodeJwt } from 'jose'
import { middleware } from './middleware'

const mockDecodeJwt = decodeJwt as jest.MockedFunction<typeof decodeJwt>
const mockNextResponseNext = NextResponse.next as jest.MockedFunction<() => unknown>
const mockNextResponseRedirect = NextResponse.redirect as jest.MockedFunction<(url: URL) => unknown>

function makeRequest(pathname: string, cookieValue?: string) {
  const { NextRequest } = jest.requireMock('next/server')
  const url = `http://localhost${pathname}`
  const options = cookieValue ? { cookies: { sc_session: cookieValue } } : undefined
  return new NextRequest(url, options)
}

beforeEach(() => {
  jest.clearAllMocks()
  // Reset mockNext to return a valid response object after clearAllMocks
  mockNextResponseNext.mockReturnValue({ status: 200, headers: new Map() })
  mockNextResponseRedirect.mockImplementation((url: URL) => ({
    status: 307,
    headers: new Map([['location', url.toString()]]),
  }))
})

describe('middleware', () => {
  it('passes through /login without redirect', () => {
    const req = makeRequest('/login')
    middleware(req)
    expect(mockNextResponseNext).toHaveBeenCalled()
    expect(mockNextResponseRedirect).not.toHaveBeenCalled()
  })

  it('passes through /auth/callback without redirect', () => {
    const req = makeRequest('/auth/callback')
    middleware(req)
    expect(mockNextResponseNext).toHaveBeenCalled()
    expect(mockNextResponseRedirect).not.toHaveBeenCalled()
  })

  it('passes through /api/auth/session without redirect', () => {
    const req = makeRequest('/api/auth/session')
    middleware(req)
    expect(mockNextResponseNext).toHaveBeenCalled()
    expect(mockNextResponseRedirect).not.toHaveBeenCalled()
  })

  it('redirects to /login?next=/dashboard when no cookie is present', () => {
    const req = makeRequest('/dashboard')
    middleware(req)
    expect(mockNextResponseRedirect).toHaveBeenCalled()
    const redirectUrl: URL = mockNextResponseRedirect.mock.calls[0][0] as URL
    expect(redirectUrl.pathname).toBe('/login')
    expect(redirectUrl.searchParams.get('next')).toBe('/dashboard')
  })

  it('redirects to /login when cookie has an expired token', () => {
    const pastExp = Math.floor(Date.now() / 1000) - 3600
    mockDecodeJwt.mockReturnValue({ exp: pastExp } as never)

    const req = makeRequest('/dashboard', 'fake.access.token||fake.refresh.token')
    middleware(req)
    expect(mockNextResponseRedirect).toHaveBeenCalled()
    const redirectUrl: URL = mockNextResponseRedirect.mock.calls[0][0] as URL
    expect(redirectUrl.pathname).toBe('/login')
  })

  it('passes through /dashboard with a valid cookie', () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    mockDecodeJwt.mockReturnValue({ exp: futureExp } as never)

    const req = makeRequest('/dashboard', 'fake.access.token||fake.refresh.token')
    middleware(req)
    expect(mockNextResponseNext).toHaveBeenCalled()
    expect(mockNextResponseRedirect).not.toHaveBeenCalled()
  })
})
