// api/auth/token/route.ts — Returns the raw access token for use by the API client
// This Route Handler runs server-side and can read httpOnly cookies.
// The token is returned in JSON and held in-memory in the client (never in localStorage/DOM).

import { NextResponse } from 'next/server'
import { getSession } from '@/lib/session'

export async function GET() {
  const session = await getSession()

  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  return NextResponse.json({ token: session.accessToken })
}
