import { apiFetch } from './api'

export interface LoginResponse {
  token: string
  employee_id: string
  tenant_id: string
  name: string
  name_ar: string | null
  language: string
}

export interface UserSession {
  employeeId: string
  name: string
  nameAr: string | null
  language: string
  role?: string
}

/** Retrieve the stored user session (survives in-tab navigation).
 *  Falls back to decoding the JWT if krew_user wasn't saved (e.g. logged in
 *  before this code was deployed).
 */
export function getUserSession(): UserSession | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = sessionStorage.getItem('krew_user')
    if (raw) return JSON.parse(raw) as UserSession

    // Fallback: decode name from JWT payload
    const token = getAuthToken()
    if (token) {
      const payload = JSON.parse(atob(token.split('.')[1]))
      if (payload.name) {
        const session: UserSession = {
          employeeId: payload.sub ?? '',
          name: payload.name,
          nameAr: payload.name_ar ?? null,
          language: 'en',
        }
        // Persist for next time
        sessionStorage.setItem('krew_user', JSON.stringify(session))
        return session
      }
    }
  } catch { /* ignore */ }
  return null
}

function _saveUserSession(res: LoginResponse): void {
  if (typeof window === 'undefined') return
  try {
    sessionStorage.setItem(
      'krew_user',
      JSON.stringify({
        employeeId: res.employee_id,
        name: res.name,
        nameAr: res.name_ar,
        language: res.language,
      }),
    )
  } catch { /* SSR or private browsing */ }
}

/**
 * In-memory stash of the chat JWT. Populated on a successful login so that
 * the WebSocket client can append it as a `?token=...` query param — the
 * SameSite=Lax chat cookie is not sent on a cross-origin WS upgrade in dev
 * (frontend at :3000, backend at :8080).
 *
 * NOT persisted to localStorage on purpose: survives in-tab navigation via
 * this module's singleton, but a hard refresh requires re-login. That's the
 * security trade-off for avoiding long-lived tokens in browser storage.
 */
let _authToken: string | null = null

function _loadFromSession(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return sessionStorage.getItem('krew_chat_jwt')
  } catch {
    return null
  }
}

export function getAuthToken(): string | null {
  if (!_authToken) {
    _authToken = _loadFromSession()
  }
  return _authToken
}

export function setAuthToken(token: string | null): void {
  _authToken = token
  if (typeof window === 'undefined') return
  try {
    if (token) {
      sessionStorage.setItem('krew_chat_jwt', token)
    } else {
      sessionStorage.removeItem('krew_chat_jwt')
    }
  } catch { /* SSR or private browsing */ }
}

/**
 * Authenticate against POST /chat/auth/login.
 * Body: { employee_number, national_id_last4 }.
 * The backend sets an httpOnly `krew_chat_jwt` cookie on success and returns
 * the JWT in the body — we stash it in memory for the WS client.
 */
export async function login(
  employeeNumber: string,
  nationalIdLast4: string
): Promise<LoginResponse> {
  const res = await apiFetch<LoginResponse>('/chat/auth/login', {
    method: 'POST',
    body: JSON.stringify({
      employee_number: employeeNumber,
      national_id_last4: nationalIdLast4,
    }),
  })
  if (res?.token) {
    setAuthToken(res.token)
    _saveUserSession(res)
  }
  return res
}

/** POST /chat/auth/logout — relies on the cookie/Bearer token. */
export async function logout(): Promise<void> {
  try {
    await apiFetch('/chat/auth/logout', { method: 'POST' })
  } finally {
    setAuthToken(null)
    // Tear down the WS singleton so the next login gets a fresh connection
    // with the new user's token. Import dynamically to avoid circular deps.
    const { resetWebSocket } = await import('./ws')
    resetWebSocket()
  }
}
