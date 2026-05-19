type Status = 'pending' | 'completed' | 'escalated' | 'rejected'

const statusStyles: Record<Status, string> = {
  pending: 'bg-gray-100 text-gray-600',
  completed: 'bg-green-100 text-green-800',
  escalated: 'bg-amber-100 text-amber-800',
  rejected: 'bg-red-100 text-red-800',
}

const statusLabels: Record<Status, string> = {
  pending: 'Pending',
  completed: 'Completed',
  escalated: 'Escalated',
  rejected: 'Rejected',
}

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span
      className={`inline-block px-2 py-1 rounded text-xs font-semibold ${statusStyles[status]}`}
    >
      {statusLabels[status]}
    </span>
  )
}
