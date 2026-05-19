'use client'

import { useEffect, useRef, useState } from 'react'

const MIN_JUSTIFICATION_LENGTH = 20

export function ConfirmModal({
  isOpen,
  title,
  description,
  action,
  onConfirm,
  onCancel,
  isLoading = false,
}: {
  isOpen: boolean
  title: string
  description?: string
  action: 'approve' | 'reject'
  onConfirm: (justification: string) => void
  onCancel: () => void
  isLoading?: boolean
}) {
  const [justification, setJustification] = useState('')
  const [touched, setTouched] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (isOpen) {
      setJustification('')
      setTouched(false)
      setTimeout(() => textareaRef.current?.focus(), 50)
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onCancel])

  if (!isOpen) return null

  const isValid = justification.length >= MIN_JUSTIFICATION_LENGTH
  const showError = touched && !isValid

  const confirmClasses =
    action === 'approve'
      ? 'bg-green-600 hover:bg-green-700 disabled:bg-green-300'
      : 'bg-red-600 hover:bg-red-700 disabled:bg-red-300'

  const titleColor = action === 'approve' ? 'text-green-700' : 'text-red-700'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div className="w-full max-w-md bg-white rounded-xl shadow-xl p-6">
        <h2 className={`text-lg font-semibold mb-1 ${titleColor}`}>{title}</h2>
        {description && <p className="text-sm text-gray-600 mb-4">{description}</p>}

        <label className="block mb-1">
          <span className="text-sm font-medium text-gray-700">Justificación</span>
          <textarea
            ref={textareaRef}
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="Describe el motivo de tu decisión..."
            rows={4}
            className={`mt-1 w-full px-3 py-2 text-sm border rounded-lg resize-none focus:outline-none focus:ring-2 ${
              showError
                ? 'border-red-400 focus:ring-red-300'
                : 'border-gray-300 focus:ring-brand/30'
            }`}
          />
        </label>

        <div className="flex justify-between items-center mb-4">
          {showError ? (
            <p className="text-xs text-red-500">
              Mínimo {MIN_JUSTIFICATION_LENGTH} caracteres
            </p>
          ) : (
            <span />
          )}
          <p className="text-xs text-gray-400 ml-auto">
            {justification.length}/{MIN_JUSTIFICATION_LENGTH} mínimo
          </p>
        </div>

        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={() => onConfirm(justification)}
            disabled={!isValid || isLoading}
            className={`px-4 py-2 text-sm text-white rounded-lg transition-colors disabled:cursor-not-allowed ${confirmClasses}`}
          >
            {isLoading ? 'Procesando...' : 'Confirmar'}
          </button>
        </div>
      </div>
    </div>
  )
}
