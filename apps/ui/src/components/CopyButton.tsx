'use client'

import { useState } from 'react'

interface CopyButtonProps {
  text: string
  className?: string
}

export function CopyButton({ text, className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <button
      onClick={handleCopy}
      className={
        className ??
        'ml-2 text-xs px-1.5 py-0.5 border rounded text-gray-500 hover:text-brand hover:border-brand transition-colors'
      }
      title="Copiar al portapapeles"
    >
      {copied ? '✓' : 'Copiar'}
    </button>
  )
}
