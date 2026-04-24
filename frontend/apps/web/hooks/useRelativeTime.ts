/**
 * Hook that returns a live-updating relative timestamp string.
 *
 * All consumers share a single 15-second interval. The interval is created
 * on first mount and cleaned up when no consumers remain.
 *
 * The getSnapshot callback caches the last formatted string to avoid
 * returning a new string reference on every call — useSyncExternalStore
 * compares by Object.is, so a new string with the same value would cause
 * unnecessary re-renders.
 */
'use client'

import { useRef, useSyncExternalStore } from 'react'

let tick = 0
const tickListeners = new Set<() => void>()
let intervalId: ReturnType<typeof setInterval> | null = null

function ensureInterval() {
  if (intervalId) return
  intervalId = setInterval(() => {
    tick++
    tickListeners.forEach((l) => l())
  }, 15_000)
}

function subscribeTick(listener: () => void): () => void {
  tickListeners.add(listener)
  ensureInterval()
  return () => {
    tickListeners.delete(listener)
    if (tickListeners.size === 0 && intervalId) {
      clearInterval(intervalId)
      intervalId = null
    }
  }
}

function formatRelative(epochMs: number): string {
  const diff = Math.max(0, Math.floor((Date.now() - epochMs) / 1000))
  if (diff < 5) return 'now'
  if (diff < 60) return `${diff}s`
  const mins = Math.floor(diff / 60)
  if (mins < 60) return `${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h`
  return `${Math.floor(hrs / 24)}d`
}

export function useRelativeTime(epochMs: number): string {
  // Cache the last formatted string to return a stable reference when the
  // output hasn't changed — prevents useSyncExternalStore from triggering
  // unnecessary re-renders.
  const cacheRef = useRef('')

  return useSyncExternalStore(
    subscribeTick,
    () => {
      const next = formatRelative(epochMs)
      if (next !== cacheRef.current) {
        cacheRef.current = next
      }
      return cacheRef.current
    },
    () => formatRelative(epochMs),
  )
}
