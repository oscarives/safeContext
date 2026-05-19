import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FindingCard, type Finding } from '../FindingCard'

const baseFinding: Finding = {
  finding_id: 'finding-123',
  detector: 'pii-detector',
  rule_id: 'rule-001',
  confidence: 0.95,
  severity: 'high',
  span_start: 5,
  span_end: 10,
  explanation: {},
  document_preview: 'hello world test',
}

describe('FindingCard', () => {
  it('renders detector and confidence', () => {
    render(<FindingCard finding={baseFinding} />)
    expect(screen.getByText('pii-detector')).toBeInTheDocument()
    expect(screen.getByText('95% confidence')).toBeInTheDocument()
  })

  it('renders SeverityBadge with the correct severity', () => {
    render(<FindingCard finding={baseFinding} />)
    expect(screen.getByText('HIGH')).toBeInTheDocument()
  })

  it('does not render action buttons when no callbacks are passed', () => {
    render(<FindingCard finding={baseFinding} />)
    expect(screen.queryByText('Aprobar')).not.toBeInTheDocument()
    expect(screen.queryByText('Rechazar')).not.toBeInTheDocument()
  })

  it('renders Aprobar and Rechazar buttons when callbacks are passed', () => {
    render(
      <FindingCard
        finding={baseFinding}
        onApprove={jest.fn()}
        onReject={jest.fn()}
      />
    )
    expect(screen.getByText('Aprobar')).toBeInTheDocument()
    expect(screen.getByText('Rechazar')).toBeInTheDocument()
  })

  it('buttons are disabled when disabled prop is true', () => {
    render(
      <FindingCard
        finding={baseFinding}
        onApprove={jest.fn()}
        onReject={jest.fn()}
        disabled={true}
      />
    )
    expect(screen.getByText('Aprobar')).toBeDisabled()
    expect(screen.getByText('Rechazar')).toBeDisabled()
  })

  it('calls onApprove with the finding_id when Aprobar is clicked', async () => {
    const user = userEvent.setup()
    const onApprove = jest.fn()
    render(
      <FindingCard
        finding={baseFinding}
        onApprove={onApprove}
        onReject={jest.fn()}
      />
    )
    await user.click(screen.getByText('Aprobar'))
    expect(onApprove).toHaveBeenCalledWith('finding-123')
  })
})
