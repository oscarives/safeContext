import React from 'react'
import { render, screen } from '@testing-library/react'
import { EmptyState } from '../EmptyState'

describe('EmptyState', () => {
  it('renders title', () => {
    render(<EmptyState title="Sin resultados" />)
    expect(screen.getByText('Sin resultados')).toBeInTheDocument()
  })

  it('renders description when provided', () => {
    render(<EmptyState title="Sin resultados" description="No hay datos disponibles." />)
    expect(screen.getByText('No hay datos disponibles.')).toBeInTheDocument()
  })

  it('does not render description when omitted', () => {
    render(<EmptyState title="Sin resultados" />)
    expect(screen.queryByText(/disponibles/i)).not.toBeInTheDocument()
  })

  it('renders action link when provided', () => {
    render(
      <EmptyState
        title="Sin resultados"
        action={{ label: 'Escanear documento', href: '/scan' }}
      />
    )
    const link = screen.getByRole('link', { name: 'Escanear documento' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/scan')
  })

  it('does not render action link when omitted', () => {
    render(<EmptyState title="Sin resultados" />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
