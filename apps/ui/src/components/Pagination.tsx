'use client'

export function Pagination({
  total,
  page,
  pageSize,
  onPageChange,
}: {
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number) => void
}) {
  const totalPages = Math.ceil(total / pageSize)
  const start = (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)

  if (totalPages <= 1 && total === 0) return null

  const pages = buildPageRange(page, totalPages)

  return (
    <nav className="flex flex-col sm:flex-row items-center justify-between gap-3 py-3" aria-label="Pagination">
      <p className="text-sm text-gray-500">
        Mostrando {total === 0 ? 0 : start}–{end} de {total} resultados
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1}
          aria-label="Previous page"
          className="px-3 py-1.5 text-sm border rounded hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Anterior
        </button>

        {pages.map((p, i) =>
          p === '...' ? (
            <span key={`ellipsis-${i}`} className="px-2 py-1.5 text-sm text-gray-400">
              …
            </span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p as number)}
              aria-label={`Page ${p}`}
              aria-current={p === page ? 'page' : undefined}
              className={`px-3 py-1.5 text-sm border rounded transition-colors ${
                p === page
                  ? 'bg-brand text-white border-brand'
                  : 'hover:bg-gray-50'
              }`}
            >
              {p}
            </button>
          )
        )}

        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page === totalPages || totalPages === 0}
          aria-label="Next page"
          className="px-3 py-1.5 text-sm border rounded hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Siguiente
        </button>
      </div>
    </nav>
  )
}

function buildPageRange(current: number, total: number): (number | '...')[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }

  const pages: (number | '...')[] = [1]

  if (current > 3) pages.push('...')

  const rangeStart = Math.max(2, current - 1)
  const rangeEnd = Math.min(total - 1, current + 1)

  for (let i = rangeStart; i <= rangeEnd; i++) {
    pages.push(i)
  }

  if (current < total - 2) pages.push('...')

  pages.push(total)

  return pages
}
