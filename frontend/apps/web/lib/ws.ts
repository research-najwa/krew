/**
 * Typed WebSocket client for the Krew real-time gateway.
 *
 * Envelope (v1):
 *   { v: 1, id: <ulid>, type: <string>, ts: <iso>, ref?: <string|null>, payload: {...} }
 *
 * Features:
 *  - Auto-reconnect with exponential backoff (1s → 30s cap)
 *  - Replies to server `ping` with `pong` automatically
 *  - Event emitter API: `.on(type, handler)` / `.off(type, handler)`
 *  - Logs known close codes (4401 auth, 4408 heartbeat, 4410 idle) with reasons
 *
 * Auth: in dev the Next.js app (localhost:3000) talks to the backend
 * (localhost:8080) cross-origin, and the SameSite=Lax chat cookie is NOT sent
 * on a cross-origin WS upgrade. We therefore pass the JWT via `?token=...`,
 * pulled from the in-memory token stash populated at login time. Prod can
 * switch to the cookie path by not providing a token.
 */

export interface WsEnvelope<P = unknown> {
  v: number
  id: string
  type: string
  ts: string
  ref?: string | null
  payload: P
}

export type WsStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error' | 'auth_required'

export type WsHandler = (envelope: WsEnvelope) => void

const CLOSE_CODE_REASONS: Record<number, string> = {
  4401: 'auth_required — JWT missing, invalid, or expired',
  4408: 'heartbeat_timeout — server did not receive pong in time',
  4410: 'idle_timeout — no client activity for 30 minutes',
}

function makeId(): string {
  const ts = Date.now().toString().padStart(13, '0')
  const rand = Math.random().toString(16).slice(2, 14).padEnd(12, '0')
  return `${ts}${rand}`
}

function nowIso(): string {
  return new Date().toISOString()
}

export class KrewWebSocket {
  private buildUrl: () => string
  private ws: WebSocket | null = null
  private handlers = new Map<string, Set<WsHandler>>()
  private statusHandlers = new Set<(s: WsStatus) => void>()
  private _status: WsStatus = 'idle'
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private explicitlyClosed = false

  constructor(buildUrl: () => string) {
    this.buildUrl = buildUrl
  }

  get status(): WsStatus {
    return this._status
  }

  private setStatus(s: WsStatus) {
    this._status = s
    for (const h of this.statusHandlers) {
      try {
        h(s)
      } catch (err) {
        console.error('[ws] status handler threw', err)
      }
    }
  }

  onStatus(handler: (s: WsStatus) => void): () => void {
    this.statusHandlers.add(handler)
    return () => this.statusHandlers.delete(handler)
  }

  on(type: string, handler: WsHandler): () => void {
    let bucket = this.handlers.get(type)
    if (!bucket) {
      bucket = new Set()
      this.handlers.set(type, bucket)
    }
    bucket.add(handler)
    return () => this.off(type, handler)
  }

  off(type: string, handler: WsHandler): void {
    const bucket = this.handlers.get(type)
    if (!bucket) return
    bucket.delete(handler)
    if (bucket.size === 0) this.handlers.delete(type)
  }

  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return
    }
    this.explicitlyClosed = false
    this.setStatus('connecting')

    let socket: WebSocket
    const url = this.buildUrl()
    console.log('[ws] connecting to', url.replace(/token=[^&]+/, 'token=***'))
    try {
      socket = new WebSocket(url)
    } catch (err) {
      console.error('[ws] failed to construct WebSocket', err)
      this.setStatus('error')
      this.scheduleReconnect()
      return
    }
    this.ws = socket

    socket.onopen = () => {
      this.reconnectAttempts = 0
      this.setStatus('open')
    }

    socket.onmessage = (event) => {
      let envelope: WsEnvelope
      try {
        envelope = JSON.parse(event.data) as WsEnvelope
      } catch {
        console.warn('[ws] received non-JSON frame', event.data)
        return
      }
      // Auto-respond to server heartbeat pings
      if (envelope.type === 'ping') {
        this.send('pong', {}, envelope.id)
        return
      }
      const bucket = this.handlers.get(envelope.type)
      if (bucket) {
        for (const h of bucket) {
          try {
            h(envelope)
          } catch (err) {
            console.error(`[ws] handler for "${envelope.type}" threw`, err)
          }
        }
      }
    }

    socket.onerror = (event) => {
      console.warn('[ws] socket error', event)
      this.setStatus('error')
    }

    socket.onclose = (event) => {
      const reason = CLOSE_CODE_REASONS[event.code]
      if (reason) {
        console.warn(`[ws] closed code=${event.code} (${reason}) wasClean=${event.wasClean}`)
      } else {
        console.log(`[ws] closed code=${event.code} reason="${event.reason}" wasClean=${event.wasClean}`)
      }
      this.ws = null
      if (!this.explicitlyClosed && event.code === 4401) {
        // Auth failure — surface specific status so UI can redirect to login
        this.setStatus('auth_required')
        return
      }
      this.setStatus('closed')
      if (!this.explicitlyClosed) {
        this.scheduleReconnect()
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer || this.explicitlyClosed) return
    // 1s, 2s, 4s, 8s, 16s, 30s (cap)
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30_000)
    this.reconnectAttempts += 1
    console.log(`[ws] reconnect attempt ${this.reconnectAttempts} in ${delay}ms`)
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  disconnect(code = 1000, reason = 'client_disconnect'): void {
    this.explicitlyClosed = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      try {
        this.ws.close(code, reason)
      } catch {
        // ignore
      }
      this.ws = null
    }
    this.setStatus('closed')
  }

  /**
   * Send an envelope to the server. Returns the generated envelope id so the
   * caller can correlate responses via the `ref` field.
   */
  send(type: string, payload: unknown, id?: string): string {
    const envelope: WsEnvelope = {
      v: 1,
      id: id ?? makeId(),
      type,
      ts: nowIso(),
      payload: (payload ?? {}) as unknown,
    }
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(envelope))
    } else {
      console.warn(`[ws] drop send: socket not open (type=${type})`)
    }
    return envelope.id
  }
}

// ── Singleton accessor ──────────────────────────────────────────────
let _singleton: KrewWebSocket | null = null

function buildWsUrl(): string {
  const base = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/api/v1/ws'
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { getAuthToken } = require('./auth') as typeof import('./auth')
  const token = getAuthToken()
  if (token) {
    const sep = base.includes('?') ? '&' : '?'
    return `${base}${sep}token=${encodeURIComponent(token)}`
  }
  return base
}

export function getWebSocket(): KrewWebSocket {
  if (!_singleton) {
    _singleton = new KrewWebSocket(buildWsUrl)
  }
  return _singleton
}

export function resetWebSocket(): void {
  if (_singleton) {
    _singleton.disconnect()
    _singleton = null
  }
}
