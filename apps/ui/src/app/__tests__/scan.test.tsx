import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock API client
jest.mock('@/lib/api-client', () => ({
  apiClient: {
    postScan: jest.fn(),
    getAuditExport: jest.fn(),
  },
}))

// Mock useSession
jest.mock('@/hooks/useSession', () => ({
  useSession: () => ({
    user: { sub: 'u1', name: 'Test', email: 'test@t.com', roles: ['viewer'] },
    isLoading: false,
    hasRole: () => false,
  }),
}))

// Mock CopyButton clipboard (not available in jsdom)
jest.mock('@/components', () => ({
  ...jest.requireActual('@/components'),
  CopyButton: ({ text }: { text: string }) => <button data-testid="copy-btn">{text}</button>,
  DocumentViewer: ({ text }: { text: string }) => <div data-testid="doc-viewer">{text}</div>,
}))

import { apiClient } from '@/lib/api-client'
import ScanPage from '../scan/page'

const mockPostScan = apiClient.postScan as jest.MockedFunction<typeof apiClient.postScan>
const mockGetAuditExport = apiClient.getAuditExport as jest.MockedFunction<typeof apiClient.getAuditExport>

beforeEach(() => jest.clearAllMocks())

describe('ScanPage', () => {
  it('renders idle state — textarea and disabled scan button', () => {
    render(<ScanPage />)
    expect(screen.getByPlaceholderText(/pega el texto/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /escanear/i })).toBeDisabled()
  })

  it('enables scan button when text is entered', async () => {
    const user = userEvent.setup()
    render(<ScanPage />)
    await user.type(screen.getByPlaceholderText(/pega el texto/i), 'Texto de prueba')
    expect(screen.getByRole('button', { name: /escanear/i })).not.toBeDisabled()
  })

  it('shows scanning state after clicking scan', async () => {
    const user = userEvent.setup()
    // postScan never resolves so the page stays in scanning state
    mockPostScan.mockReturnValue(new Promise(() => {}))
    render(<ScanPage />)
    await user.type(screen.getByPlaceholderText(/pega el texto/i), 'Texto de prueba')
    await user.click(screen.getByRole('button', { name: /escanear/i }))
    expect(await screen.findByText(/escaneando/i)).toBeInTheDocument()
  })

  it('shows clean result when no findings', async () => {
    const user = userEvent.setup()
    mockPostScan.mockResolvedValue({
      trace_id: 'trace-001',
      artifact_digest: 'sha256:abc',
      policy_version: '1.0.0',
      findings: [],
      requires_human_review: false,
    })
    mockGetAuditExport.mockResolvedValue({
      trace_id: 'trace-001',
      exported_at: new Date().toISOString(),
      operation: { status: 'completed', policy_version: '1.0.0', requires_human_review: false },
      findings: [],
      redactions: [],
      artifacts: [],
      hmac_signature: 'sig',
    })
    render(<ScanPage />)
    await user.type(screen.getByPlaceholderText(/pega el texto/i), 'Texto limpio')
    await user.click(screen.getByRole('button', { name: /escanear/i }))
    await waitFor(() =>
      expect(screen.getByText(/documento limpio/i)).toBeInTheDocument(),
      { timeout: 5000 }
    )
  })

  it('shows error state when postScan rejects', async () => {
    const user = userEvent.setup()
    mockPostScan.mockRejectedValue(new Error('Network error'))
    render(<ScanPage />)
    await user.type(screen.getByPlaceholderText(/pega el texto/i), 'Texto')
    await user.click(screen.getByRole('button', { name: /escanear/i }))
    await waitFor(() =>
      expect(screen.getByText(/error al escanear/i)).toBeInTheDocument(),
      { timeout: 3000 }
    )
  })

  it('shows retry button on error', async () => {
    const user = userEvent.setup()
    mockPostScan.mockRejectedValue(new Error('fail'))
    render(<ScanPage />)
    await user.type(screen.getByPlaceholderText(/pega el texto/i), 'Texto')
    await user.click(screen.getByRole('button', { name: /escanear/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /reintentar/i })).toBeInTheDocument(),
      { timeout: 3000 }
    )
  })
})
