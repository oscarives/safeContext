import React from 'react'
import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CopyButton } from '../CopyButton'

// navigator.clipboard is read-only in jsdom — define via property descriptor
// before each test and keep a reference to the mock for assertions.
const writeTextMock = jest.fn().mockImplementation(() => Promise.resolve())

beforeAll(() => {
  Object.defineProperty(global.navigator, 'clipboard', {
    value: { writeText: writeTextMock },
    writable: true,
    configurable: true,
  })
})

describe('CopyButton', () => {
  beforeEach(() => {
    writeTextMock.mockClear()
  })

  it('renders with "Copiar" label by default', () => {
    render(<CopyButton text="texto a copiar" />)
    expect(screen.getByRole('button', { name: 'Copiar' })).toBeInTheDocument()
  })

  it('copies text to clipboard on click', async () => {
    render(<CopyButton text="mi-trace-id-123" />)
    const btn = screen.getByRole('button')

    await act(async () => {
      btn.click()
      // Let the microtask from writeText().then() settle
      await Promise.resolve()
    })

    expect(writeTextMock).toHaveBeenCalledWith('mi-trace-id-123')
  })

  it('shows "✓" after successful copy and reverts after 2s', async () => {
    jest.useFakeTimers()
    render(<CopyButton text="abc" />)
    const btn = screen.getByRole('button')

    await act(async () => {
      btn.click()
      await Promise.resolve()
    })

    expect(btn).toHaveTextContent('✓')

    act(() => {
      jest.advanceTimersByTime(2000)
    })

    expect(btn).toHaveTextContent('Copiar')
    jest.useRealTimers()
  })
})
