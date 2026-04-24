/**
 * Invisible component that subscribes to WS events and pushes FeedItems
 * into the activity-feed-store. Mounted once in ChatLayout.
 */
'use client'

import { useEffect, useRef } from 'react'

import { useWebSocket, type WsEnvelope } from '@/hooks/useWebSocket'
import {
  pushFeedItem,
  setOnAgentSwitch,
} from '@/lib/activity-feed-store'

let idCounter = 0
function feedId(): string {
  return `feed-${Date.now()}-${++idCounter}`
}

/** Unicode-safe slice that won't split surrogate pairs. */
function safeSlice(str: string, max: number): string {
  const chars = [...str]
  return chars.length <= max ? str : chars.slice(0, max).join('')
}

export default function ActivityFeedWatcher() {
  const { status, on } = useWebSocket()
  const prevStatus = useRef(status)

  // Connection status changes (skip initial idle→open transition)
  useEffect(() => {
    if (prevStatus.current === status) return
    const prev = prevStatus.current
    prevStatus.current = status
    // Don't push a "Connected" item on initial page load
    if (prev === 'idle') return
    pushFeedItem({
      id: feedId(),
      kind: 'connection',
      agent: '',
      timestamp: Date.now(),
      connectionStatus: status,
    })
  }, [status])

  // Agent switch callback
  useEffect(() => {
    setOnAgentSwitch((from, to) => {
      pushFeedItem({
        id: feedId(),
        kind: 'agent_switch',
        agent: to,
        timestamp: Date.now(),
        fromAgent: from,
        toAgent: to,
      })
    })
    return () => setOnAgentSwitch(null)
  }, [])

  // WS event subscriptions
  // NOTE: `on` is intentionally stable (useCallback with no deps in
  // useWebSocket) — do not add dependencies that would make it unstable.
  useEffect(() => {
    const offs: Array<() => void> = []

    offs.push(
      on('chat.tool.start', (env: WsEnvelope) => {
        const p = env.payload as Record<string, unknown> | null
        if (!p || !p.tool_name) return
        pushFeedItem({
          id: feedId(),
          kind: 'tool_start',
          agent: String(p.agent ?? ''),
          timestamp: Date.now(),
          toolName: String(p.tool_name),
          displayNameEn: p.display_name_en ? String(p.display_name_en) : undefined,
          displayNameAr: p.display_name_ar ? String(p.display_name_ar) : undefined,
        })
      }),
    )

    offs.push(
      on('chat.tool.result', (env: WsEnvelope) => {
        const p = env.payload as Record<string, unknown> | null
        if (!p || !p.tool_name) return
        pushFeedItem({
          id: feedId(),
          kind: 'tool_result',
          agent: String(p.agent ?? ''),
          timestamp: Date.now(),
          toolName: String(p.tool_name),
          displayNameEn: p.display_name_en ? String(p.display_name_en) : undefined,
          displayNameAr: p.display_name_ar ? String(p.display_name_ar) : undefined,
          toolSuccess: !!p.success,
          durationMs: (p.duration_ms as number) ?? null,
          resultSummary: p.result_summary
            ? safeSlice(String(p.result_summary), 80)
            : undefined,
        })
      }),
    )

    offs.push(
      on('chat.message.created', (env: WsEnvelope) => {
        const p = env.payload as Record<string, unknown> | null
        if (!p || !p.role) return
        pushFeedItem({
          id: feedId(),
          kind: p.role === 'user' ? 'user_message' : 'message',
          agent: String(p.agent ?? ''),
          timestamp: Date.now(),
        })
      }),
    )

    offs.push(
      on('error', (env: WsEnvelope) => {
        const p = env.payload as Record<string, unknown> | null
        pushFeedItem({
          id: feedId(),
          kind: 'error',
          agent: '',
          timestamp: Date.now(),
          errorMessage: p?.message ? String(p.message) : 'Unknown error',
        })
      }),
    )

    return () => offs.forEach((off) => off())
  }, [on])

  return null
}
