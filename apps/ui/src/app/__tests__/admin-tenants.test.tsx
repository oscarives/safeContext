import React from 'react'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock API client
jest.mock('@/lib/api-client', () => ({
  apiClient: {
    listTenants: jest.fn(),
    createTenant: jest.fn(),
    deactivateTenant: jest.fn(),
  },
}))

// Mock useSession — admin user
jest.mock('@/hooks/useSession', () => ({
  useSession: () => ({
    user: { sub: 'u1', name: 'Admin', email: 'admin@t.com', roles: ['admin'] },
    isLoading: false,
    hasRole: (r: string) => r === 'admin',
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
import TenantsPage from '../admin/tenants/page'

const mockListTenants = apiClient.listTenants as jest.MockedFunction<typeof apiClient.listTenants>
const mockCreateTenant = apiClient.createTenant as jest.MockedFunction<typeof apiClient.createTenant>
const mockDeactivateTenant = apiClient.deactivateTenant as jest.MockedFunction<typeof apiClient.deactivateTenant>

const sampleTenants = [
  {
    id: 't1',
    name: 'Acme Corp',
    slug: 'acme-corp',
    plan: 'enterprise',
    is_active: true,
    max_scans_per_day: 100,
    retention_days: 365,
    contact_email: 'admin@acme.com',
    policy_config: null,
    siem_config: null,
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 't2',
    name: 'Test Org',
    slug: 'test-org',
    plan: 'free',
    is_active: false,
    max_scans_per_day: null,
    retention_days: 90,
    contact_email: null,
    policy_config: null,
    siem_config: null,
    created_at: '2024-06-01T00:00:00Z',
  },
]

beforeEach(() => {
  jest.clearAllMocks()
})

describe('TenantsPage', () => {
  it('renders loading spinner initially', () => {
    mockListTenants.mockReturnValue(new Promise(() => {}))
    render(<TenantsPage />)
    expect(screen.getByText('Loading tenants...')).toBeInTheDocument()
  })

  it('renders empty state when no tenants', async () => {
    mockListTenants.mockResolvedValue([])
    render(<TenantsPage />)

    await waitFor(() => {
      expect(screen.getByText('No tenants configured yet')).toBeInTheDocument()
    })
  })

  it('renders tenant table with data', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    render(<TenantsPage />)

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    })
    expect(screen.getByText('acme-corp')).toBeInTheDocument()
    expect(screen.getByText('enterprise')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('Inactive')).toBeInTheDocument()
  })

  it('shows create tenant button', async () => {
    mockListTenants.mockResolvedValue([])
    render(<TenantsPage />)

    await waitFor(() => {
      expect(screen.getByText('Create Tenant')).toBeInTheDocument()
    })
  })

  it('opens create modal on button click', async () => {
    mockListTenants.mockResolvedValue([])
    const user = userEvent.setup()
    render(<TenantsPage />)

    await waitFor(() => {
      expect(screen.getByText('Create Tenant')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Create Tenant'))
    expect(screen.getByPlaceholderText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('acme-corp')).toBeInTheDocument()
  })

  it('creates tenant via modal form', async () => {
    mockListTenants.mockResolvedValue([])
    mockCreateTenant.mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(<TenantsPage />)

    await waitFor(() => {
      expect(screen.getByText('Create Tenant')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Create Tenant'))

    await user.type(screen.getByPlaceholderText('Acme Corp'), 'New Tenant')
    await user.type(screen.getByPlaceholderText('acme-corp'), 'new-tenant')

    await act(async () => {
      // Submit the form — the Create button inside the modal
      const buttons = screen.getAllByText('Create Tenant')
      // Second one is the submit button in the modal (first is page header button)
      // Actually let's find the submit button
      const submitBtn = screen.getByRole('button', { name: 'Create' })
      await user.click(submitBtn)
    })

    expect(mockCreateTenant).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'New Tenant', slug: 'new-tenant' })
    )
  })

  it('shows deactivate confirmation on button click', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    const user = userEvent.setup()
    render(<TenantsPage />)

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Deactivate'))
    expect(screen.getByText('Deactivate Tenant')).toBeInTheDocument()
  })

  it('deactivates tenant after confirm', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    mockDeactivateTenant.mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(<TenantsPage />)

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    })

    // Click deactivate on first active tenant
    await user.click(screen.getByText('Deactivate'))

    await act(async () => {
      // Confirm in the modal — the SimpleConfirmModal uses confirmLabel="Deactivate"
      const confirmBtns = screen.getAllByText('Deactivate')
      // The last one should be in the modal
      await user.click(confirmBtns[confirmBtns.length - 1])
    })

    expect(mockDeactivateTenant).toHaveBeenCalledWith('t1')
  })

  it('shows error toast on load failure', async () => {
    mockListTenants.mockRejectedValue(new Error('Network error'))
    render(<TenantsPage />)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error', message: 'Network error' })
      )
    })
  })
})
