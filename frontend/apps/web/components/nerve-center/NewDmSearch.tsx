'use client'

import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { setSelectedPeer, setConversations } from '@/lib/people-store'
import { useCurrentAgent } from '@/lib/agent-store'

interface Colleague {
  id: string
  name: string
  name_ar: string | null
  job_title: string
  department_name: string | null
  department_name_ar: string | null
  is_bot?: boolean
}

export default function NewDmSearch({ onClose }: { onClose: () => void }) {
  const { locale } = useCurrentAgent()
  const isAr = locale === 'ar'
  const [query, setQuery] = useState('')
  const [allColleagues, setAllColleagues] = useState<Colleague[]>([])
  const [results, setResults] = useState<Colleague[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [onClose])

  // Load all colleagues once on mount
  useEffect(() => {
    let cancelled = false
    apiFetch<Colleague[]>('/dm/colleagues')
      .then((data) => {
        if (cancelled) return
        if (Array.isArray(data)) {
          setAllColleagues(data)
          setResults(data)
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const status = (err as { status?: number })?.status
        if (status === 401) {
          setError(isAr ? 'انتهت الجلسة — أعد تسجيل الدخول' : 'Session expired — please re-login')
        } else {
          setError(isAr ? 'فشل تحميل الزملاء' : 'Failed to load colleagues')
        }
        console.error('[NewDmSearch] load failed:', err)
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  // Filter locally when query changes (no extra API calls needed)
  useEffect(() => {
    const q = query.trim().toLowerCase()
    if (!q) {
      setResults(allColleagues)
      return
    }
    setResults(allColleagues.filter((c) =>
      c.name.toLowerCase().includes(q) ||
      (c.name_ar && c.name_ar.toLowerCase().includes(q)) ||
      c.job_title.toLowerCase().includes(q) ||
      (c.department_name && c.department_name.toLowerCase().includes(q))
    ))
  }, [query, allColleagues])

  return (
    <div
      ref={panelRef}
      className="absolute inset-x-0 top-0 bottom-0 z-50 bg-surface-2 flex flex-col"
    >
      <div className="p-3 border-b border-border">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-ink">
            {isAr ? 'رسالة جديدة' : 'New Message'}
          </span>
          <button
            onClick={onClose}
            className="text-ink-dim hover:text-ink text-xs p-1"
          >
            ✕
          </button>
        </div>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={isAr ? 'ابحث عن زميل...' : 'Search colleagues…'}
          className="w-full text-sm px-3 py-1.5 rounded-md border border-border bg-white text-ink placeholder:text-ink-dim focus:outline-none focus:border-[#1264a3]"
        />
      </div>
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="text-center text-xs text-ink-dim py-4">
            {isAr ? 'جاري البحث...' : 'Searching…'}
          </div>
        )}
        {results.map((c) => {
          const displayName = isAr && c.name_ar ? c.name_ar : c.name
          const dept = isAr && c.department_name_ar ? c.department_name_ar : c.department_name
          return (
            <button
              key={c.id}
              onClick={() => {
                setSelectedPeer(c.id, {
                  id: c.id,
                  name: c.name,
                  nameAr: c.name_ar,
                  jobTitle: c.job_title,
                })
                // Refresh conversations so the new peer appears in the list
                apiFetch<Array<{
                  id: string; peer_id: string; peer_name: string; peer_name_ar: string | null
                  peer_job_title: string; last_message: string | null
                  last_message_at: string | null; unread_count: number
                }>>('/dm/conversations')
                  .then((data) => {
                    if (Array.isArray(data)) {
                      setConversations(data.map((conv) => ({
                        id: conv.id,
                        peerId: conv.peer_id,
                        peerName: conv.peer_name,
                        peerNameAr: conv.peer_name_ar,
                        peerJobTitle: conv.peer_job_title,
                        lastMessage: conv.last_message,
                        lastMessageAt: conv.last_message_at,
                        unreadCount: conv.unread_count,
                      })))
                    }
                  })
                  .catch(() => {})
                onClose()
              }}
              className="w-full flex items-center gap-2 px-4 py-2.5 text-sm hover:bg-surface-3 transition-colors text-start"
            >
              <span className={`w-7 h-7 rounded-full text-[10px] font-semibold flex items-center justify-center shrink-0 ${c.is_bot ? 'bg-emerald-100 text-emerald-700' : 'bg-[#1264a3]/20 text-[#1264a3]'}`}>
                {c.is_bot ? 'AI' : displayName.charAt(0).toUpperCase()}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-ink truncate">
                  {displayName}
                  {c.is_bot && <span className="ml-1.5 text-[9px] font-medium text-emerald-600 bg-emerald-50 px-1 py-0.5 rounded">BOT</span>}
                </div>
                <div className="text-[11px] text-ink-dim truncate">
                  {c.job_title}{dept ? ` · ${dept}` : ''}
                </div>
              </div>
            </button>
          )
        })}
        {error && (
          <div className="text-center text-xs text-rose-500 py-4">{error}</div>
        )}
        {!loading && !error && results.length === 0 && (
          <div className="text-center text-xs text-ink-dim py-4">
            {query.trim()
              ? (isAr ? 'لا توجد نتائج' : 'No results')
              : (isAr ? 'لا يوجد زملاء' : 'No colleagues found')}
          </div>
        )}
      </div>
    </div>
  )
}
