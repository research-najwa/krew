'use client'

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'

import { useWebSocket, type WsEnvelope } from '@/hooks/useWebSocket'
import {
  usePeople,
  incrementPeerUnread,
  setPeerTyping,
  updateConversationLastMessage,
} from '@/lib/people-store'
import { useCurrentAgent } from '@/lib/agent-store'
import { AGENTS, getAgent } from '@/lib/agents'
import { apiFetch } from '@/lib/api'

// ── Types ───────────────────────────────────────────────────────

interface DmMsg {
  id: string
  senderId: string
  content: string
  createdAt: string
  isEdited: boolean
  isDeleted: boolean
  messageType: 'human' | 'agent' | 'system'
  agentName: string | null
  replyToId: string | null
  reactions: Record<string, string[]> | null
  attachments: Array<{ type: string; url: string; name: string; size?: number; duration_sec?: number }> | null
  pending?: boolean
}

interface DmMessagePayload {
  conversation_id: string
  message_id: string
  sender_id: string
  peer_id: string
  text: string
  created_at: string
  message_type?: string
  agent_name?: string
  reply_to_id?: string | null
  attachments?: unknown[] | null
}

interface DmTypingPayload {
  sender_id: string
  peer_id: string
}

interface PeerProfile {
  id: string
  name: string
  name_ar: string | null
  email: string
  phone: string | null
  job_title: string
  department_name: string | null
  department_name_ar: string | null
  hire_date: string | null
  is_saudi: boolean
}

const STATUS_LABEL: Record<string, string> = {
  idle: 'Connecting…',
  connecting: 'Connecting…',
  open: 'Online',
  closed: 'Disconnected',
  error: 'Connection error',
  auth_required: 'Session expired',
}

const EMOJI_PALETTE = ['👍', '❤️', '😂', '🎉', '🔥', '👀', '✅', '💯']

// ── Component ───────────────────────────────────────────────────

