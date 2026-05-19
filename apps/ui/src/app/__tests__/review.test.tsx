import React from 'react'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock API client
jest.mock('@/lib/api-client', () => ({
  apiClient: {
    getPendingReviews: jest.fn(),
    postReviewDecision: jest.fn(),
  },
  ForbiddenError: class ForbiddenError extends Error {
    constructor(message = 'Forbidden') {
      super(message)
      this.name = 'ForbiddenError'
    }
  },
}))

// Mock useSession
jest.mock('@/hooks/useSession', () => ({
  useSession: () => ({
    user: { sub: 'user-1', name: 'Test', email: 'test@test.com', roles: ['reviewer'] },
    isLoading: false,
    hasRole: () => true,
  }),
}))

// Mock useToast at the ToastProvider module level
const mockShowToast = jest.fn()
jest.mock('@/components/ToastProvider', () => ({
  useToast: () => ({ showToast: mockShowToast }),
  ToastProvider: ({ children }: { children: React.ReactNode }) => children,
}))

import { apiClient } from '@/lib/api-client'
import ReviewPage from '../review/page'

const mockGetPendingReviews = apiClient.getPendingReviews as jest.MockedFunction<typeof apiClient.getPendingReviews>
const mockPostReviewDecision = apiClient.postReviewDecision as jest.MockedFunction<typeof apiClient.postReviewDecision>

const sampleFinding = {
  finding_id: 'f-001',
  operation_id: 'op-001',
  trace_id: 'trace-abc',
  detector: 'pii-detector',
  rule_id: 'rule-001',
  confidence: 0.9,
  severity: 'high' as const,
  span_start: 0,
  span_end: 5,
  explanation: {},
  document_preview: 'hello world',
  created_at: '2024-01-01T00:00:00Z',
}

beforeEach(() => {
  jest.clearAllMocks()
})

describe('ReviewPage', () => {
  it('shows spinner while loading', async () => {
    // getPendingReviews never resolves during this test
    mockGetPendingReviews.mockReturnValue(new Promise(() => {}))
    render(<ReviewPage />)
    // The loading spinner should appear
    expect(document.querySelector('main')).toBeInTheDocument()
    // There should be no findings list while loading
    expect(screen.queryByText('Sin revisiones pendientes')).not.toBeInTheDocument()
  })

  it('shows EmptyState when there are no findings', async () => {
    mockGetPendingReviews.mockResolvedValue({ total: 0, items: [] })
    await act(async () => {
      render(<ReviewPage />)
    })
    await waitFor(() => {
      expect(screen.getByText('Sin revisiones pendientes')).toBeInTheDocument()
    })
  })

  it('shows list of findings when data is available', async () => {
    mockGetPendingReviews.mockResolvedValue({ total: 1, items: [sampleFinding] })
    await act(async () => {
      render(<ReviewPage />)
    })
    await waitFor(() => {
      expect(screen.getByText('pii-detector')).toBeInTheDocument()
    })
  })

  it('opens modal when Aprobar button is clicked', async () => {
    const user = userEvent.setup()
    mockGetPendingReviews.mockResolvedValue({ total: 1, items: [sampleFinding] })
    await act(async () => {
      render(<ReviewPage />)
    })
    await waitFor(() => {
      expect(screen.getByText('Aprobar')).toBeInTheDocument()
    })
    await user.click(screen.getByText('Aprobar'))
    expect(screen.getByText('Aprobar hallazgo')).toBeInTheDocument()
  })

  it('calls postReviewDecision with correct action after confirming in modal', async () => {
    const user = userEvent.setup()
    mockGetPendingReviews.mockResolvedValue({ total: 1, items: [sampleFinding] })
    mockPostReviewDecision.mockResolvedValue({ trace_id: 'trace-abc', status: 'completed' })

    await act(async () => {
      render(<ReviewPage />)
    })
    await waitFor(() => expect(screen.getByText('Aprobar')).toBeInTheDocument())

    await user.click(screen.getByText('Aprobar'))
    await waitFor(() => expect(screen.getByText('Aprobar hallazgo')).toBeInTheDocument())

    const textarea = screen.getByPlaceholderText('Describe el motivo de tu decisión...')
    await user.type(textarea, 'This is a valid justification for this finding')

    await user.click(screen.getByText('Confirmar'))

    await waitFor(() => {
      expect(mockPostReviewDecision).toHaveBeenCalledWith(
        'f-001',
        'approve',
        'This is a valid justification for this finding'
      )
    })
  })

  it('shows error toast when backend returns an error', async () => {
    const user = userEvent.setup()
    mockGetPendingReviews.mockResolvedValue({ total: 1, items: [sampleFinding] })
    mockPostReviewDecision.mockRejectedValue(new Error('Backend failure'))

    await act(async () => {
      render(<ReviewPage />)
    })
    await waitFor(() => expect(screen.getByText('Aprobar')).toBeInTheDocument())

    await user.click(screen.getByText('Aprobar'))
    await waitFor(() => expect(screen.getByText('Aprobar hallazgo')).toBeInTheDocument())

    const textarea = screen.getByPlaceholderText('Describe el motivo de tu decisión...')
    await user.type(textarea, 'This is a valid justification for this finding')

    await user.click(screen.getByText('Confirmar'))

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith('Backend failure', 'error')
    })
  })
})
