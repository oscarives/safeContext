import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

jest.mock('@/hooks/useSession', () => ({
  useSession: () => ({
    user: {
      sub: 'user-1',
      name: 'Oscar Rivas',
      email: 'oscar@empresa.com',
      roles: ['admin', 'reviewer'],
      expiresAt: Date.now() / 1000 + 3600,
    },
    isLoading: false,
    hasRole: () => true,
  }),
}))

import NavBar from '../NavBar'

describe('NavBar', () => {
  it('renders the SafeContext brand link', () => {
    render(<NavBar />)
    expect(screen.getByText('SafeContext')).toBeInTheDocument()
  })

  it('renders all navigation links', () => {
    render(<NavBar />)
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/dashboard')
    expect(screen.getByRole('link', { name: 'Scan' })).toHaveAttribute('href', '/scan')
    expect(screen.getByRole('link', { name: 'Review' })).toHaveAttribute('href', '/review')
    expect(screen.getByRole('link', { name: 'Audit' })).toHaveAttribute('href', '/audit')
  })

  it('renders Grafana as external link', () => {
    render(<NavBar />)
    const grafanaLink = screen.getByRole('link', { name: /Grafana/i })
    expect(grafanaLink).toHaveAttribute('target', '_blank')
    expect(grafanaLink).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('renders logged-in user name', () => {
    render(<NavBar />)
    expect(screen.getByText('Oscar Rivas')).toBeInTheDocument()
  })

  it('renders Sign out button', () => {
    render(<NavBar />)
    expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument()
  })

  it('Sign out navigates to /api/auth/logout', async () => {
    const user = userEvent.setup()
    const assignMock = jest.fn()
    Object.defineProperty(window, 'location', {
      value: { href: '' },
      writable: true,
    })
    render(<NavBar />)
    await user.click(screen.getByRole('button', { name: /sign out/i }))
    expect(window.location.href).toBe('/api/auth/logout')
  })
})
