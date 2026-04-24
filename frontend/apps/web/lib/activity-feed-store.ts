/**
 * Module-level store for the Live Activity Feed.
 *
 * Same pattern as agent-store.ts — useSyncExternalStore with module state.
 * Stores a capped FIFO list of FeedItems and the collapsed/expanded state.
 *
 * IMPORTANT: `items` must always be replaced immutably (spread + slice).
 * Mutating in place (e.g. items.push()) will break snapshot diffing and
 * cause React to silently stop re-rendering.
 */
'use client'

import { useSyncExternalStore } from 'react'
import type { WsStatus } from '@/lib/ws'

export type FeedItemKind =
  | 'tool_start'
  | 'tool_result'
  | 'message'
  | 'user_message'
  | 'agent_switch'
  | 'error'
  | 'connection'

export interface FeedItem {
  id: string
  kind: FeedItemKind
  agent: string
  timestamp: number
  // tool fields
  toolName?: string
  displayNameEn?: string
  displayNameAr?: string
  toolSuccess?: boolean
  durationMs?: number | null
  resultSummary?: string
  // agent_switch
  fromAgent?: string
  toAgent?: string
  // error
  errorMessage?: string
  // connection
  connectionStatus?: WsStatus
}

const MAX_ITEMS = 100

// ── Module state ────────────────────────────────────────────────────
let items: FeedItem[] = []
// Always start false — read from localStorage post-hydration to avoid
// SSR/client mismatch (see initCollapsedFromStorage below).
let collapsed = false

const listeners = new Set<() => void>()

// RAF-coalesced emit: multiple pushFeedItem calls within a single frame
// are batched into one listener notification, preventing UI jank from
// event flooding (e.g. rapid tool.start + tool.result bursts).
let rafPending = false
function emit() {
  if (typeof requestAnimationFrame === 'undefined') {
    // SSR or test environment — fire synchronously
    listeners.forEach((l) => l())
    return
  }
  if (!rafPending) {
    rafPending = true
    requestAnimationFrame(() => {
      rafPending = false
      listeners.forEach((l) => l())
    })
  }
}

// ── Public mutators ─────────────────────────────────────────────────

export function pushFeedItem(item: FeedItem): void {
  if (items.length >= MAX_ITEMS) {
    items = [...items.slice(1), item]
  } else {
    items = [...items, item]
  }
  emit()
}

export function setCollapsed(val: boolean): void {
  collapsed = val
  try {
    localStorage.setItem('krew:feed-collapsed', val ? '1' : '0')
  } catch {
    // storage full or SSR
  }
  emit()
}

export function toggleCollapsed(): void {
  setCollapsed(!collapsed)
}

/**
 * Read collapsed state from localStorage. Must be called from a useEffect
 * (client-only) to avoid SSR hydration mismatch.
 */
export function initCollapsedFromStorage(): void {
  try {
    if (typeof window !== 'undefined') {
      const val = localStorage.getItem('krew:feed-collapsed')
      if (val === '1' && !collapsed) {
        collapsed = true
        emit()
      }
    }
  } catch {
    // SSR or storage unavailable
  }
}

// ── Agent switch callback ───────────────────────────────────────────
let _onAgentSwitch: ((from: string, to: string) => void) | null = null

export function setOnAgentSwitch(
  cb: ((from: string, to: string) => void) | null,
): void {
  _onAgentSwitch = cb
}

export function fireAgentSwitch(from: string, to: string): void {
  if (_onAgentSwitch) _onAgentSwitch(from, to)
}

// ── Subscriptions ───────────────────────────────────────────────────

interface FeedSnapshot {
  items: FeedItem[]
  collapsed: boolean
}

let snapshot: FeedSnapshot = { items, collapsed }

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot(): FeedSnapshot {
  const next: FeedSnapshot = { items, collapsed }
  if (next.items !== snapshot.items || next.collapsed !== snapshot.collapsed) {
    snapshot = next
  }
  return snapshot
}

const serverSnapshot: FeedSnapshot = { items: [], collapsed: false }
function getServerSnapshot(): FeedSnapshot {
  return serverSnapshot
}

export function useActivityFeed(): FeedSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
