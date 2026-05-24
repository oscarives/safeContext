import React from 'react'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock API client
jest.mock('@/lib/api-client', () => ({
  apiClient: {
    listTenants: jest.fn(),
    updateTenant: jest.fn(),
    triggerPurge: jest.fn(),
    listCertificates: jest.fn(),
    getCertificate: jest.fn(),
  },
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
import RetentionPage from '../admin/retention/page'

const mockListTenants = apiClient.listTenants as jest.MockedFunction<typeof apiClient.listTenants>
const mockUpdateTenant = apiClient.updateTenant as jest.MockedFunction<typeof apiClient.updateTenant>
const mockTriggerPurge = apiClient.triggerPurge as jest.MockedFunction<typeof apiClient.triggerPurge>
const mockListCertificates = apiClient.listCertificates as jest.MockedFunction<typeof apiClient.listCertificates>
const mockGetCertificate = apiClient.getCertificate as jest.MockedFunction<typeof apiClient.getCertificate>

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
]

const sampleCerts = [
  {
    certificate_id: 'cert-001',
    object_name: 'purge/cert-001.json',
    size: 1234,
    last_modified: '2024-06-01T10:00:00Z',
  },
  {
    certificate_id: 'cert-002',
    object_name: 'purge/cert-002.json',
    size: 5678,
    last_modified: null,
  },
]

const samplePurgeResult = {
  purged: true,
  operations_deleted: 42,
  findings_deleted: 128,
  redactions_deleted: 64,
  artifacts_deleted: 10,
  certificate_id: 'cert-new',
  certificate_stored: true,
}

beforeEach(() => {
  jest.clearAllMocks()
  mockListCertificates.mockResolvedValue([])
})

describe('RetentionPage', () => {
  it('renders loading spinner initially', () => {
    mockListTenants.mockReturnValue(new Promise(() => {}))
    render(<RetentionPage />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('renders retention configuration after loading', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    render(<RetentionPage />)

    await waitFor(() => {
      expect(screen.getByText('GDPR Retention')).toBeInTheDocument()
    })
    expect(screen.getByText('Retention Configuration')).toBeInTheDocument()
    expect(screen.getByText('Manual Purge')).toBeInTheDocument()
    expect(screen.getByText('Deletion Certificates')).toBeInTheDocument()
  })

  it('shows tenant selector with loaded tenants', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    render(<RetentionPage />)

    await waitFor(() => {
      expect(screen.getByText('Acme Corp (acme-corp)')).toBeInTheDocument()
    })
  })

  it('saves retention period', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    mockUpdateTenant.mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(<RetentionPage />)

    await waitFor(() => {
      expect(screen.getByText('Save')).toBeInTheDocument()
    })

    await act(async () => {
      await user.click(screen.getByText('Save'))
    })

    expect(mockUpdateTenant).toHaveBeenCalledWith('t1', { retention_days: 365 })
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'success', message: 'Retention period saved' })
    )
  })

  it('shows purge confirmation modal on button click', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    const user = userEvent.setup()
    render(<RetentionPage />)

    await waitFor(() => {
      expect(screen.getByText('Execute Purge')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Execute Purge'))
    expect(screen.getByText('Confirm GDPR Purge')).toBeInTheDocument()
  })

  it('executes purge and shows result', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    mockTriggerPurge.mockResolvedValue(samplePurgeResult)
    const user = userEvent.setup()
    render(<RetentionPage />)

    await waitFor(() => {
      expect(screen.getByText('Execute Purge')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Execute Purge'))

    await act(async () => {
      // Confirm in the modal
      const execButtons = screen.getAllByText('Execute Purge')
      await user.click(execButtons[execButtons.length - 1])
    })

    await waitFor(() => {
      expect(screen.getByText('Purge Completed')).toBeInTheDocument()
    })
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('shows nothing-to-purge result', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    mockTriggerPurge.mockResolvedValue({ purged: false })
    const user = userEvent.setup()
    render(<RetentionPage />)

    await waitFor(() => {
      expect(screen.getByText('Execute Purge')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Execute Purge'))

    await act(async () => {
      const execButtons = screen.getAllByText('Execute Purge')
      await user.click(execButtons[execButtons.length - 1])
    })

    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringContaining('nothing to purge') })
    )
  })

  it('renders certificate list', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    mockListCertificates.mockResolvedValue(sampleCerts)
    render(<RetentionPage />)

    await waitFor(() => {
      expect(screen.getByText('cert-001')).toBeInTheDocument()
    })
    expect(screen.getByText('cert-002')).toBeInTheDocument()
    expect(screen.getByText('(1234 bytes)')).toBeInTheDocument()
  })

  it('shows empty state when no certificates', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    mockListCertificates.mockResolvedValue([])
    render(<RetentionPage />)

    await waitFor(() => {
      expect(screen.getByText('No deletion certificates found for this tenant')).toBeInTheDocument()
    })
  })

  it('views certificate detail', async () => {
    mockListTenants.mockResolvedValue(sampleTenants)
    mockListCertificates.mockResolvedValue(sampleCerts)
    mockGetCertificate.mockResolvedValue({
      certificate_id: 'cert-001',
      data: { purge_date: '2024-06-01', ops_deleted: 10 },
    })
    const user = userEvent.setup()
    render(<RetentionPage />)

    await waitFor(() => {
      expect(screen.getByText('cert-001')).toBeInTheDocument()
    })

    const viewButtons = screen.getAllByText('View')
    await act(async () => {
      await user.click(viewButtons[0])
    })

    await waitFor(() => {
      expect(screen.getByText('Certificate Detail')).toBeInTheDocument()
    })
  })

  it('shows error toast on tenant load failure', async () => {
    mockListTenants.mockRejectedValue(new Error('DB down'))
    render(<RetentionPage />)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error', message: 'DB down' })
      )
    })
  })
})
