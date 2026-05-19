import React from 'react'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock API client
jest.mock('@/lib/api-client', () => ({
  apiClient: {
    getAuditExport: jest.fn(),
  },
  ForbiddenError: class ForbiddenError extends Error {},
}))

import { apiClient } from '@/lib/api-client'
import AuditPage from '../audit/page'

const mockGetAuditExport = apiClient.getAuditExport as jest.MockedFunction<typeof apiClient.getAuditExport>

const sampleAuditResponse = {
  trace_id: 'trace-xyz-123',
  exported_at: '2024-01-01T00:00:00Z',
  operation: {
    id: 'op-001',
    trace_id: 'trace-xyz-123',
    actor_id: 'actor-1',
    actor_type: 'human',
    document_id: 'doc-1',
    artifact_digest: 'abcdef1234567890abcdef1234567890',
    policy_version: 'v1.0',
    status: 'completed',
    created_at: '2024-01-01T00:00:00Z',
    completed_at: '2024-01-01T00:01:00Z',
  },
  findings: [],
  redactions: [],
  artifacts: [],
  hmac_signature: 'hmac-signature-value',
}

beforeEach(() => {
  jest.clearAllMocks()
  // navigator.clipboard is read-only in jsdom — define via property descriptor
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: jest.fn().mockResolvedValue(undefined) },
    writable: true,
    configurable: true,
  })
  global.URL.createObjectURL = jest.fn(() => 'blob:mock')
  global.URL.revokeObjectURL = jest.fn()
})

describe('AuditPage', () => {
  it('renders the search form initially', () => {
    render(<AuditPage />)
    expect(
      screen.getByPlaceholderText('Introduce el trace_id (UUID completo o parcial)')
    ).toBeInTheDocument()
    expect(screen.getByText('Buscar')).toBeInTheDocument()
  })

  it('shows spinner during search', async () => {
    mockGetAuditExport.mockReturnValue(new Promise(() => {}))
    const user = userEvent.setup()
    render(<AuditPage />)

    const input = screen.getByPlaceholderText('Introduce el trace_id (UUID completo o parcial)')
    await user.type(input, 'trace-xyz-123')
    await user.click(screen.getByText('Buscar'))

    expect(screen.getByText('Buscando...')).toBeInTheDocument()
  })

  it('shows operation data after successful search', async () => {
    mockGetAuditExport.mockResolvedValue(sampleAuditResponse)
    const user = userEvent.setup()
    render(<AuditPage />)

    const input = screen.getByPlaceholderText('Introduce el trace_id (UUID completo o parcial)')
    await user.type(input, 'trace-xyz-123')

    await act(async () => {
      await user.click(screen.getByText('Buscar'))
    })

    await waitFor(() => {
      expect(screen.getByText('Resumen de operación')).toBeInTheDocument()
    })
    expect(screen.getByText('Completed')).toBeInTheDocument()
  })

  it('shows "Trace ID no encontrado" error when getAuditExport throws 404', async () => {
    mockGetAuditExport.mockRejectedValue(new Error('Audit export failed (404): not found'))
    const user = userEvent.setup()
    render(<AuditPage />)

    const input = screen.getByPlaceholderText('Introduce el trace_id (UUID completo o parcial)')
    await user.type(input, 'nonexistent-trace')

    await act(async () => {
      await user.click(screen.getByText('Buscar'))
    })

    await waitFor(() => {
      expect(screen.getByText('Trace ID no encontrado')).toBeInTheDocument()
    })
  })

  it('download button uses correct filename with trace_id', async () => {
    mockGetAuditExport.mockResolvedValue(sampleAuditResponse)
    const user = userEvent.setup()

    // Mock document.createElement to intercept anchor creation for download
    const mockClick = jest.fn()
    const mockAnchor = { href: '', download: '', click: mockClick }
    const originalCreateElement = document.createElement.bind(document)
    jest.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') return mockAnchor as unknown as HTMLElement
      return originalCreateElement(tag)
    })

    render(<AuditPage />)

    const input = screen.getByPlaceholderText('Introduce el trace_id (UUID completo o parcial)')
    await user.type(input, 'trace-xyz-123')

    await act(async () => {
      await user.click(screen.getByText('Buscar'))
    })

    await waitFor(() => {
      expect(screen.getByText('Descargar JSON')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Descargar JSON'))

    expect(mockAnchor.download).toBe('safecontext_audit_trace-xyz-123.json')
    expect(mockClick).toHaveBeenCalled()

    jest.restoreAllMocks()
  })
})
