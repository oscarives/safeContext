import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'

// Mock API client
jest.mock('@/lib/api-client', () => ({
  apiClient: {
    getHealth: jest.fn(),
    getOperations: jest.fn(),
  },
  NotImplementedError: class NotImplementedError extends Error {
    constructor(m = 'Not implemented') { super(m); this.name = 'NotImplementedError' }
  },
}))

// Mock useSession
jest.mock('@/hooks/useSession', () => ({
  useSession: () => ({
    user: { sub: 'u1', name: 'Dev Admin', email: 'admin@t.com', roles: ['admin', 'reviewer', 'viewer', 'policy_editor'] },
    isLoading: false,
    hasRole: () => true,
  }),
}))

// Mock RelativeTime (avoids setInterval in tests)
jest.mock('@/components', () => ({
  ...jest.requireActual('@/components'),
  RelativeTime: ({ ts }: { ts: number }) => <span data-testid="relative-time">{ts}</span>,
}))

import { apiClient } from '@/lib/api-client'
import DashboardPage from '../dashboard/page'

const mockGetHealth = apiClient.getHealth as jest.MockedFunction<typeof apiClient.getHealth>
const mockGetOperations = apiClient.getOperations as jest.MockedFunction<typeof apiClient.getOperations>

const healthOk = { status: 'ok', postgres: 'ok', redis: 'ok', minio: 'ok' }
const opsEmpty = {
  total: 0, items: [],
  total_pending: 0, total_escalated: 0, total_completed: 0, total_rejected: 0,
}

beforeEach(() => {
  jest.clearAllMocks()
  mockGetHealth.mockResolvedValue(healthOk)
  mockGetOperations.mockResolvedValue(opsEmpty)
})

describe('DashboardPage', () => {
  it('renders welcome message with user name', async () => {
    render(<DashboardPage />)
    await waitFor(() => expect(screen.getByText(/Dev Admin/)).toBeInTheDocument())
  })

  it('shows Admin badge for admin user', async () => {
    render(<DashboardPage />)
    await waitFor(() => expect(screen.getByText('Admin')).toBeInTheDocument())
  })

  it('renders health cards when health is OK', async () => {
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Postgres')).toBeInTheDocument()
      expect(screen.getByText('Redis')).toBeInTheDocument()
      expect(screen.getByText('MinIO')).toBeInTheDocument()
    })
    const okElements = screen.getAllByText('OK')
    expect(okElements.length).toBeGreaterThanOrEqual(3)
  })

  it('shows API error when health fetch fails', async () => {
    mockGetHealth.mockRejectedValue(new Error('Connection refused'))
    render(<DashboardPage />)
    await waitFor(() =>
      expect(screen.getByText(/no se puede conectar/i)).toBeInTheDocument()
    )
  })

  it('shows zero stats when operations returns empty', async () => {
    render(<DashboardPage />)
    await waitFor(() => {
      // Stats cards for Total Scans, Aprobados, Pendientes, Rechazados
      const zeros = screen.getAllByText('0')
      expect(zeros.length).toBeGreaterThanOrEqual(4)
    })
  })

  it('shows real stats from operations response', async () => {
    mockGetOperations.mockResolvedValue({
      total: 10, items: [],
      total_pending: 3, total_escalated: 2, total_completed: 4, total_rejected: 1,
    })
    render(<DashboardPage />)
    await waitFor(() => expect(screen.getByText('10')).toBeInTheDocument())
    expect(screen.getByText('4')).toBeInTheDocument()  // aprobados (completed)
    expect(screen.getByText('2')).toBeInTheDocument()  // pendientes (escalated)
    expect(screen.getByText('1')).toBeInTheDocument()  // rechazados
  })

  it('renders accesos rapidos links', async () => {
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Escanear documento')).toBeInTheDocument()
      expect(screen.getByText('Revisiones pendientes')).toBeInTheDocument()
      expect(screen.getByText('Audit Trail')).toBeInTheDocument()
    })
  })
})
