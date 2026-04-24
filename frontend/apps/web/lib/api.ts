/**
 * Thin fetch wrapper for the Krew FastAPI backend.
 *
 * In dev, NEXT_PUBLIC_API_BASE defaults to "/api/v1" and Next.js rewrites
 * /api/* to http://localhost:8080/api/* (see next.config.js), so the browser
 * sees a same-origin request and we avoid CORS entirely.
 *
 * The backend's /chat/auth/login endpoint sets an httpOnly `krew_chat_jwt`
 * cookie, so we always send credentials. It also returns a Bearer token in
 * the JSON body — callers that want to use Bearer auth can capture it.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/v1'

export class ApiError extends Error {
  status: number
  body: string
  constructor(status: number, body: string, message: string) {
    super(message)
    this.status = status
    this.body = body
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  // Attach Bearer token for authenticated requests
  const authHeaders: Record<string, string> = {}
  try {
    const { getAuthToken } = await import('./auth')
    const token = getAuthToken()
    if (token) authHeaders['Authorization'] = `Bearer ${token}`
  } catch { /* auth module not available */ }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...authHeaders,
      ...(init.headers || {}),
    },
  })

  const text = await res.text()
  if (!res.ok) {
    let message = `API ${res.status}`
    try {
      const parsed = JSON.parse(text) as { detail?: string; message?: string }
      message = parsed.detail || parsed.message || message
    } catch {
      if (text) message = text
    }
    throw new ApiError(res.status, text, message)
  }

  if (!text) return undefined as T
  try {
    return JSON.parse(text) as T
  } catch {
    return text as unknown as T
  }
}
