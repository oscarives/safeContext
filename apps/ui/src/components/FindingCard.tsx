'use client'

import { SeverityBadge } from './SeverityBadge'

export interface Finding {
  finding_id: string
  detector: string
  rule_id: string
  confidence: number
  severity: 'low' | 'medium' | 'high' | 'critical'
  span_start: number
  span_end: number
  explanation: Record<string, unknown>
  document_preview: string
  created_at?: string
  operation_id?: string
  trace_id?: string
}

export function FindingCard({
  finding,
  onApprove,
  onReject,
  disabled = false,
  disabledReason,
}: {
  finding: Finding
  onApprove?: (findingId: string) => void
  onReject?: (findingId: string) => void
  disabled?: boolean
  disabledReason?: string
}) {
  const preview = finding.document_preview
  const before = preview.slice(0, finding.span_start)
  const highlighted = preview.slice(finding.span_start, finding.span_end)
  const after = preview.slice(finding.span_end)

  const hasActions = onApprove !== undefined || onReject !== undefined

  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <SeverityBadge severity={finding.severity} />
          <span className="font-mono text-sm text-gray-700">{finding.detector}</span>
          <span className="text-xs text-gray-400">rule: {finding.rule_id}</span>
        </div>
        <span className="text-sm text-gray-500 whitespace-nowrap ml-2">
          {Math.round(finding.confidence * 100)}% confidence
        </span>
      </div>

      <div className="font-mono text-sm bg-gray-50 p-2 rounded mb-3 overflow-x-auto whitespace-pre-wrap break-words">
        {before}
        <mark className="bg-yellow-200 px-0.5 rounded">{highlighted}</mark>
        {after}
      </div>

      <div className="text-xs text-gray-400 mb-3 space-y-0.5">
        {finding.trace_id && (
          <div>
            Trace: <code className="bg-gray-100 px-1 rounded">{finding.trace_id}</code>
          </div>
        )}
        <div>
          Span [{finding.span_start}:{finding.span_end}]
          {finding.created_at && (
            <> &middot; Created: {new Date(finding.created_at).toLocaleString()}</>
          )}
        </div>
      </div>

      {hasActions && (
        <div className="flex gap-2">
          {onApprove && (
            <ActionButton
              label="Aprobar"
              onClick={() => onApprove(finding.finding_id)}
              disabled={disabled}
              disabledReason={disabledReason}
              variant="approve"
            />
          )}
          {onReject && (
            <ActionButton
              label="Rechazar"
              onClick={() => onReject(finding.finding_id)}
              disabled={disabled}
              disabledReason={disabledReason}
              variant="reject"
            />
          )}
        </div>
      )}
    </div>
  )
}

function ActionButton({
  label,
  onClick,
  disabled,
  disabledReason,
  variant,
}: {
  label: string
  onClick: () => void
  disabled: boolean
  disabledReason?: string
  variant: 'approve' | 'reject'
}) {
  const baseClasses =
    variant === 'approve'
      ? 'bg-green-600 hover:bg-green-700 disabled:bg-green-300'
      : 'bg-red-600 hover:bg-red-700 disabled:bg-red-300'

  const button = (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-1.5 text-white text-sm rounded transition-colors disabled:cursor-not-allowed ${baseClasses}`}
    >
      {label}
    </button>
  )

  if (disabled && disabledReason) {
    return (
      <div className="relative group inline-block">
        {button}
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 bg-gray-800 text-white text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-10">
          {disabledReason}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-800" />
        </div>
      </div>
    )
  }

  return button
}
