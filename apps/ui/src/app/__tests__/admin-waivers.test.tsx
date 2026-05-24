import React from 'react'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock API client
jest.mock('@/lib/api-client', () => ({
  apiClient: {
    listWaivers: jest.fn(),
    createWaiver: jest.fn(),
    revokeWaiver: jest.fn(),
  },
}))

// Mock useSession — admin with policy_editor role
jest.mock('@/hooks/useSession', () => ({
  useSession: () => ({
    user: { sub: 'u1', name: 'Admin', email: 'admin@t.com', roles: ['admin', 'policy_editor'] },
    isLoading: false,
    hasRole: (r: string) => ['admin', 'policy_editor'].includes(r),
  }),
}))

// Mock useToast
const mockAddToast = jest.fn()
jest.mock('@/components/useToast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

// Mock RelativeTime
jest.mock('@/components/RelativeTime', () => ({
  RelativeTime: ({ ts }: { ts: number }) => <span data-testid="relative-time">{ts}</span>,
}))

import { apiClient } from '@/lib/api-client'
import WaiversPage from '../admin/waivers/page'

const mockListWaivers = apiClient.listWaivers as jest.MockedFunction<typeof apiClient.listWaivers>
const mockCreateWaiver = apiClient.createWaiver as jest.MockedFunction<typeof apiClient.createWaiver>
const mockRevokeWaiver = apiClient.revokeWaiver as jest.MockedFunction<typeof apiClient.revokeWaiver>

const sampleWaivers = [
  {
    id: 'w1',
    rule_id: 'regex_connection_string',
    entity_pattern: 'localhost.*testdb',
    justification: 'This is a local dev database connection string, not production',
    approved_by: 'admin@t.com',
    status: 'active',
    expires_at: '2025-12-31T23:59:59Z',
    created_at: '2024-01-15T10:00:00Z',
  },
  {
    id: 'w2',
    rule_id: 'regex_api_key',
    entity_pattern: 'DEMO_KEY_.*',
    justification: 'Demo API keys are not real secrets, used in documentation only',
    approved_by: 'admin@t.com',
    status: 'revoked',
    expires_at: null,
    created_at: '2024-02-01T08:00:00Z',
  },
]

beforeEach(() => {
  jest.clearAllMocks()
})

describe('WaiversPage', () => {
  it('renders loading spinner initially', () => {
    mockListWaivers.mockReturnValue(new Promise(() => {}))
    render(<WaiversPage />)
    expect(screen.getByText('Loading waivers...')).toBeInTheDocument()
  })

  it('renders empty state when no waivers', async () => {
    mockListWaivers.mockResolvedValue([])
    render(<WaiversPage />)

    await waitFor(() => {
      expect(screen.getByText('No active waivers')).toBeInTheDocument()
    })
  })

  it('renders waiver table with data', async () => {
    mockListWaivers.mockResolvedValue(sampleWaivers)
    render(<WaiversPage />)

    await waitFor(() => {
      expect(screen.getByText('regex_connection_string')).toBeInTheDocument()
    })
    expect(screen.getByText('localhost.*testdb')).toBeInTheDocument()
    expect(screen.getByText('active')).toBeInTheDocument()
    expect(screen.getByText('revoked')).toBeInTheDocument()
  })

  it('shows create waiver button for policy editors', async () => {
    mockListWaivers.mockResolvedValue([])
    render(<WaiversPage />)

    await waitFor(() => {
      expect(screen.getByText('Create Waiver')).toBeInTheDocument()
    })
  })

  it('opens create modal on button click', async () => {
    mockListWaivers.mockResolvedValue([])
    const user = userEvent.setup()
    render(<WaiversPage />)

    await waitFor(() => {
      expect(screen.getByText('Create Waiver')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Create Waiver'))
    expect(screen.getByPlaceholderText('regex_connection_string')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('localhost.*testdb')).toBeInTheDocument()
  })

  it('validates regex pattern in create form', async () => {
    mockListWaivers.mockResolvedValue([])
    const user = userEvent.setup()
    render(<WaiversPage />)

    await waitFor(() => {
      expect(screen.getByText('Create Waiver')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Create Waiver'))

    const patternInput = screen.getByPlaceholderText('localhost.*testdb')
    // Use fireEvent.change since userEvent.type treats brackets as special keyboard keys
    fireEvent.change(patternInput, { target: { value: '[invalid(' } })

    expect(screen.getByText('Invalid regular expression')).toBeInTheDocument()
  })

  it('shows revoke button only for active waivers', async () => {
    mockListWaivers.mockResolvedValue(sampleWaivers)
    render(<WaiversPage />)

    await waitFor(() => {
      expect(screen.getByText('regex_connection_string')).toBeInTheDocument()
    })

    // Only one Revoke button (for the active waiver)
    const revokeButtons = screen.getAllByText('Revoke')
    expect(revokeButtons).toHaveLength(1)
  })

  it('shows revoke confirmation modal', async () => {
    mockListWaivers.mockResolvedValue(sampleWaivers)
    const user = userEvent.setup()
    render(<WaiversPage />)

    await waitFor(() => {
      expect(screen.getByText('regex_connection_string')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Revoke'))
    expect(screen.getByText('Revoke Waiver')).toBeInTheDocument()
  })

  it('revokes waiver after confirm', async () => {
    mockListWaivers.mockResolvedValue(sampleWaivers)
    mockRevokeWaiver.mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(<WaiversPage />)

    await waitFor(() => {
      expect(screen.getByText('regex_connection_string')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Revoke'))

    await act(async () => {
      // The confirm button in the modal also says "Revoke"
      const revokeButtons = screen.getAllByText('Revoke')
      await user.click(revokeButtons[revokeButtons.length - 1])
    })

    expect(mockRevokeWaiver).toHaveBeenCalledWith('w1')
  })

  it('shows error toast on load failure', async () => {
    mockListWaivers.mockRejectedValue(new Error('Connection refused'))
    render(<WaiversPage />)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error', message: 'Connection refused' })
      )
    })
  })
})
