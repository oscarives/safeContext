import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfirmModal } from '../ConfirmModal'

const defaultProps = {
  isOpen: true,
  title: 'Aprobar hallazgo',
  action: 'approve' as const,
  onConfirm: jest.fn(),
  onCancel: jest.fn(),
}

beforeEach(() => {
  jest.clearAllMocks()
})

describe('ConfirmModal', () => {
  it('does not render anything when isOpen is false', () => {
    render(<ConfirmModal {...defaultProps} isOpen={false} />)
    expect(screen.queryByText('Aprobar hallazgo')).not.toBeInTheDocument()
  })

  it('renders the modal when isOpen is true', () => {
    render(<ConfirmModal {...defaultProps} />)
    expect(screen.getByText('Aprobar hallazgo')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Describe el motivo de tu decisión...')).toBeInTheDocument()
  })

  it('Confirm button is disabled with 0 chars of justification', () => {
    render(<ConfirmModal {...defaultProps} />)
    expect(screen.getByText('Confirmar')).toBeDisabled()
  })

  it('Confirm button is disabled with 19 chars of justification', async () => {
    const user = userEvent.setup()
    render(<ConfirmModal {...defaultProps} />)
    const textarea = screen.getByPlaceholderText('Describe el motivo de tu decisión...')
    await user.type(textarea, '1234567890123456789') // 19 chars
    expect(screen.getByText('Confirmar')).toBeDisabled()
  })

  it('Confirm button is enabled with 20 chars of justification', async () => {
    const user = userEvent.setup()
    render(<ConfirmModal {...defaultProps} />)
    const textarea = screen.getByPlaceholderText('Describe el motivo de tu decisión...')
    await user.type(textarea, '12345678901234567890') // 20 chars
    expect(screen.getByText('Confirmar')).not.toBeDisabled()
  })

  it('calls onConfirm with the correct justification on submit', async () => {
    const user = userEvent.setup()
    const onConfirm = jest.fn()
    render(<ConfirmModal {...defaultProps} onConfirm={onConfirm} />)
    const textarea = screen.getByPlaceholderText('Describe el motivo de tu decisión...')
    await user.type(textarea, 'This is a valid justification text')
    await user.click(screen.getByText('Confirmar'))
    expect(onConfirm).toHaveBeenCalledWith('This is a valid justification text')
  })

  it('calls onCancel when Cancelar button is clicked', async () => {
    const user = userEvent.setup()
    const onCancel = jest.fn()
    render(<ConfirmModal {...defaultProps} onCancel={onCancel} />)
    await user.click(screen.getByText('Cancelar'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('calls onCancel when Escape key is pressed', () => {
    const onCancel = jest.fn()
    render(<ConfirmModal {...defaultProps} onCancel={onCancel} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
