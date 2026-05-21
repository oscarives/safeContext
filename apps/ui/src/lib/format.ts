// format.ts — Shared formatting utilities for SafeContext UI

/**
 * Truncate a digest/hash for display.
 * Shows head chars + "..." + tail chars only when the string is long enough.
 * Audit and Dashboard share this helper — do NOT inline local copies.
 */
export function truncateDigest(digest: string, head = 8, tail = 4): string {
  return digest.length > head + tail + 3
    ? `${digest.slice(0, head)}...${digest.slice(-tail)}`
    : digest
}

/**
 * Format an ISO date string for display in Spanish locale.
 * Returns "—" for null/empty input.
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('es-ES', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  })
}

/**
 * Compute human-readable processing time between two ISO timestamps.
 */
export function processingTime(created: string, completed: string | null): string {
  if (!completed) return '—'
  const ms = new Date(completed).getTime() - new Date(created).getTime()
  if (ms < 0) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

/**
 * Spanish plural helper for "hallazgo(s)".
 */
export function pluralHallazgos(n: number): string {
  return `${n} hallazgo${n !== 1 ? 's' : ''}`
}
