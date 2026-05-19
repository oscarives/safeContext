'use client'

import { useMemo, useState } from 'react'

type Severity = 'low' | 'medium' | 'high' | 'critical'

interface SpanFinding {
  span_start: number
  span_end: number
  severity: Severity
  detector: string
}

const severityOrder: Record<Severity, number> = {
  low: 0,
  medium: 1,
  high: 2,
  critical: 3,
}

const spanBgColors: Record<Severity, string> = {
  low: 'bg-green-200',
  medium: 'bg-amber-200',
  high: 'bg-red-200',
  critical: 'bg-purple-200',
}

interface Segment {
  text: string
  finding?: SpanFinding
}

function buildSegments(text: string, findings: SpanFinding[]): Segment[] {
  if (findings.length === 0) return [{ text }]

  const sorted = [...findings].sort((a, b) => a.span_start - b.span_start)

  const events: Array<{ pos: number; type: 'start' | 'end'; finding: SpanFinding }> = []
  for (const f of sorted) {
    events.push({ pos: f.span_start, type: 'start', finding: f })
    events.push({ pos: f.span_end, type: 'end', finding: f })
  }
  events.sort((a, b) => a.pos - b.pos || (a.type === 'end' ? -1 : 1))

  const segments: Segment[] = []
  let cursor = 0
  const active: SpanFinding[] = []

  const positions = [...new Set(events.map((e) => e.pos))].sort((a, b) => a - b)

  for (const pos of positions) {
    if (pos > cursor && text.slice(cursor, pos).length > 0) {
      const dominant = active.reduce<SpanFinding | undefined>((best, f) =>
        !best || severityOrder[f.severity] > severityOrder[best.severity] ? f : best,
        undefined
      )
      segments.push({ text: text.slice(cursor, pos), finding: dominant })
    }

    const startEvents = events.filter((e) => e.pos === pos && e.type === 'start')
    const endEvents = events.filter((e) => e.pos === pos && e.type === 'end')

    for (const e of endEvents) {
      const idx = active.indexOf(e.finding)
      if (idx !== -1) active.splice(idx, 1)
    }
    for (const e of startEvents) {
      active.push(e.finding)
    }

    cursor = pos
  }

  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor) })
  }

  return segments
}

export function DocumentViewer({
  text,
  findings,
}: {
  text: string
  findings: SpanFinding[]
}) {
  const [tooltip, setTooltip] = useState<{ label: string; x: number; y: number } | null>(null)

  const segments = useMemo(() => buildSegments(text, findings), [text, findings])

  return (
    <div
      className="font-mono text-sm bg-gray-50 p-4 rounded whitespace-pre-wrap overflow-x-auto leading-relaxed relative"
      onMouseLeave={() => setTooltip(null)}
    >
      {segments.map((seg, i) =>
        seg.finding ? (
          <mark
            key={i}
            className={`cursor-pointer rounded-sm px-0.5 ${spanBgColors[seg.finding.severity as Severity]}`}
            onMouseEnter={(e) => {
              const rect = (e.target as HTMLElement).getBoundingClientRect()
              setTooltip({
                label: `${seg.finding!.detector} · ${seg.finding!.severity}`,
                x: rect.left + rect.width / 2,
                y: rect.top - 8,
              })
            }}
            onMouseLeave={() => setTooltip(null)}
          >
            {seg.text}
          </mark>
        ) : (
          <span key={i}>{seg.text}</span>
        )
      )}

      {tooltip && (
        <div
          className="fixed z-20 px-2 py-1 bg-gray-800 text-white text-xs rounded whitespace-nowrap pointer-events-none -translate-x-1/2 -translate-y-full"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.label}
        </div>
      )}
    </div>
  )
}
