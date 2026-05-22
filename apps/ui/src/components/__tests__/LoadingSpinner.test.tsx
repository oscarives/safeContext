import React from 'react'
import { render, screen } from '@testing-library/react'
import { LoadingSpinner } from '../LoadingSpinner'

describe('LoadingSpinner', () => {
  it('renders without crashing (default size md)', () => {
    const { container } = render(<LoadingSpinner />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveClass('w-8', 'h-8')
  })

  it('renders with size sm', () => {
    const { container } = render(<LoadingSpinner size="sm" />)
    expect(container.querySelector('svg')).toHaveClass('w-4', 'h-4')
  })

  it('renders with size lg', () => {
    const { container } = render(<LoadingSpinner size="lg" />)
    expect(container.querySelector('svg')).toHaveClass('w-12', 'h-12')
  })

  it('renders message when provided', () => {
    render(<LoadingSpinner message="Cargando datos..." />)
    expect(screen.getByText('Cargando datos...')).toBeInTheDocument()
  })

  it('does not render message when omitted', () => {
    render(<LoadingSpinner />)
    expect(screen.queryByText(/cargando/i)).not.toBeInTheDocument()
  })
})
