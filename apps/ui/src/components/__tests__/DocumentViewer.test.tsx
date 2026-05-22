import React from 'react'
import { render, screen } from '@testing-library/react'
import { DocumentViewer } from '../DocumentViewer'

describe('DocumentViewer', () => {
  it('renders plain text without findings', () => {
    render(<DocumentViewer text="Hello world, no PII here." findings={[]} />)
    expect(screen.getByText(/Hello world/)).toBeInTheDocument()
  })

  it('renders empty text without crashing', () => {
    const { container } = render(<DocumentViewer text="" findings={[]} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders text split by a single finding span', () => {
    render(
      <DocumentViewer
        text="Email: john@empresa.com here"
        findings={[{
          span_start: 7,
          span_end: 23,
          severity: 'medium',
          detector: 'presidio.EMAIL_ADDRESS',
        }]}
      />
    )
    // Pre-span text
    expect(screen.getByText(/Email:/)).toBeInTheDocument()
    // The highlighted email span
    expect(screen.getByText('john@empresa.com')).toBeInTheDocument()
    // Post-span text
    expect(screen.getByText(/here/)).toBeInTheDocument()
  })

  it('applies correct background color for critical severity', () => {
    const { container } = render(
      <DocumentViewer
        text="key: sk-ant-abc123"
        findings={[{
          span_start: 5,
          span_end: 18,
          severity: 'critical',
          detector: 'presidio.API_KEY',
        }]}
      />
    )
    // critical → bg-purple-200
    const highlighted = container.querySelector('.bg-purple-200')
    expect(highlighted).toBeInTheDocument()
  })

  it('applies correct background color for medium severity', () => {
    const { container } = render(
      <DocumentViewer
        text="Email: user@test.org found"
        findings={[{
          span_start: 7,
          span_end: 19,
          severity: 'medium',
          detector: 'presidio.EMAIL_ADDRESS',
        }]}
      />
    )
    // medium → bg-amber-200
    const highlighted = container.querySelector('.bg-amber-200')
    expect(highlighted).toBeInTheDocument()
  })

  it('renders multiple findings with different severities', () => {
    const { container } = render(
      <DocumentViewer
        text="email@test.com and sk-key-123"
        findings={[
          { span_start: 0, span_end: 14, severity: 'medium', detector: 'presidio.EMAIL_ADDRESS' },
          { span_start: 19, span_end: 29, severity: 'critical', detector: 'presidio.API_KEY' },
        ]}
      />
    )
    expect(container.querySelector('.bg-amber-200')).toBeInTheDocument()
    expect(container.querySelector('.bg-purple-200')).toBeInTheDocument()
  })
})
