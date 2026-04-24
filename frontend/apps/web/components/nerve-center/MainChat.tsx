'use client'

import { useEffect, useRef, useState, type FormEvent } from 'react'

import { useWebSocket, type WsEnvelope } from '@/hooks/useWebSocket'
import { AGENTS, getAgent, DEFAULT_AGENT_ID } from '@/lib/agents'
import {
  incrementUnread,
  resetUnread,
  setCurrentAgentId,
  useCurrentAgent,
} from '@/lib/agent-store'
import { apiFetch } from '@/lib/api'
import ToolCard, { type ToolStatus } from './ToolCard'
import FormCard, { getFormAction, buildFormMessage, FORM_SCHEMAS } from './FormCard'

/**
 * Parse trailing numbered suggestions from a message.
 * Returns the message body (without suggestions) and the list of suggestion strings.
 * Matches patterns like "1. Check my leave balance\n2. Submit request"
 */
function parseSuggestions(text: string): { body: string; suggestions: string[] } {
  // Match a trailing block of numbered items (1. ... \n 2. ... etc.)
  const lines = text.split('\n')
  const suggestions: string[] = []
  let cutIndex = lines.length

  // Walk backwards from end, collecting numbered lines
  for (let i = lines.length - 1; i >= 0; i--) {
    const trimmed = lines[i].trim()
    if (!trimmed) {
      // Allow blank lines between suggestions
      continue
    }
    const match = trimmed.match(/^\d+[\.\)]\s+(.+)$/)
    if (match) {
      suggestions.unshift(match[1].trim())
      cutIndex = i
    } else {
      break
    }
  }

  if (suggestions.length === 0) {
    return { body: text, suggestions: [] }
  }

  const body = lines.slice(0, cutIndex).join('\n').trimEnd()
  return { body, suggestions }
}

interface ToolMessage {
  id: string
  kind: 'tool'
  toolId: string
  toolName: string
  displayNameEn: string
  displayNameAr: string
  status: ToolStatus
  resultSummary?: string
  resultData?: Record<string, unknown> | null
  durationMs?: number | null
  agent: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  agent?: string
  createdAt: string
  pending?: boolean
  routedFrom?: string // when assistant reply came from a different agent than requested
}

interface FormMessage {
  id: string
  kind: 'form'
  formAction: string
  prefilled?: Record<string, string>
  agent: string
}

type LaneMessage = ChatMessage | ToolMessage | FormMessage

function isToolMessage(msg: LaneMessage): msg is ToolMessage {
  return 'kind' in msg && msg.kind === 'tool'
}

function isFormMessage(msg: LaneMessage): msg is FormMessage {
  return 'kind' in msg && msg.kind === 'form'
}

function isChatMessage(msg: LaneMessage): msg is ChatMessage {
  return !('kind' in msg)
}

interface AssistantMessagePayload {
  conversation_id: string
  message_id: string
  role: 'user' | 'assistant'
  agent?: string
  text: string
  created_at: string
}

interface ChatCompletePayload {
  conversation_id: string
  message_id: string
  agent?: string
}

interface ErrorPayload {
  code: string
  message: string
  detail?: string
}

const STATUS_LABEL: Record<string, string> = {
  idle: 'Connecting…',
  connecting: 'Connecting…',
  open: 'Online',
  closed: 'Disconnected',
  error: 'Connection error',
  auth_required: 'Session expired',
}

function buildInitialMessages(): Record<string, LaneMessage[]> {
  const map: Record<string, LaneMessage[]> = {}
  for (const a of AGENTS) {
    map[a.id] = [
      {
        id: `welcome-${a.id}`,
        role: 'assistant',
        text: a.greeting,
        agent: a.id,
        createdAt: new Date().toISOString(),
      },
    ]
  }
  return map
}