export default function DmChat() {
  const { status, send, on } = useWebSocket()
  const { selectedPeerId, selectedPeerInfo, conversations, typingPeers } = usePeople()
  const { locale, user, visibleAgents } = useCurrentAgent()

  const [messages, setMessages] = useState<DmMsg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Feature state
  const [replyTo, setReplyTo] = useState<DmMsg | null>(null)
  const [editingMsg, setEditingMsg] = useState<DmMsg | null>(null)
  const [editText, setEditText] = useState('')
  const [showEmojiFor, setShowEmojiFor] = useState<string | null>(null)
  const [showSearch, setShowSearch] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<DmMsg[]>([])
  const [showProfile, setShowProfile] = useState(false)
  const [profile, setProfile] = useState<PeerProfile | null>(null)
  const [mentionFilter, setMentionFilter] = useState<string | null>(null)
  const [deployedAgents, setDeployedAgents] = useState<Array<{ id: string; name: string; nameAr: string | null; roleTitle: string }>>([])

  const [pinnedIds, setPinnedIds] = useState<string[]>([])
  const [contextMenu, setContextMenu] = useState<{ msgId: string; x: number; y: number } | null>(null)

  const scrollRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastPeerRef = useRef<string | null>(null)

  const isAr = locale === 'ar'
  const peer = conversations.find((c) => c.peerId === selectedPeerId)
  const peerName = peer
    ? isAr && peer.peerNameAr ? peer.peerNameAr : peer.peerName
    : selectedPeerInfo
      ? isAr && selectedPeerInfo.nameAr ? selectedPeerInfo.nameAr : selectedPeerInfo.name
      : ''
  const peerJobTitle = peer?.peerJobTitle ?? selectedPeerInfo?.jobTitle ?? ''
  const peerInitial = peerName.charAt(0).toUpperCase()
  const isTyping = selectedPeerId ? typingPeers.has(selectedPeerId) : false
  const myId = user?.employeeId ?? ''

  // ── Data loading ────────────────────────────────────────────

  useEffect(() => {
    if (!selectedPeerId) {
      setMessages([])
      return
    }
    if (selectedPeerId === lastPeerRef.current) return
    lastPeerRef.current = selectedPeerId
    setReplyTo(null)
    setEditingMsg(null)
    setShowSearch(false)
    setShowProfile(false)

    setLoading(true)
    setMessages([])
    apiFetch<Array<{
      id: string; sender_id: string; content: string; created_at: string
      is_edited: boolean; is_deleted: boolean; message_type: string
      agent_name: string | null; reply_to_id: string | null
      reactions: Record<string, string[]> | null; attachments: unknown[] | null
    }>>(`/dm/conversations/${selectedPeerId}/messages?limit=50`)
      .then((data) => {
        if (Array.isArray(data)) {
          setMessages(data.map((m) => ({
            id: m.id,
            senderId: m.sender_id,
            content: m.content,
            createdAt: m.created_at,
            isEdited: m.is_edited,
            isDeleted: m.is_deleted ?? false,
            messageType: (m.message_type as DmMsg['messageType']) || 'human',
            agentName: m.agent_name,
            replyToId: m.reply_to_id,
            reactions: m.reactions,
            attachments: m.attachments as DmMsg['attachments'],
          })))
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))

    apiFetch(`/dm/conversations/${selectedPeerId}/read`, { method: 'POST' }).catch(() => {})
  }, [selectedPeerId])

  // Auto-scroll
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  useEffect(() => {
    apiFetch<Array<{ id: string; name: string; name_ar: string | null; job_title: string; is_bot?: boolean }>>('/dm/colleagues')
      .then((data) => {
        if (Array.isArray(data)) {
          setDeployedAgents(
            data.filter((c) => c.is_bot).map((a) => ({ id: a.name, name: a.name, nameAr: a.name_ar, roleTitle: a.job_title }))
          )
        }
      })
      .catch(() => {})
  }, [])

  // ── WS subscriptions ────────────────────────────────────────

  useEffect(() => {
    const offDmMessage = on('dm.message.created', (env: WsEnvelope) => {
      const p = env.payload as DmMessagePayload
      console.log('[DM] dm.message.created received:', { type: p?.message_type, agent: p?.agent_name, sender: p?.sender_id, peer: p?.peer_id, selectedPeerId, myId })
      if (!p || !p.message_id) return

      const newMsg: DmMsg = {
        id: p.message_id,
        senderId: p.sender_id,
        content: p.text,
        createdAt: p.created_at,
        isEdited: false,
        isDeleted: false,
        messageType: (p.message_type as DmMsg['messageType']) || 'human',
        agentName: p.agent_name ?? null,
        replyToId: p.reply_to_id ?? null,
        reactions: null,
        attachments: p.attachments as DmMsg['attachments'] ?? null,
      }

      const isPeerMsg = p.sender_id === selectedPeerId
      const isMyMsg = p.sender_id === myId
      // Agent messages come with sender_id = invoker, message_type = "agent"
      const isAgentForThisDm = p.message_type === 'agent' && (
        p.peer_id === selectedPeerId || p.sender_id === selectedPeerId ||
        p.peer_id === myId || p.sender_id === myId
      )

      if (isPeerMsg || isMyMsg || isAgentForThisDm) {
        setMessages((prev) => {
          if (prev.some((m) => m.id === p.message_id)) return prev
          const filtered = prev.filter((m) => !(m.pending && m.content === p.text && m.senderId === p.sender_id))
          return [...filtered, newMsg]
        })
        if (isMyMsg && p.message_type !== 'agent') setSending(false)
        if (isPeerMsg && p.message_type === 'agent') setSending(false)
        if (isPeerMsg && selectedPeerId) {
          apiFetch(`/dm/conversations/${selectedPeerId}/read`, { method: 'POST' }).catch(() => {})
        }
      } else {
        incrementPeerUnread(p.sender_id)
      }

      const peerId = p.sender_id === myId ? p.peer_id : p.sender_id
      updateConversationLastMessage(peerId, p.text, p.created_at)
    })

    const offDmTyping = on('dm.typing', (env: WsEnvelope) => {
      const p = env.payload as DmTypingPayload
      if (!p || !p.sender_id) return
      setPeerTyping(p.sender_id, true)
      setTimeout(() => setPeerTyping(p.sender_id, false), 3000)
    })

    return () => {
      offDmMessage()
      offDmTyping()
    }
  }, [on, selectedPeerId, myId])

  // ── Actions ─────────────────────────────────────────────────

  async function uploadDmFile(
    file: File | Blob,
    filename?: string,
  ): Promise<{ type: string; url: string; name: string; size: number; duration_sec?: number }> {
    const fd = new FormData()
    if (filename) {
      fd.append('file', file, filename)
    } else {
      fd.append('file', file)
    }
    const { getAuthToken } = await import('@/lib/auth')
    const token = getAuthToken()
    const res = await fetch('/api/v1/dm/upload', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    })
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
    return res.json()
  }

  const sendTyping = useCallback(() => {
    if (!selectedPeerId || status !== 'open') return
    if (typingTimerRef.current) return
    send('dm.typing', { peer_id: selectedPeerId })
    typingTimerRef.current = setTimeout(() => {
      typingTimerRef.current = null
    }, 2000)
  }, [selectedPeerId, status, send])

  async function sendMessage(text: string) {
    if (!text || sending || !selectedPeerId) return
    const optimisticId = `pending-${Date.now()}`
    const replyId = replyTo?.id ?? null
    setMessages((prev) => [
      ...prev,
      {
        id: optimisticId,
        senderId: myId,
        content: text,
        createdAt: new Date().toISOString(),
        isEdited: false,
        isDeleted: false,
        messageType: 'human',
        agentName: null,
        replyToId: replyId,
        reactions: null,
        attachments: null,
        pending: true,
      },
    ])
    setInput('')
    setReplyTo(null)
    setSending(true)
    setError(null)

    const hasMention = text.includes('@')

    if (status === 'open') {
      // Prefer WebSocket when connected
      send('dm.send', {
        peer_id: selectedPeerId,
        text,
        reply_to_id: replyId,
      })
      setTimeout(() => setSending(false), 10_000)

      // If message has @mention, poll for agent response as fallback
      if (hasMention && selectedPeerId) {
        const peerId = selectedPeerId
        const pollForAgent = async (attempt: number) => {
          if (attempt > 5) return
          await new Promise((r) => setTimeout(r, 3000))
          try {
            const msgs = await apiFetch<Array<{
              id: string; sender_id: string; content: string; created_at: string
              is_edited: boolean; is_deleted: boolean; message_type: string
              agent_name: string | null; reply_to_id: string | null
              reactions: Record<string, string[]> | null; attachments: unknown[] | null
            }>>(`/dm/conversations/${peerId}/messages?limit=5`)
            if (Array.isArray(msgs)) {
              const agentMsgs = msgs.filter((m) => m.message_type === 'agent')
              if (agentMsgs.length > 0) {
                setMessages((prev) => {
                  const existingIds = new Set(prev.map((m) => m.id))
                  const newAgentMsgs = agentMsgs
                    .filter((m) => !existingIds.has(m.id))
                    .map((m) => ({
                      id: m.id,
                      senderId: m.sender_id,
                      content: m.content,
                      createdAt: m.created_at,
                      isEdited: m.is_edited,
                      isDeleted: m.is_deleted ?? false,
                      messageType: (m.message_type as DmMsg['messageType']) || 'human',
                      agentName: m.agent_name,
                      replyToId: m.reply_to_id,
                      reactions: m.reactions,
                      attachments: m.attachments as DmMsg['attachments'],
                    }))
                  if (newAgentMsgs.length === 0) return prev
                  return [...prev, ...newAgentMsgs]
                })
                return
              }
            }
            pollForAgent(attempt + 1)
          } catch { /* ignore */ }
        }
        pollForAgent(0)
      }
    } else {
      // REST fallback when WS is not connected
      try {
        const res = await apiFetch<{ id: string; created_at: string }>(`/dm/conversations/${selectedPeerId}/send`, {
          method: 'POST',
          body: JSON.stringify({ text, reply_to_id: replyId }),
        })
        // Replace optimistic message with real one
        setMessages((prev) =>
          prev.map((m) => m.id === optimisticId ? { ...m, id: res.id, createdAt: res.created_at, pending: false } : m),
        )
        updateConversationLastMessage(selectedPeerId, text, res.created_at)
      } catch (err) {
        console.error('[DM] REST send failed:', err)
        setError(isAr ? 'فشل إرسال الرسالة' : 'Failed to send message')
        setTimeout(() => setError(null), 3000)
        // Remove optimistic message on failure
        setMessages((prev) => prev.filter((m) => m.id !== optimisticId))
      } finally {
        setSending(false)
      }
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    sendMessage(input.trim())
  }

  async function toggleReaction(msgId: string, emoji: string) {
    setShowEmojiFor(null)
    try {
      const res = await apiFetch<{ reactions: Record<string, string[]> }>(`/dm/messages/${msgId}/react`, {
        method: 'POST',
        body: JSON.stringify({ emoji }),
      })
      setMessages((prev) =>
        prev.map((m) => m.id === msgId ? { ...m, reactions: res.reactions && Object.keys(res.reactions).length ? res.reactions : null } : m),
      )
    } catch { /* ignore */ }
  }

  async function deleteMessage(msgId: string) {
    setContextMenu(null)
    try {
      await apiFetch(`/dm/messages/${msgId}`, { method: 'DELETE' })
      setMessages((prev) =>
        prev.map((m) => m.id === msgId ? { ...m, isDeleted: true, content: isAr ? 'تم حذف الرسالة' : 'This message was deleted' } : m),
      )
    } catch { /* ignore */ }
  }

  async function saveEdit(msgId: string) {
    const text = editText.trim()
    if (!text) return
    try {
      await apiFetch(`/dm/messages/${msgId}`, {
        method: 'PATCH',
        body: JSON.stringify({ content: text }),
      })
      setMessages((prev) =>
        prev.map((m) => m.id === msgId ? { ...m, content: text, isEdited: true } : m),
      )
    } catch { /* ignore */ }
    setEditingMsg(null)
    setEditText('')
  }

  async function togglePin(msgId: string) {
    setContextMenu(null)
    if (!selectedPeerId) return
    try {
      const res = await apiFetch<{ pinned_message_ids: string[] }>(
        `/dm/conversations/${selectedPeerId}/pin`,
        { method: 'POST', body: JSON.stringify({ message_id: msgId }) },
      )
      setPinnedIds(res.pinned_message_ids ?? [])
    } catch { /* ignore */ }
  }

  async function doSearch(q: string) {
    if (!q.trim() || !selectedPeerId) {
      setSearchResults([])
      return
    }
    try {
      const data = await apiFetch<Array<{
        id: string; sender_id: string; content: string; created_at: string
        is_edited: boolean; is_deleted: boolean; message_type: string
        agent_name: string | null; reply_to_id: string | null
        reactions: Record<string, string[]> | null; attachments: unknown[] | null
      }>>(`/dm/conversations/${selectedPeerId}/search?q=${encodeURIComponent(q)}`)
      if (Array.isArray(data)) {
        setSearchResults(data.map((m) => ({
          id: m.id,
          senderId: m.sender_id,
          content: m.content,
          createdAt: m.created_at,
          isEdited: m.is_edited,
          isDeleted: false,
          messageType: (m.message_type as DmMsg['messageType']) || 'human',
          agentName: m.agent_name,
          replyToId: m.reply_to_id,
          reactions: m.reactions,
          attachments: m.attachments as DmMsg['attachments'],
        })))
      }
    } catch { /* ignore */ }
  }

  async function loadProfile() {
    if (!selectedPeerId) return
    try {
      const data = await apiFetch<PeerProfile>(`/dm/employees/${selectedPeerId}/profile`)
      setProfile(data)
      setShowProfile(true)
    } catch { /* ignore */ }
  }

  function forwardToAgent(msg: DmMsg, agentId: string) {
    setContextMenu(null)
    // Send the message content as an @mention to the agent
    const text = `@${agentId} ${msg.content}`
    sendMessage(text)
  }

  // ── @mention autocomplete ───────────────────────────────────

  function handleInputChange(value: string) {
    setInput(value)
    sendTyping()
    // Detect @mention trigger
    const atIdx = value.lastIndexOf('@')
    if (atIdx >= 0 && (atIdx === 0 || value[atIdx - 1] === ' ')) {
      const fragment = value.slice(atIdx + 1).toLowerCase()
      if (fragment.length <= 20 && !fragment.includes(' ')) {
        setMentionFilter(fragment)
        return
      }
    }
    setMentionFilter(null)
  }

  function insertMention(agentId: string) {
    const atIdx = input.lastIndexOf('@')
    if (atIdx >= 0) {
      setInput(input.slice(0, atIdx) + `@${agentId} `)
    }
    setMentionFilter(null)
    inputRef.current?.focus()
  }

  const filteredAgents = mentionFilter !== null
    ? [
        ...AGENTS.filter((a) =>
          a.id.startsWith(mentionFilter!) ||
          a.name.toLowerCase().startsWith(mentionFilter!) ||
          a.nameAr.startsWith(mentionFilter!),
        ).map((a) => ({ id: a.id, name: a.name, nameAr: a.nameAr, role: isAr ? a.roleAr : a.role, initial: a.initial, colorClass: a.colorClass, isDeployed: false })),
        ...deployedAgents.filter((a) =>
          a.name.toLowerCase().startsWith(mentionFilter!) ||
          (a.nameAr && a.nameAr.startsWith(mentionFilter!)),
        ).map((a) => ({ id: a.name, name: a.name, nameAr: a.nameAr ?? a.name, role: a.roleTitle, initial: a.name.charAt(0).toUpperCase(), colorClass: 'bg-emerald-600', isDeployed: true })),
      ]
    : []

  // ── Helpers ─────────────────────────────────────────────────

  function getReplyPreview(replyId: string | null): string | null {
    if (!replyId) return null
    const orig = messages.find((m) => m.id === replyId)
    return orig ? orig.content.slice(0, 60) : null
  }

  function getAgentMeta(name: string | null) {
    if (!name) return null
    return getAgent(name)
  }

  if (!selectedPeerId) return null

  const statusLabel = STATUS_LABEL[status] ?? status
  const statusDot = status === 'open' ? 'bg-emerald-500' : status === 'connecting' || status === 'idle' ? 'bg-amber-500' : 'bg-rose-500'

  // ── Render ──────────────────────────────────────────────────

  return (
    <section dir={isAr ? 'rtl' : 'ltr'} className="chat-light flex-1 min-w-0 min-h-0 bg-white flex flex-col">
      {/* ── Header ── */}
      <header className="h-12 px-5 border-b border-[#e0e0e0] flex items-center justify-between bg-white">
        <div className="flex items-center gap-2">
          <button onClick={loadProfile} className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <span className="w-7 h-7 rounded-full bg-[#1264a3]/20 text-[#1264a3] text-[11px] font-bold flex items-center justify-center shrink-0">
              {peerInitial}
            </span>
            <span className="text-[15px] font-bold text-[#1d1c1d]">{peerName}</span>
          </button>
          {peerJobTitle && (
            <span className="text-xs text-[#616061]">{peerJobTitle}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {/* Search button */}
          <button
            onClick={() => { setShowSearch((v) => !v); setShowProfile(false) }}
            title={isAr ? 'بحث' : 'Search'}
            className="text-[#868686] hover:text-[#1d1c1d] transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </button>
          {/* Profile button */}
          <button
            onClick={() => { loadProfile(); setShowSearch(false) }}
            title={isAr ? 'الملف الشخصي' : 'Profile'}
            className="text-[#868686] hover:text-[#1d1c1d] transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
            </svg>
          </button>
          <div className="flex items-center gap-1.5">
            <span className={`inline-block w-2 h-2 rounded-full ${statusDot}`} />
            <span className="text-xs text-[#616061]">{statusLabel}</span>
          </div>
        </div>
      </header>

      {/* ── Search panel ── */}
      {showSearch && (
        <div className="px-5 py-2 border-b border-[#e0e0e0] bg-[#f8f8f8]">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              doSearch(e.target.value)
            }}
            placeholder={isAr ? 'بحث في المحادثة...' : 'Search in conversation…'}
            className="w-full text-sm px-3 py-1.5 rounded border border-[#d0d0d0] bg-white text-[#1d1c1d] focus:outline-none focus:border-[#1264a3]"
            autoFocus
          />
          {searchResults.length > 0 && (
            <div className="mt-2 max-h-[200px] overflow-y-auto space-y-1">
              {searchResults.map((r) => (
                <div key={r.id} className="text-xs text-[#1d1c1d] bg-white px-3 py-2 rounded border border-[#e0e0e0]">
                  <span className="text-[#616061]">
                    {new Date(r.createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </span>
                  {' — '}
                  {r.content.slice(0, 100)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Profile panel ── */}
      {showProfile && profile && (
        <div className="px-5 py-3 border-b border-[#e0e0e0] bg-[#f8f8f8]">
          <div className="flex items-center gap-3 mb-2">
            <span className="w-12 h-12 rounded-full bg-[#1264a3]/20 text-[#1264a3] text-lg font-bold flex items-center justify-center">
              {(isAr && profile.name_ar ? profile.name_ar : profile.name).charAt(0).toUpperCase()}
            </span>
            <div>
              <div className="text-sm font-bold text-[#1d1c1d]">{isAr && profile.name_ar ? profile.name_ar : profile.name}</div>
              <div className="text-xs text-[#616061]">{profile.job_title}</div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs text-[#616061]">
            <div>{isAr ? 'القسم' : 'Department'}: <span className="text-[#1d1c1d]">{(isAr ? profile.department_name_ar : profile.department_name) ?? '—'}</span></div>
            <div>{isAr ? 'البريد' : 'Email'}: <span className="text-[#1d1c1d]">{profile.email}</span></div>
            {profile.phone && <div>{isAr ? 'الهاتف' : 'Phone'}: <span className="text-[#1d1c1d]">{profile.phone}</span></div>}
            {profile.hire_date && <div>{isAr ? 'تاريخ التعيين' : 'Hired'}: <span className="text-[#1d1c1d]">{new Date(profile.hire_date).toLocaleDateString()}</span></div>}
          </div>
          <button onClick={() => setShowProfile(false)} className="mt-2 text-[10px] text-[#616061] hover:text-[#1d1c1d]">
            {isAr ? 'إغلاق' : 'Close'}
          </button>
        </div>
      )}

      {/* ── Pinned messages bar ── */}
      {pinnedIds.length > 0 && (
        <div className="px-5 py-1.5 border-b border-[#e0e0e0] bg-amber-50 text-xs">
          <span className="font-semibold text-amber-700">📌 {pinnedIds.length} {isAr ? 'رسائل مثبتة' : 'pinned'}</span>
        </div>
      )}

      {/* ── Messages ── */}
      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto bg-white">
        <div className="max-w-[900px] mx-auto py-4 space-y-1">
          {loading && (
            <div className="text-center text-xs text-[#616061] py-8">
              {isAr ? 'جاري التحميل...' : 'Loading messages…'}
            </div>
          )}
          {!loading && messages.length === 0 && (
            <div className="text-center text-xs text-[#616061] py-8">
              {isAr ? 'ابدأ المحادثة! جرب @Deema لاستدعاء وكيل ذكي' : 'Start the conversation! Try @Deema to invoke an AI agent'}
            </div>
          )}
          {messages.map((msg) => {
            const isMe = msg.senderId === myId
            const isAgent = msg.messageType === 'agent'
            const agentMeta = isAgent ? getAgentMeta(msg.agentName) : null
            const isPinned = pinnedIds.includes(msg.id)
            const replyPreview = getReplyPreview(msg.replyToId)

            // Determine avatar and name
            let avatarClass = isMe ? 'bg-[#1264a3]' : 'bg-[#616061]'
            let avatarText = isMe ? (user?.name?.charAt(0).toUpperCase() ?? 'Y') : peerInitial
            let displayName = isMe ? (isAr ? 'أنت' : 'You') : peerName

            if (isAgent && agentMeta) {
              avatarClass = agentMeta.colorClass
              avatarText = agentMeta.initial
              displayName = isAr ? agentMeta.nameAr : agentMeta.name
            }

            if (msg.isDeleted) {
              return (
                <div key={msg.id} className="slack-msg flex gap-3 px-5 opacity-50">
                  <div className={`w-9 h-9 rounded-lg ${avatarClass} flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5`}>
                    {avatarText}
                  </div>
                  <div className="text-[13px] text-[#616061] italic mt-2">
                    {isAr ? 'تم حذف هذه الرسالة' : 'This message was deleted'}
                  </div>
                </div>
              )
            }

            // Editing mode
            if (editingMsg?.id === msg.id) {
              return (
                <div key={msg.id} className="slack-msg flex gap-3 px-5 bg-amber-50">
                  <div className={`w-9 h-9 rounded-lg ${avatarClass} flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5`}>
                    {avatarText}
                  </div>
                  <div className="flex-1 min-w-0">
                    <input
                      type="text"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveEdit(msg.id)
                        if (e.key === 'Escape') { setEditingMsg(null); setEditText('') }
                      }}
                      className="w-full text-[13px] px-2 py-1 border border-[#1264a3] rounded bg-white focus:outline-none"
                      autoFocus
                    />
                    <div className="flex gap-2 mt-1">
                      <button onClick={() => saveEdit(msg.id)} className="text-[10px] text-[#007a5a] font-semibold">{isAr ? 'حفظ' : 'Save'}</button>
                      <button onClick={() => { setEditingMsg(null); setEditText('') }} className="text-[10px] text-[#616061]">{isAr ? 'إلغاء' : 'Cancel'}</button>
                    </div>
                  </div>
                </div>
              )
            }

            return (
              <div
                key={msg.id}
                className={`slack-msg group flex gap-3 px-5 relative ${msg.pending ? 'opacity-60' : ''} ${isMe && !isAgent ? 'bg-[#f8f8f8]' : ''} ${isAgent ? 'bg-[#f0f4ff]' : ''} ${isPinned ? 'border-s-2 border-s-amber-400' : ''}`}
                onContextMenu={(e) => {
                  e.preventDefault()
                  setContextMenu({ msgId: msg.id, x: e.clientX, y: e.clientY })
                }}
              >
                <div className={`w-9 h-9 rounded-lg ${avatarClass} flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5`}>
                  {avatarText}
                </div>
                <div className="min-w-0 flex-1">
                  {/* Reply preview */}
                  {replyPreview && (
                    <div className="text-[11px] text-[#616061] border-s-2 border-s-[#1264a3] ps-2 mb-0.5 truncate">
                      {replyPreview}
                    </div>
                  )}
                  <div className="flex items-baseline gap-2">
                    <span className="text-[15px] font-bold text-[#1d1c1d]">{displayName}</span>
                    {isAgent && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1264a3]/10 text-[#1264a3] font-semibold">AI</span>
                    )}
                    {msg.isEdited && <span className="text-[10px] text-[#868686]">({isAr ? 'معدّل' : 'edited'})</span>}
                    <span className="text-xs text-[#616061]">
                      {new Date(msg.createdAt).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
                    </span>
                    {isPinned && <span className="text-[10px]" title="Pinned">📌</span>}
                  </div>
                  <div dir="auto" className="text-[15px] text-[#1d1c1d] whitespace-pre-wrap break-words leading-[1.46668]">
                    {msg.content}
                  </div>

                  {/* Attachments */}
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-1">
                      {msg.attachments.map((att, i) => (
                        <a key={i} href={att.url} target="_blank" rel="noopener noreferrer"
                          className="text-[11px] px-2 py-1 bg-[#f0f0f0] rounded border border-[#d0d0d0] text-[#1264a3] hover:bg-[#e0e0e0] flex items-center gap-1">
                          {att.type === 'voice' ? '🎤' : att.type === 'image' ? '🖼' : '📎'}
                          {att.name || (att.type === 'voice' ? `${att.duration_sec}s` : 'file')}
                        </a>
                      ))}
                    </div>
                  )}

                  {/* Reactions display */}
                  {msg.reactions && Object.keys(msg.reactions).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {Object.entries(msg.reactions).map(([emoji, users]) => (
                        <button
                          key={emoji}
                          onClick={() => toggleReaction(msg.id, emoji)}
                          className={`text-[11px] px-1.5 py-0.5 rounded-full border transition-colors ${
                            users.includes(myId)
                              ? 'bg-[#1264a3]/10 border-[#1264a3]/30 text-[#1264a3]'
                              : 'bg-[#f0f0f0] border-[#d0d0d0] text-[#616061] hover:bg-[#e0e0e0]'
                          }`}
                        >
                          {emoji} {users.length}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Hover toolbar */}
                  {!msg.pending && (
                    <div className="absolute top-0 end-2 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5 bg-white border border-[#e0e0e0] rounded shadow-sm px-0.5 py-0.5 -translate-y-1/2">
                      {/* Reply */}
                      <button onClick={() => { setReplyTo(msg); inputRef.current?.focus() }}
                        title={isAr ? 'رد' : 'Reply'}
                        className="p-1 text-[#868686] hover:text-[#1d1c1d] transition-colors">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 17 4 12 9 7" /><path d="M20 18v-2a4 4 0 0 0-4-4H4" /></svg>
                      </button>
                      {/* Emoji */}
                      <button onClick={() => setShowEmojiFor(showEmojiFor === msg.id ? null : msg.id)}
                        title={isAr ? 'تفاعل' : 'React'}
                        className="p-1 text-[#868686] hover:text-[#1d1c1d] transition-colors">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="M8 14s1.5 2 4 2 4-2 4-2" /><line x1="9" y1="9" x2="9.01" y2="9" /><line x1="15" y1="9" x2="15.01" y2="9" /></svg>
                      </button>
                      {/* Pin */}
                      <button onClick={() => togglePin(msg.id)}
                        title={isPinned ? (isAr ? 'إلغاء التثبيت' : 'Unpin') : (isAr ? 'تثبيت' : 'Pin')}
                        className="p-1 text-[#868686] hover:text-[#1d1c1d] transition-colors">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="17" x2="12" y2="22" /><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z" /></svg>
                      </button>
                      {/* Edit (own messages only) */}
                      {isMe && !isAgent && (
                        <button onClick={() => { setEditingMsg(msg); setEditText(msg.content) }}
                          title={isAr ? 'تعديل' : 'Edit'}
                          className="p-1 text-[#868686] hover:text-[#1d1c1d] transition-colors">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                        </button>
                      )}
                      {/* Delete (own messages only) */}
                      {isMe && !isAgent && (
                        <button onClick={() => deleteMessage(msg.id)}
                          title={isAr ? 'حذف' : 'Delete'}
                          className="p-1 text-[#868686] hover:text-rose-500 transition-colors">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
                        </button>
                      )}
                      {/* Forward to agent */}
                      {!isAgent && (
                        <button onClick={() => setContextMenu({ msgId: msg.id, x: 0, y: 0 })}
                          title={isAr ? 'تحويل لوكيل' : 'Forward to agent'}
                          className="p-1 text-[#868686] hover:text-[#1d1c1d] transition-colors">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 17 20 12 15 7" /><path d="M4 18v-2a4 4 0 0 1 4-4h12" /></svg>
                        </button>
                      )}
                    </div>
                  )}

                  {/* Emoji picker popover */}
                  {showEmojiFor === msg.id && (
                    <div className="absolute top-0 end-2 -translate-y-full mb-1 bg-white border border-[#e0e0e0] rounded-lg shadow-lg p-1.5 flex gap-1 z-50">
                      {EMOJI_PALETTE.map((emoji) => (
                        <button
                          key={emoji}
                          onClick={() => toggleReaction(msg.id, emoji)}
                          className="text-lg hover:scale-125 transition-transform p-0.5"
                        >
                          {emoji}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          })}

          {/* Typing indicator */}
          {isTyping && (
            <div className="slack-msg flex gap-3 px-5">
              <div className="w-9 h-9 rounded-lg bg-[#616061] flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5">
                {peerInitial}
              </div>
              <div className="flex items-center gap-1 mt-2">
                <span className="text-xs text-[#616061] mr-1">
                  {isAr ? `${peerName} يكتب` : `${peerName} is typing`}
                </span>
                <span className="w-1.5 h-1.5 rounded-full bg-[#868686] animate-blink" />
                <span className="w-1.5 h-1.5 rounded-full bg-[#868686] animate-blink [animation-delay:0.2s]" />
                <span className="w-1.5 h-1.5 rounded-full bg-[#868686] animate-blink [animation-delay:0.4s]" />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Context menu (forward to agent) ── */}
      {contextMenu && (
        <div
          className="fixed bg-white border border-[#e0e0e0] rounded-lg shadow-lg py-1 z-50 min-w-[180px]"
          style={{ top: contextMenu.y || '50%', left: contextMenu.x || '50%' }}
        >
          <div className="px-3 py-1 text-[10px] font-semibold text-[#616061] uppercase">
            {isAr ? 'تحويل إلى وكيل' : 'Forward to agent'}
          </div>
          {visibleAgents.map((a) => (
            <button
              key={a.id}
              onClick={() => {
                const msg = messages.find((m) => m.id === contextMenu.msgId)
                if (msg) forwardToAgent(msg, a.id)
              }}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-[#f0f0f0] transition-colors text-start"
            >
              <span className={`w-5 h-5 rounded-full ${a.colorClass} text-white text-[9px] font-bold flex items-center justify-center`}>
                {a.initial}
              </span>
              <span>{isAr ? a.nameAr : a.name}</span>
            </button>
          ))}
          <button
            onClick={() => setContextMenu(null)}
            className="w-full px-3 py-1.5 text-[11px] text-[#616061] hover:bg-[#f0f0f0] text-start"
          >
            {isAr ? 'إلغاء' : 'Cancel'}
          </button>
        </div>
      )}

      {/* Close context menu on outside click */}
      {contextMenu && (
        <div className="fixed inset-0 z-40" onClick={() => setContextMenu(null)} />
      )}

      {/* ── Error bar ── */}
      {error && (
        <div className="px-6 py-2 text-xs text-rose-500 bg-rose-500/10 border-t border-rose-500/20">
          {error}
        </div>
      )}

      {/* ── Reply preview ── */}
      {replyTo && (
        <div className="px-5 py-1.5 border-t border-[#e0e0e0] bg-[#f8f8f8] flex items-center gap-2">
          <div className="border-s-2 border-s-[#1264a3] ps-2 text-xs text-[#616061] flex-1 truncate">
            {isAr ? 'رد على' : 'Replying to'}: {replyTo.content.slice(0, 60)}
          </div>
          <button onClick={() => setReplyTo(null)} className="text-[#868686] hover:text-[#1d1c1d] text-xs">✕</button>
        </div>
      )}

      {/* ── Input ── */}
      <form onSubmit={handleSubmit} className="px-5 pb-4 pt-1">
        <div className="max-w-[900px] mx-auto relative">
          {/* @mention autocomplete */}
          {filteredAgents.length > 0 && (
            <div className="absolute bottom-full mb-1 start-0 bg-white border border-[#e0e0e0] rounded-lg shadow-lg py-1 z-50 min-w-[200px]">
              <div className="px-3 py-1 text-[10px] font-semibold text-[#616061] uppercase">
                {isAr ? 'استدعاء وكيل' : 'Mention an agent'}
              </div>
              {filteredAgents.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => insertMention(a.id)}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-[#f0f0f0] transition-colors text-start"
                >
                  <span className={`w-5 h-5 rounded-full ${a.colorClass} text-white text-[9px] font-bold flex items-center justify-center`}>
                    {a.initial}
                  </span>
                  <span className="font-medium">{isAr ? a.nameAr : a.name}</span>
                  <span className="text-[11px] text-[#616061]">{a.role}</span>
                </button>
              ))}
            </div>
          )}

          <div className="flex items-center gap-2 bg-white border border-[#c4c4c4] rounded-lg px-3 py-2 focus-within:border-[#868686] focus-within:shadow-[0_0_0_1px_#868686] transition-all">
            {/* Attach file button */}
            <label
              title={isAr ? 'إرفاق ملف' : 'Attach file'}
              className="text-[#868686] hover:text-[#1d1c1d] transition-colors cursor-pointer shrink-0"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
              <input
                type="file"
                className="hidden"
                accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt"
                onChange={async (e) => {
                  const file = e.target.files?.[0]
                  if (!file) return
                  e.target.value = ''
                  try {
                    const att = await uploadDmFile(file)
                    if (selectedPeerId) {
                      const text = `📎 ${att.name}`
                      if (status === 'open') {
                        send('dm.send', { peer_id: selectedPeerId, text, attachments: [att] })
                      } else {
                        await apiFetch(`/dm/conversations/${selectedPeerId}/send`, {
                          method: 'POST',
                          body: JSON.stringify({ text, attachments: [att] }),
                        })
                      }
                    }
                  } catch (err) {
                    console.error('[DM] file upload error:', err)
                    setError(isAr ? 'فشل رفع الملف' : 'Upload failed')
                    setTimeout(() => setError(null), 3000)
                  }
                }}
              />
            </label>
            {/* Voice note button */}
            <button
              type="button"
              title={isAr ? 'رسالة صوتية' : 'Voice note'}
              className="text-[#868686] hover:text-[#1d1c1d] transition-colors shrink-0"
              onClick={async () => {
                try {
                  if (!navigator.mediaDevices?.getUserMedia) {
                    setError(isAr ? 'المتصفح لا يدعم التسجيل الصوتي' : 'Browser does not support audio recording')
                    setTimeout(() => setError(null), 4000)
                    return
                  }
                  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
                  const recorder = new MediaRecorder(stream)
                  const chunks: BlobPart[] = []
                  recorder.ondataavailable = (e) => chunks.push(e.data)
                  recorder.onstop = async () => {
                    stream.getTracks().forEach((t) => t.stop())
                    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
                    try {
                      const att = await uploadDmFile(blob, 'voice-note.webm')
                      att.duration_sec = Math.round((Date.now() - recordStart) / 1000)
                      if (selectedPeerId) {
                        const text = `🎤 ${isAr ? 'رسالة صوتية' : 'Voice note'} (${att.duration_sec}s)`
                        if (status === 'open') {
                          send('dm.send', { peer_id: selectedPeerId, text, attachments: [att] })
                        } else {
                          await apiFetch(`/dm/conversations/${selectedPeerId}/send`, {
                            method: 'POST',
                            body: JSON.stringify({ text, attachments: [att] }),
                          })
                        }
                      }
                    } catch {
                      setError(isAr ? 'فشل رفع التسجيل' : 'Voice upload failed')
                      setTimeout(() => setError(null), 3000)
                    }
                  }
                  const recordStart = Date.now()
                  recorder.start()
                  const stopBtn = document.createElement('div')
                  stopBtn.className = 'fixed inset-0 z-[100] bg-black/20 flex items-center justify-center cursor-pointer'
                  stopBtn.innerHTML = `<div class="bg-white rounded-xl px-6 py-4 text-center shadow-2xl">
                    <div class="w-4 h-4 rounded-full bg-rose-500 animate-pulse mx-auto mb-2"></div>
                    <div class="text-sm font-medium">${isAr ? 'جاري التسجيل... اضغط للإيقاف' : 'Recording… Click to stop'}</div>
                  </div>`
                  stopBtn.onclick = () => {
                    recorder.stop()
                    stopBtn.remove()
                  }
                  document.body.appendChild(stopBtn)
                  setTimeout(() => {
                    if (recorder.state === 'recording') {
                      recorder.stop()
                      stopBtn.remove()
                    }
                  }, 60_000)
                } catch (err) {
                  console.error('[DM] mic error:', err)
                  const msg = err instanceof DOMException && err.name === 'NotFoundError'
                    ? (isAr ? 'لا يوجد ميكروفون' : 'No microphone found')
                    : (isAr ? 'لا يمكن الوصول للميكروفون — افتح إعدادات المتصفح واسمح بالوصول' : 'Microphone blocked — allow access in browser settings')
                  setError(msg)
                  setTimeout(() => setError(null), 5000)
                }
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            </button>
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => handleInputChange(e.target.value)}
              placeholder={isAr ? `اكتب رسالة لـ ${peerName} أو @اسم_الوكيل` : `Message ${peerName} or @agent`}
              disabled={sending}
              className="flex-1 bg-transparent text-[13px] text-[#1d1c1d] placeholder:text-[#868686] focus:outline-none disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              className="w-7 h-7 rounded-md bg-[#007a5a] text-white flex items-center justify-center hover:bg-[#148567] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <svg width="13" height="13" viewBox="0 0 20 20" fill="currentColor">
                <path d="M1.5 2.25a.755.755 0 0 1 1-.71l15.596 7.808a.73.73 0 0 1 0 1.304L2.5 18.46a.755.755 0 0 1-1-.71v-5.5L12 10 1.5 7.75v-5.5z" />
              </svg>
            </button>
          </div>
        </div>
      </form>
    </section>
  )
}
