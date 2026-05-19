const NextResponse = {
  next: jest.fn(() => ({ type: 'next' })),
  redirect: jest.fn((url) => ({ type: 'redirect', url: url.toString() })),
  json: jest.fn((data) => ({ type: 'json', data })),
}

class NextRequest {
  constructor(url, init = {}) {
    this.url = typeof url === 'string' ? url : url.toString()
    this.nextUrl = new URL(this.url)
    this.cookies = { get: jest.fn() }
    this.headers = new Map(Object.entries(init.headers || {}))
    this.method = init.method || 'GET'
  }
}

module.exports = { NextResponse, NextRequest }
