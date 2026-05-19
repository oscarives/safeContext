type Severity = 'low' | 'medium' | 'high' | 'critical'

const severityStyles: Record<Severity, string> = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-amber-100 text-amber-800',
  high: 'bg-red-100 text-red-800',
  critical: 'bg-purple-100 text-purple-800',
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-block px-2 py-1 rounded text-xs font-semibold ${severityStyles[severity]}`}
    >
      {severity.toUpperCase()}
    </span>
  )
}
