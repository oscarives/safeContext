// api/auth/session/route.ts — Returns the current user profile (NO raw token)
// Used by client components via useSession hook.

import { NextResponse } from 'next/server'
import { getSession } from '@/lib/session'

export async function GET() {
  const session = await getSession()

  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // Never expose the raw accessToken to client JavaScript
  return NextResponse.json({
    sub: session.sub,
    name: session.name,
    email: session.email,
    roles: session.roles,
    expiresAt: session.expiresAt,
  })
}