export default function MainChat() {
  const { status, send, on } = useWebSocket()
  const { agentId, agent, locale, toggleLocale } = useCurrentAgent()

  // Per-agent conversation state
  const [messagesByAgent, setMessagesByAgent] = useState<
    Record<string, LaneMessage[]>
  >(() => buildInitialMessages())
  const [conversationIdByAgent, setConversationIdByAgent] = useState<
    Record<string, string | null>
  >(() =>
    AGENTS.reduce((acc, a) => {
      acc[a.id] = null
      return acc
    }, {} as Record<string, string | null>),
  )

  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Recent conversations for the history dropdown
  const [recentConversations, setRecentConversations] = useState<
    Array<{ id: string; agent_name: string; topic: string; started_at: string; status: string }>
  >([])
  const [showHistory, setShowHistory] = useState(false)

  // ref -> the agent the user sent the message to (used to reconcile the
  // optimistic user bubble back to the correct agent lane)
  const pendingByRef = useRef<Map<string, string>>(new Map())
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const historyRef = useRef<HTMLDivElement | null>(null)

  const messages = messagesByAgent[agentId] ?? []

  // Fetch recent conversations on mount
  useEffect(() => {
    apiFetch<Array<{ id: string; agent_name: string; topic: string; started_at: string; status: string }>>('/chat/conversations')
      .then((data) => {
        if (Array.isArray(data)) setRecentConversations(data.slice(0, 15))
      })
      .catch(() => {})
  }, [])

  // Close history dropdown on outside click
  useEffect(() => {
    if (!showHistory) return
    function handleClick(e: MouseEvent) {
      if (historyRef.current && !historyRef.current.contains(e.target as Node)) {
        setShowHistory(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showHistory])

  // Auto-scroll when the visible thread changes
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, agentId])

  // Reset unread for the agent we just switched to
  useEffect(() => {
    resetUnread(agentId)
  }, [agentId])

  // When locale toggles, reset the current agent's conversation to start fresh in the new language
  const prevLocaleRef = useRef(locale)
  useEffect(() => {
    if (prevLocaleRef.current !== locale) {
      prevLocaleRef.current = locale
      // Reset current agent conversation with a fresh greeting in the new language
      const currentAgent = getAgent(agentId)
      if (!currentAgent) return
      const greeting = locale === 'ar' ? currentAgent.greetingAr : currentAgent.greeting
      setMessagesByAgent((prev) => ({
        ...prev,
        [agentId]: [
          {
            id: `welcome-${agentId}-${Date.now()}`,
            role: 'assistant',
            text: greeting,
            agent: agentId,
            createdAt: new Date().toISOString(),
          },
        ],
      }))
      // Clear the conversation ID so a new one starts
      setConversationIdByAgent((prev) => ({ ...prev, [agentId]: null }))
    }
  }, [locale, agentId])

  // Wire WS subscriptions — NOTE: we intentionally don't depend on agentId
  // here, because the handler must route replies by payload.agent, not the
  // currently-selected agent.
  useEffect(() => {
    const offMessage = on('chat.message.created', (env: WsEnvelope) => {
      const payload = env.payload as AssistantMessagePayload
      if (!payload || !payload.role) return

      if (payload.role === 'assistant') {
        // Figure out which lane this message belongs to.
        // For deployed agents (dept:uuid), use the lane the user sent from
        const refLane = env.ref ? pendingByRef.current.get(env.ref) ?? null : null
        const repliedAgent =
          (payload.agent && getAgent(payload.agent) ? payload.agent : null) ??
          refLane ??
          DEFAULT_AGENT_ID

        // Determine which agent the user had asked (for routed-to hint)
        const requestedAgent = env.ref
          ? pendingByRef.current.get(env.ref) ?? null
          : null
        const routedFrom =
          requestedAgent && requestedAgent !== repliedAgent
            ? requestedAgent
            : undefined

        // Persist conversation id under the replied agent lane
        if (payload.conversation_id) {
          setConversationIdByAgent((prev) =>
            prev[repliedAgent] ? prev : { ...prev, [repliedAgent]: payload.conversation_id },
          )
        }

        setMessagesByAgent((prev) => {
          const lane = prev[repliedAgent] ?? []
          return {
            ...prev,
            [repliedAgent]: [
              ...lane,
              {
                id: payload.message_id,
                role: 'assistant',
                text: payload.text,
                agent: repliedAgent,
                createdAt: payload.created_at,
                routedFrom,
              },
            ],
          }
        })

        // Bump unread if the user isn't currently looking at this agent
        incrementUnread(repliedAgent)
      } else if (payload.role === 'user') {
        // Reconcile optimistic user message — find the lane by ref.
        const lane = env.ref ? pendingByRef.current.get(env.ref) : null
        if (!lane) return
        setMessagesByAgent((prev) => {
          const laneMsgs = prev[lane] ?? []
          const idx = laneMsgs.findIndex((m) => isChatMessage(m) && m.pending && m.role === 'user')
          if (idx === -1) return prev
          const copy = laneMsgs.slice()
          copy[idx] = {
            id: payload.message_id,
            role: 'user',
            text: payload.text,
            createdAt: payload.created_at,
          }
          return { ...prev, [lane]: copy }
        })
        if (payload.conversation_id) {
          setConversationIdByAgent((prev) =>
            prev[lane] ? prev : { ...prev, [lane]: payload.conversation_id },
          )
        }
      }
    })

    const offComplete = on('chat.complete', (env: WsEnvelope) => {
      const payload = env.payload as ChatCompletePayload
      const lane = env.ref ? pendingByRef.current.get(env.ref) : null
      if (lane && payload?.conversation_id) {
        setConversationIdByAgent((prev) =>
          prev[lane] ? prev : { ...prev, [lane]: payload.conversation_id },
        )
      }
      if (env.ref) pendingByRef.current.delete(env.ref)
      clearSendingTimeout()
      setSending(false)
    })

    const offError = on('error', (env: WsEnvelope) => {
      const payload = env.payload as ErrorPayload
      if (env.ref && pendingByRef.current.has(env.ref)) {
        const lane = pendingByRef.current.get(env.ref)!
        pendingByRef.current.delete(env.ref)
        clearSendingTimeout()
        setSending(false)
        // Roll back the optimistic user message in that lane
        setMessagesByAgent((prev) => ({
          ...prev,
          [lane]: (prev[lane] ?? []).filter((m) => !isChatMessage(m) || !m.pending),
        }))
      }
      setError(payload?.message || 'Something went wrong')
      setTimeout(() => setError(null), 4000)
    })

    const offToolStart = on('chat.tool.start', (env: WsEnvelope) => {
      const p = env.payload as {
        tool_id: string
        tool_name: string
        display_name_en: string
        display_name_ar: string
        agent: string
      }
      if (!p || !p.tool_name) return
      const lane = env.ref ? pendingByRef.current.get(env.ref) ?? p.agent : p.agent
      const targetLane = getAgent(lane) ? lane : DEFAULT_AGENT_ID
      setMessagesByAgent((prev) => {
        const laneMsgs = prev[targetLane] ?? []
        // Skip if a completed card already exists (tool.result arrived first)
        if (laneMsgs.some((m) => isToolMessage(m) && m.toolId === p.tool_id)) {
          return prev
        }
        return {
          ...prev,
          [targetLane]: [
            ...laneMsgs,
            {
              id: `tool-${p.tool_id}-${Date.now()}`,
              kind: 'tool' as const,
              toolId: p.tool_id,
              toolName: p.tool_name,
              displayNameEn: p.display_name_en,
              displayNameAr: p.display_name_ar,
              status: 'running' as const,
              agent: p.agent,
            },
          ],
        }
      })
    })

    const offToolResult = on('chat.tool.result', (env: WsEnvelope) => {
      const p = env.payload as {
        tool_id: string
        tool_name: string
        display_name_en: string
        display_name_ar: string
        agent: string
        success: boolean
        result_summary: string
        result_data?: Record<string, unknown> | null
        duration_ms?: number | null
      }
      if (!p || !p.tool_name) return
      const lane = env.ref ? pendingByRef.current.get(env.ref) ?? p.agent : p.agent
      const targetLane = getAgent(lane) ? lane : DEFAULT_AGENT_ID

      // If the tool result requires confirmation, render as a FormCard instead
      const rd = p.result_data
      if (p.success && rd && rd.confirmation_required && rd.form_type) {
        const formAction = rd.form_type === 'leave_request' ? 'submit_leave_request' : String(rd.form_type)
        const prefilled: Record<string, string> = {}
        if (rd.leave_type) prefilled.leave_type = String(rd.leave_type)
        if (rd.start_date) prefilled.start_date = String(rd.start_date)
        if (rd.end_date) prefilled.end_date = String(rd.end_date)
        if (rd.reason) prefilled.reason = String(rd.reason)
        const formMsg: FormMessage = {
          id: `form-${p.tool_id}-${Date.now()}`,
          kind: 'form',
          formAction,
          prefilled,
          agent: p.agent,
        }
        setMessagesByAgent((prev) => {
          const laneMsgs = prev[targetLane] ?? []
          // Remove the running tool card if present
          const filtered = laneMsgs.filter(
            (m) => !(isToolMessage(m) && m.toolId === p.tool_id && m.status === 'running'),
          )
          return { ...prev, [targetLane]: [...filtered, formMsg] }
        })
        return
      }

      setMessagesByAgent((prev) => {
        const laneMsgs = prev[targetLane] ?? []
        // Find the matching running tool card and update it
        const idx = laneMsgs.findIndex(
          (m) => isToolMessage(m) && m.toolId === p.tool_id && m.status === 'running',
        )
        const resultCard: ToolMessage = {
          id: idx !== -1 ? laneMsgs[idx].id : `tool-${p.tool_id}-${Date.now()}`,
          kind: 'tool',
          toolId: p.tool_id,
          toolName: p.tool_name,
          displayNameEn: p.display_name_en,
          displayNameAr: p.display_name_ar,
          status: p.success ? 'success' : 'error',
          resultSummary: p.result_summary,
          resultData: p.result_data ?? null,
          durationMs: p.duration_ms ?? null,
          agent: p.agent,
        }
        if (idx !== -1) {
          const copy = laneMsgs.slice()
          copy[idx] = resultCard
          return { ...prev, [targetLane]: copy }
        }
        // tool.start hasn't been processed yet (React batching) — insert
        // the completed card directly so data is never lost
        return { ...prev, [targetLane]: [...laneMsgs, resultCard] }
      })
    })

    return () => {
      offMessage()
      offComplete()
      offError()
      offToolStart()
      offToolResult()
    }
  }, [on])

  // Safety timeout: if sending stays true for 30s, force-reset it
  const sendingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function clearSendingTimeout() {
    if (sendingTimeoutRef.current) {
      clearTimeout(sendingTimeoutRef.current)
      sendingTimeoutRef.current = null
    }
  }

  function sendText(text: string) {
    if (!text) return
    if (sending) return
    if (status !== 'open') {
      setError('Not connected — please wait a moment and try again')
      return
    }

    const targetAgentId = agentId
    const optimisticId = `pending-${Date.now()}`
    setMessagesByAgent((prev) => ({
      ...prev,
      [targetAgentId]: [
        ...(prev[targetAgentId] ?? []),
        {
          id: optimisticId,
          role: 'user',
          text,
          createdAt: new Date().toISOString(),
          pending: true,
        },
      ],
    }))
    setInput('')
    setSending(true)
    setError(null)
    // Safety: force-reset sending after 30s in case chat.complete never arrives
    clearSendingTimeout()
    sendingTimeoutRef.current = setTimeout(() => {
      setSending(false)
    }, 30_000)

    const envId = send('chat.send', {
      agent: targetAgentId,
      text,
      conversation_id: conversationIdByAgent[targetAgentId] ?? null,
      locale,
    })
    pendingByRef.current.set(envId, targetAgentId)
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    sendText(input.trim())
  }

  // Listen for tool-panel prompt events
  useEffect(() => {
    function onPrompt(e: Event) {
      const text = (e as CustomEvent<string>).detail
      if (!text) return
      // Check if this prompt should open a form card instead
      const formAction = getFormAction(text)
      if (formAction && FORM_SCHEMAS[formAction]) {
        const formMsg: FormMessage = {
          id: `form-${Date.now()}`,
          kind: 'form',
          formAction,
          agent: agentId,
        }
        setMessagesByAgent((prev) => ({
          ...prev,
          [agentId]: [...(prev[agentId] ?? []), formMsg],
        }))
        return
      }
      sendText(text)
    }
    window.addEventListener('krew:send-prompt', onPrompt)
    return () => window.removeEventListener('krew:send-prompt', onPrompt)
  })

  const statusLabel = STATUS_LABEL[status] ?? status
  const statusDot =
    status === 'open'
      ? 'bg-emerald-500'
      : status === 'connecting' || status === 'idle'
      ? 'bg-amber-500'
      : 'bg-rose-500' // closed, error, auth_required

  return (
    <section dir={locale === 'ar' ? 'rtl' : 'ltr'} className="chat-light flex-1 min-w-0 min-h-0 bg-white flex flex-col">
      <header className="h-12 px-5 border-b border-[#e0e0e0] flex items-center justify-between bg-white">
        <div className="flex items-center gap-2">
          <span className="text-[15px] font-bold text-[#1d1c1d]">
            # {locale === 'ar' ? agent.nameAr : agent.name}
          </span>
          <span className="text-xs text-[#616061]">
            {locale === 'ar' ? agent.roleAr : agent.role}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Language toggle */}
          <button
            type="button"
            onClick={toggleLocale}
            className="flex items-center h-7 rounded-full border border-[#d0d0d0] bg-[#f8f8f8] hover:bg-[#eee] transition-colors cursor-pointer overflow-hidden"
          >
            <span
              className={`px-2.5 py-0.5 text-[11px] font-semibold transition-colors rounded-full ${
                locale === 'en' ? 'bg-[#1264a3] text-white' : 'text-[#616061]'
              }`}
            >
              EN
            </span>
            <span
              className={`px-2.5 py-0.5 text-[11px] font-semibold transition-colors rounded-full ${
                locale === 'ar' ? 'bg-[#1264a3] text-white' : 'text-[#616061]'
              }`}
            >
              عربي
            </span>
          </button>
          <div className="flex items-center gap-1.5">
            <span className={`inline-block w-2 h-2 rounded-full ${statusDot}`} />
            <span className="text-xs text-[#616061]">{statusLabel}</span>
          </div>
        </div>
      </header>

      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto bg-white">
        <div className="max-w-[900px] mx-auto py-4 space-y-1">
          {messages.map((msg) => {
            if (isToolMessage(msg)) {
              const toolAgent = getAgent(msg.agent) ?? agent
              return (
                <div key={msg.id} className="slack-msg flex gap-3 px-5">
                  <div
                    className={`w-9 h-9 rounded-lg ${toolAgent.colorClass} flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5`}
                  >
                    {toolAgent.initial}
                  </div>
                  <div className="min-w-0 flex-1">
                    <ToolCard
                      toolName={msg.toolName}
                      displayNameEn={msg.displayNameEn}
                      displayNameAr={msg.displayNameAr}
                      status={msg.status}
                      resultSummary={msg.resultSummary}
                      resultData={msg.resultData}
                      durationMs={msg.durationMs}
                      agent={msg.agent}
                      locale={locale}
                      onAction={sendText}
                    />
                  </div>
                </div>
              )
            }
            if (isFormMessage(msg)) {
              const schema = FORM_SCHEMAS[msg.formAction]
              if (!schema) return null
              return (
                <FormCard
                  key={msg.id}
                  schema={schema}
                  prefilled={msg.prefilled}
                  agent={msg.agent}
                  onConfirm={(data) => {
                    const text = buildFormMessage(msg.formAction, data)
                    sendText(text)
                  }}
                  onReset={() => {
                    // Remove the form card from the lane
                    setMessagesByAgent((prev) => ({
                      ...prev,
                      [agentId]: (prev[agentId] ?? []).filter((m) => m.id !== msg.id),
                    }))
                  }}
                />
              )
            }
            const isUser = msg.role === 'user'
            const msgAgent = getAgent(msg.agent ?? agentId) ?? agent
            const isWelcome = msg.id.startsWith('welcome-')
            return (
              <div
                key={msg.id}
                className={`slack-msg group flex gap-3 px-5 ${msg.pending ? 'opacity-60' : ''} ${isUser ? 'bg-[#f8f8f8]' : ''}`}
              >
                {/* Avatar */}
                <div
                  className={`w-9 h-9 rounded-lg ${isUser ? 'bg-[#1264a3]' : msgAgent.colorClass} flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5`}
                >
                  {isUser ? 'You' : msgAgent.initial}
                </div>
                {/* Content */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <span className="text-[15px] font-bold text-[#1d1c1d]">
                      {isUser ? (locale === 'ar' ? 'أنت' : 'You') : (locale === 'ar' ? msgAgent.nameAr : msgAgent.name)}
                    </span>
                    {msg.routedFrom && (
                      <span className="text-xs text-[#616061]">
                        via {getAgent(msg.routedFrom)?.name ?? msg.routedFrom}
                      </span>
                    )}
                    <span className="text-xs text-[#616061]">
                      {new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
                    </span>
                    {!isUser && !isWelcome && (
                      <button
                        type="button"
                        title="Retry this response"
                        onClick={() => {
                          // Find the last user message before this agent response,
                          // remove everything from that user msg onward, then re-send
                          const allMsgs = messagesByAgent[agentId] ?? []
                          const idx = allMsgs.findIndex((m) => m.id === msg.id)
                          if (idx <= 0) return
                          let userMsgIdx = -1
                          let userText = ''
                          for (let j = idx - 1; j >= 0; j--) {
                            const prev = allMsgs[j]
                            if ('role' in prev && prev.role === 'user' && 'text' in prev) {
                              userMsgIdx = j
                              userText = prev.text
                              break
                            }
                          }
                          if (userMsgIdx < 0 || !userText) return
                          // Trim messages: keep everything up to (not including) the user msg
                          setMessagesByAgent((prev) => ({
                            ...prev,
                            [agentId]: allMsgs.slice(0, userMsgIdx),
                          }))
                          sendText(userText)
                        }}
                        disabled={sending}
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-[#616061] hover:text-[#1d1c1d] disabled:opacity-30 cursor-pointer p-0.5"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="1 4 1 10 7 10" />
                          <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                        </svg>
                      </button>
                    )}
                  </div>
                  {(() => {
                    const displayText = isWelcome && locale === 'ar' ? (msgAgent.greetingAr ?? msg.text) : msg.text
                    const { body, suggestions } = parseSuggestions(displayText)
                    return (
                      <>
                        {body && (
                          <div dir="auto" className="text-[15px] text-[#1d1c1d] whitespace-pre-wrap break-words leading-[1.46668]">
                            {body}
                          </div>
                        )}
                        {!isUser && suggestions.length > 0 && (
                          <div className={`flex flex-wrap gap-1.5 ${body ? 'mt-2' : ''}`}>
                            {suggestions.map((s) => (
                              <button
                                key={s}
                                type="button"
                                onClick={() => {
                                  const formAction = getFormAction(s)
                                  if (formAction && FORM_SCHEMAS[formAction]) {
                                    const formMsg: FormMessage = {
                                      id: `form-${Date.now()}`,
                                      kind: 'form',
                                      formAction,
                                      agent: agentId,
                                    }
                                    setMessagesByAgent((prev) => ({
                                      ...prev,
                                      [agentId]: [...(prev[agentId] ?? []), formMsg],
                                    }))
                                  } else {
                                    sendText(s)
                                  }
                                }}
                                disabled={sending}
                                className="px-3 py-1.5 text-[11px] font-medium rounded-lg border border-[#d0d0d0] bg-white text-[#1264a3] hover:bg-[#f0f0f0] hover:border-[#bbb] transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                              >
                                {s}
                              </button>
                            ))}
                          </div>
                        )}
                      </>
                    )
                  })()}
                </div>
              </div>
            )
          })}
          {sending && (
            <div className="slack-msg flex gap-3 px-5">
              <div
                className={`w-9 h-9 rounded-lg ${agent.colorClass} flex items-center justify-center text-white text-xs font-bold shrink-0 mt-0.5`}
              >
                {agent.initial}
              </div>
              <div className="flex items-center gap-1 mt-2">
                <span className="text-xs text-[#616061] mr-1">{locale === 'ar' ? `${agent.nameAr} يكتب` : `${agent.name} is typing`}</span>
                <span className="w-1.5 h-1.5 rounded-full bg-[#868686] animate-blink" />
                <span className="w-1.5 h-1.5 rounded-full bg-[#868686] animate-blink [animation-delay:0.2s]" />
                <span className="w-1.5 h-1.5 rounded-full bg-[#868686] animate-blink [animation-delay:0.4s]" />
              </div>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="px-6 py-2 text-xs text-rose-500 bg-rose-500/10 border-t border-rose-500/20">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="px-5 pb-4 pt-1">
        <div className="max-w-[900px] mx-auto relative">
          {/* History dropdown */}
          {showHistory && recentConversations.length > 0 && (
            <div
              ref={historyRef}
              className="absolute bottom-full left-0 right-0 mb-2 bg-white border border-[#e0e0e0] rounded-lg shadow-lg max-h-[280px] overflow-y-auto z-50"
            >
              <div className="px-3 py-2 border-b border-[#e0e0e0]">
                <span className="text-[11px] font-semibold text-[#616061] uppercase tracking-wider">Recent Conversations</span>
              </div>
              {recentConversations.map((conv) => {
                const convAgent = getAgent(conv.agent_name)
                return (
                  <button
                    key={conv.id}
                    type="button"
                    onClick={() => {
                      setShowHistory(false)
                      if (convAgent) {
                        setCurrentAgentId(conv.agent_name)
                      }
                      setConversationIdByAgent((prev) => ({
                        ...prev,
                        [conv.agent_name]: conv.id,
                      }))
                    }}
                    className="w-full px-3 py-2.5 flex items-center gap-3 hover:bg-[#f8f8f8] transition-colors text-left"
                  >
                    {convAgent && (
                      <div className={`w-6 h-6 rounded ${convAgent.colorClass} flex items-center justify-center text-white text-[10px] font-bold shrink-0`}>
                        {convAgent.initial}
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-[#1d1c1d] truncate">{conv.topic || 'Untitled conversation'}</div>
                      <div className="text-[10px] text-[#616061] mt-0.5">
                        {convAgent?.name ?? conv.agent_name}
                        {conv.started_at && ` · ${new Date(conv.started_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`}
                      </div>
                    </div>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${conv.status === 'active' ? 'bg-[#007a5a]/10 text-[#007a5a]' : 'bg-[#e8e8e8] text-[#616061]'}`}>
                      {conv.status === 'active' ? 'Active' : 'Resolved'}
                    </span>
                  </button>
                )
              })}
            </div>
          )}

          <div className="flex items-center gap-2 bg-white border border-[#c4c4c4] rounded-lg px-3 py-2 focus-within:border-[#868686] focus-within:shadow-[0_0_0_1px_#868686] transition-all">
            {/* History button */}
            <button
              type="button"
              onClick={() => setShowHistory((v) => !v)}
              title="Recent conversations"
              className="text-[#868686] hover:text-[#1d1c1d] transition-colors shrink-0"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="8" cy="8" r="6.5" />
                <polyline points="8,4.5 8,8 10.5,9.5" />
              </svg>
            </button>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={locale === 'ar' ? `اكتب رسالة لـ ${agent.nameAr}` : `Message #${agent.name}`}
              disabled={sending}
              className="flex-1 bg-transparent text-[13px] text-[#1d1c1d] placeholder:text-[#868686] focus:outline-none disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={sending || !input.trim() || status !== 'open'}
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
