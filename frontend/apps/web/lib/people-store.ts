/**
 * Module-level store for DM (people) state — selected peer, conversations,
 * unread counts, and online presence.
 *
 * Same pattern as agent-store.ts: useSyncExternalStore for concurrent-safe
 * React subscriptions without extra deps.
 */
'use client'

import { useSyncExternalStore } from 'react'

type Listener = () => void

export interface Colleague {
  id: string
  name: string
  nameAr: string | null
  jobTitle: string
  departmentName: string | null
  departmentNameAr: string | null
}

export interface DmConversation {
  id: string
  peerId: string
  peerName: string
  peerNameAr: string | null
  peerJobTitle: string
  lastMessage: string | null
  lastMessageAt: string | null
  unreadCount: number
}

export interface DmMessage {
  id: string
  senderId: string
  content: string
  createdAt: string
  isEdited: boolean
}

/** Info about the currently selected peer (for new conversations without history) */
export interface SelectedPeerInfo {
  id: string
  name: string
  nameAr: string | null
  jobTitle: string
}

interface PeopleState {
  /** Currently selected peer employee ID (null = no DM open) */
  selectedPeerId: string | null
  /** Info about the selected peer (set when selecting from search) */
  selectedPeerInfo: SelectedPeerInfo | null
  /** Cached DM conversations list */
  conversations: DmConversation[]
  /** Per-peer unread badge counts */
  unreadByPeer: Record<string, number>
  /** Peer IDs that are currently typing */
  typingPeers: Set<string>
}

let state: PeopleState = {
  selectedPeerId: null,
  selectedPeerInfo: null,
  conversations: [],
  unreadByPeer: {},
  typingPeers: new Set(),
}

const listeners = new Set<Listener>()

function emit() {
  listeners.forEach((l) => l())
}

// ── Public setters ──────────────────────────────────────────────

export function setSelectedPeer(peerId: string | null, info?: SelectedPeerInfo): void {
  if (state.selectedPeerId === peerId) return
  const newUnread = { ...state.unreadByPeer }
  if (peerId) newUnread[peerId] = 0
  state = { ...state, selectedPeerId: peerId, selectedPeerInfo: info ?? null, unreadByPeer: newUnread }
  emit()
}

export function clearSelectedPeer(): void {
  if (state.selectedPeerId === null) return
  state = { ...state, selectedPeerId: null }
  emit()
}

export function setConversations(convos: DmConversation[]): void {
  const unread: Record<string, number> = {}
  for (const c of convos) {
    unread[c.peerId] = c.unreadCount
  }
  state = { ...state, conversations: convos, unreadByPeer: unread }
  emit()
}

export function incrementPeerUnread(peerId: string): void {
  if (peerId === state.selectedPeerId) return // already viewing
  state = {
    ...state,
    unreadByPeer: {
      ...state.unreadByPeer,
      [peerId]: (state.unreadByPeer[peerId] ?? 0) + 1,
    },
  }
  emit()
}

export function setPeerTyping(peerId: string, isTyping: boolean): void {
  const next = new Set(state.typingPeers)
  if (isTyping) next.add(peerId)
  else next.delete(peerId)
  state = { ...state, typingPeers: next }
  emit()
}

export function updateConversationLastMessage(
  peerId: string,
  text: string,
  timestamp: string,
): void {
  const updated = state.conversations.map((c) =>
    c.peerId === peerId
      ? { ...c, lastMessage: text.slice(0, 100), lastMessageAt: timestamp }
      : c,
  )
  // Move the updated conversation to the top
  updated.sort((a, b) => {
    const ta = a.lastMessageAt ?? ''
    const tb = b.lastMessageAt ?? ''
    return tb.localeCompare(ta)
  })
  state = { ...state, conversations: updated }
  emit()
}

// ── Subscription ────────────────────────────────────────────────

export function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot(): PeopleState {
  return state
}

function getServerSnapshot(): PeopleState {
  return state
}

// ── React hook ──────────────────────────────────────────────────

export interface UsePeopleResult {
  selectedPeerId: string | null
  selectedPeerInfo: SelectedPeerInfo | null
  setSelectedPeer: (id: string | null, info?: SelectedPeerInfo) => void
  clearSelectedPeer: () => void
  conversations: DmConversation[]
  unreadByPeer: Record<string, number>
  typingPeers: Set<string>
  totalUnread: number
}

export function usePeople(): UsePeopleResult {
  const snap = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  const totalUnread = Object.values(snap.unreadByPeer).reduce((s, n) => s + n, 0)
  return {
    selectedPeerId: snap.selectedPeerId,
    selectedPeerInfo: snap.selectedPeerInfo,
    setSelectedPeer,
    clearSelectedPeer,
    conversations: snap.conversations,
    unreadByPeer: snap.unreadByPeer,
    typingPeers: snap.typingPeers,
    totalUnread,
  }
}
