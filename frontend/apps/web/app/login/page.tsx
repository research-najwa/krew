'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { login } from '@/lib/auth'

export default function LoginPage() {
  const router = useRouter()
  const [employeeNumber, setEmployeeNumber] = useState('')
  const [last4, setLast4] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(employeeNumber, last4)
      router.push('/chat')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm bg-surface border border-border rounded-2xl p-8 shadow-2xl">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-semibold text-ink">Krew</h1>
          <p className="text-sm text-ink-dim mt-1">Sign in to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-ink-dim mb-1.5">
              Employee number
            </label>
            <input
              type="text"
              value={employeeNumber}
              onChange={(e) => setEmployeeNumber(e.target.value)}
              required
              autoFocus
              className="w-full px-3 py-2 bg-surface-2 border border-border rounded-lg text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-agent-deema/40"
              placeholder="e.g. EMP-001"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-ink-dim mb-1.5">
              Last 4 digits of National ID
            </label>
            <input
              type="text"
              inputMode="numeric"
              pattern="\d{4}"
              maxLength={4}
              value={last4}
              onChange={(e) => setLast4(e.target.value.replace(/\D/g, ''))}
              required
              className="w-full px-3 py-2 bg-surface-2 border border-border rounded-lg text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-agent-deema/40 tracking-widest"
              placeholder="1234"
            />
          </div>

          {error && (
            <div className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-agent-deema hover:bg-agent-deema/90 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium transition-colors"
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </main>
  )
}
