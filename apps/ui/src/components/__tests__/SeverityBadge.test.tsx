import React from 'react'
import { render, screen } from '@testing-library/react'
import { SeverityBadge } from '../SeverityBadge'

describe('SeverityBadge', () => {
  it('renders LOW for severity low', () => {
    render(<SeverityBadge severity="low" />)
    expect(screen.getByText('LOW')).toBeInTheDocument()
  })

  it('renders MEDIUM for severity medium', () => {
    render(<SeverityBadge severity="medium" />)
    expect(screen.getByText('MEDIUM')).toBeInTheDocument()
  })

  it('renders HIGH for severity high', () => {
    render(<SeverityBadge severity="high" />)
    expect(screen.getByText('HIGH')).toBeInTheDocument()
  })

  it('renders CRITICAL for severity critical', () => {
    render(<SeverityBadge severity="critical" />)
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  it('applies green classes for low severity', () => {
    const { container } = render(<SeverityBadge severity="low" />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toContain('bg-green-100')
    expect(badge.className).toContain('text-green-800')
  })

  it('applies amber classes for medium severity', () => {
    const { container } = render(<SeverityBadge severity="medium" />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toContain('bg-amber-100')
    expect(badge.className).toContain('text-amber-800')
  })

  it('applies red classes for high severity', () => {
    const { container } = render(<SeverityBadge severity="high" />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toContain('bg-red-100')
    expect(badge.className).toContain('text-red-800')
  })

  it('applies purple classes for critical severity', () => {
    const { container } = render(<SeverityBadge severity="critical" />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toContain('bg-purple-100')
    expect(badge.className).toContain('text-purple-800')
  })
})
