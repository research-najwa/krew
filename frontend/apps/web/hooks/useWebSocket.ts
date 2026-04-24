'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  getWebSocket,
  resetWebSocket,
  type KrewWebSocket,
  type WsEnvelope,
  type WsHandler,
  type WsStatus,
} from '@/lib/ws'

export interface UseWebSocketApi {
  status: WsStatus
  send: (type: string, payload: unknown) => string
  on: (type: string, handler: WsHandler) => () => void
}

/**
 * React hook around the singleton KrewWebSocket.
 *
 * Auto-connects on mount and tracks connection status. The client itself is
 * a process-wide singleton, so multiple components mounting this hook share a
 * single socket — unmounting one does NOT close the connection for the others.
 * The socket stays open for the lifetime of the tab; logout/page-reset should
 * call resetWebSocket() explicitly.
 */
export function useWebSocket(): UseWebSocketApi {
  const clientRef = useRef<KrewWebSocket | null>(null)

  if (clientRef.current === null) {
    clientRef.current = getWebSocket()
  }

  const [status, setStatus] = useState<WsStatus>(clientRef.current?.status ?? 'idle')

  useEffect(() => {
    let client = clientRef.current
    if (!client) return

    // If singleton was left in a dead state (e.g. after auth redirect),
    // get a fresh one so connect() actually works.
    if (client.status === 'closed' || client.status === 'error') {
      resetWebSocket()
      client = getWebSocket()
      clientRef.current = client
    }

    setStatus(client.status)
    const unsubscribeStatus = client.onStatus((s) => {
      setStatus(s)
      if (s === 'auth_required' && typeof window !== 'undefined') {
        // JWT expired or missing — reset singleton and redirect to login
        resetWebSocket()
        clientRef.current = null
        sessionStorage.clear()
        window.location.href = '/login'
      }
    })
    client.connect()

    return () => {
      unsubscribeStatus()
      // Do NOT disconnect �� other mounted components may still need the socket.
    }
  }, [])

  const send = useCallback((type: string, payload: unknown): string => {
    const client = clientRef.current
    if (!client) return ''
    return client.send(type, payload)
  }, [])

  const on = useCallback((type: string, handler: WsHandler) => {
    const client = clientRef.current
    if (!client) return () => {}
    return client.on(type, handler)
  }, [])

  return { status, send, on }
}

export type { WsEnvelope, WsStatus }
