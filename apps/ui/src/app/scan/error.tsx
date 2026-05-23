'use client'

import { useEffect } from 'react'

/**
 * Error boundary for the /scan route.
 *
 * Shows a contextual message and lets the user retry or navigate away.
 */
export default function ScanError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('[SafeContext:scan] Error:', error)
  }, [error])

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] px-4 text-center">
      <div className="rounded-xl border border-red-200 bg-red-50 p-8 max-w-md w-full shadow-sm">
        <h2 className="text-xl font-bold text-red-800 mb-2">
          Error en el escáner
        </h2>
        <p className="text-sm text-red-600 mb-4">
          No se pudo completar el escaneo. Verifica que el backend esté activo e
          intenta nuevamente.
        </p>
        {error.digest && (
          <p className="text-xs text-gray-400 mb-4 font-mono">
            Error ID: {error.digest}
          </p>
        )}
        <div className="flex gap-3 justify-center">
          <button
            onClick={reset}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm font-medium"
          >
            Reintentar
          </button>
          <a
            href="/dashboard"
            className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
          >
            Volver al dashboard
          </a>
        </div>
      </div>
    </div>
  )
}
