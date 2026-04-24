/**
 * Tiny module-level store for the currently-selected agent + per-agent
 * unread badge counts.
 *
 * Why module-level instead of React Context:
 *   - Sidebar and MainChat are sibling components; a context would force
 *     lifting state into the page layout and adding a provider.
 *   - This store has no server dependency, no SSR hydration concerns
 *     (the page is a client component), and no need for per-subtree
 *     isolation. A single global is the simplest correct choice.
 *   - useSyncExternalStore gives us a concurrent-safe subscription without
 *     adding zustand or jotai.
 */
'use client'

import { useSyncExternalStore } from 'react'

import { AGENTS, DEFAULT_AGENT_ID, getAgent, type AgentMeta } from './agents'
import { fireAgentSwitch } from './activity-feed-store'
import { getUserSession, type UserSession } from './auth'

type Listener = () => void

export type Locale = 'en' | 'ar'

interface StoreState {
  currentAgentId: string
  unreadByAgent: Record<string, number>
  locale: Locale
  /** Agents this user is allowed to access (null = not yet loaded → show all) */
  accessibleAgentIds: string[] | null
  /** Logged-in user info (loaded from sessionStorage) */
  user: UserSession | null
}

const initialUnread: Record<string, number> = AGENTS.reduce(
  (acc, a) => {
    acc[a.id] = 0
    return acc
  },
  {} as Record<string, number>,
)

let state: StoreState = {
  currentAgentId: DEFAULT_AGENT_ID,
  unreadByAgent: initialUnread,
  locale: 'en',
  accessibleAgentIds: null,
  user: typeof window !== 'undefined' ? getUserSession() : null,
}

const listeners = new Set<Listener>()

function emit() {
  listeners.forEach((l) => l())
}

export function getCurrentAgentId(): string {
  return state.currentAgentId
}

export function setCurrentAgentId(id: string): void {
  if (!getAgent(id)) return
  if (state.currentAgentId === id) {
    // Still clear the badge if re-selecting
    if ((state.unreadByAgent[id] ?? 0) !== 0) {
      state = {
        ...state,
        unreadByAgent: { ...state.unreadByAgent, [id]: 0 },
      }
      emit()
    }
    return
  }
  const prev = state.currentAgentId
  state = {
    ...state,
    currentAgentId: id,
    unreadByAgent: { ...state.unreadByAgent, [id]: 0 },
  }
  emit()
  // Notify the activity feed about the agent switch
  fireAgentSwitch(prev, id)
}

export function getUnreadByAgent(): Record<string, number> {
  return state.unreadByAgent
}

export function incrementUnread(agentId: string): void {
  if (!getAgent(agentId)) return
  if (agentId === state.currentAgentId) return // already "seen"
  state = {
    ...state,
    unreadByAgent: {
      ...state.unreadByAgent,
      [agentId]: (state.unreadByAgent[agentId] ?? 0) + 1,
    },
  }
  emit()
}

export function getLocale(): Locale {
  return state.locale
}

export function setLocale(locale: Locale): void {
  if (state.locale === locale) return
  state = { ...state, locale }
  emit()
}

export function toggleLocale(): void {
  setLocale(state.locale === 'en' ? 'ar' : 'en')
}

export function setAccessibleAgentIds(ids: string[]): void {
  state = { ...state, accessibleAgentIds: ids }
  // If current agent is not accessible, switch to the first accessible one
  if (ids.length > 0 && !ids.includes(state.currentAgentId)) {
    state = { ...state, currentAgentId: ids[0] }
  }
  emit()
}

export function getAccessibleAgents(): AgentMeta[] {
  if (!state.accessibleAgentIds) return [...AGENTS]
  return AGENTS.filter((a) => state.accessibleAgentIds!.includes(a.id))
}

export function setUser(user: UserSession | null): void {
  state = { ...state, user }
  emit()
}

export function resetUnread(agentId: string): void {
  if ((state.unreadByAgent[agentId] ?? 0) === 0) return
  state = {
    ...state,
    unreadByAgent: { ...state.unreadByAgent, [agentId]: 0 },
  }
  emit()
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot(): StoreState {
  return state
}

function getServerSnapshot(): StoreState {
  return state
}

export interface UseCurrentAgentResult {
  agentId: string
  setAgentId: (id: string) => void
  agent: AgentMeta
  /** Only agents this user can access (filtered by backend RBAC) */
  visibleAgents: AgentMeta[]
  unreadByAgent: Record<string, number>
  locale: Locale
  toggleLocale: () => void
  user: UserSession | null
}

export function useCurrentAgent(): UseCurrentAgentResult {
  const snap = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  const agent = getAgent(snap.currentAgentId) ?? getAgent(DEFAULT_AGENT_ID)!
  const visibleAgents = snap.accessibleAgentIds
    ? AGENTS.filter((a) => snap.accessibleAgentIds!.includes(a.id))
    : [...AGENTS]
  return {
    agentId: snap.currentAgentId,
    setAgentId: setCurrentAgentId,
    agent,
    visibleAgents,
    unreadByAgent: snap.unreadByAgent,
    locale: snap.locale,
    toggleLocale,
    user: snap.user,
  }
}
