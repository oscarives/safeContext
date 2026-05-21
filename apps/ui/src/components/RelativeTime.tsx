'use client'

import { useEffect, useState } from 'react'

function secondsAgo(ts: number): string {
  const delta = Math.floor((Date.now() - ts) / 1000)
  if (delta < 5) return 'ahora mismo'
  if (delta < 60) return `hace ${delta} seg`
  return `hace ${Math.floor(delta / 60)} min`
}

/**
 * Displays a relative timestamp that updates every second.
 * Isolated so only this <span> re-renders on each tick — not the parent page.
 */
export function RelativeTime({ ts }: { ts: number }) {
  const [, setTick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000)
    return () => clearInterval(t)
  }, [])
  return <span>{secondsAgo(ts)}</span>
}
