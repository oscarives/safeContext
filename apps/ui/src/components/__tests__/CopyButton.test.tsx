import React from 'react'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CopyButton } from '../CopyButton'

describe('CopyButton', () => {
  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: { writeText: jest.fn().mockResolvedValue(undefined) },
    })
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('renders with "Copiar" label by default', () => {
    render(<CopyButton text="texto a copiar" />)
    expect(screen.getByRole('button', { name: 'Copiar' })).toBeInTheDocument()
  })

  it('copies text to clipboard on click', async () => {
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
    render(<CopyButton text="mi-trace-id-123" />)
    await user.click(screen.getByRole('button'))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('mi-trace-id-123')
  })

  it('shows "✓" after successful copy and reverts after 2s', async () => {
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
    render(<CopyButton text="abc" />)
    await user.click(screen.getByRole('button'))
    expect(screen.getByRole('button')).toHaveTextContent('✓')
    act(() => jest.advanceTimersByTime(2000))
    expect(screen.getByRole('button')).toHaveTextContent('Copiar')
  })
})
