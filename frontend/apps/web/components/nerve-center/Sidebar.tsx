'use client'

import { useEffect, useState } from 'react'
import { useCurrentAgent, setAccessibleAgentIds, setUser } from '@/lib/agent-store'
import { usePeople, setSelectedPeer, clearSelectedPeer, setConversations } from '@/lib/people-store'
import { logout, getUserSession } from '@/lib/auth'
import { apiFetch } from '@/lib/api'
import NewDmSearch from './NewDmSearch'

const ROLE_LABELS: Record<string, { en: string; ar: string }> = {
  c_suite:         { en: 'Executive',         ar: 'تنفيذي' },
  hr_admin:        { en: 'HR Admin',          ar: 'مدير موارد بشرية' },
  hr_manager:      { en: 'HR Manager',        ar: 'مدير الموارد البشرية' },
  hr_specialist:   { en: 'HR Specialist',     ar: 'أخصائي موارد بشرية' },
  department_head: { en: 'Department Head',   ar: 'رئيس قسم' },
  hiring_manager:  { en: 'Hiring Manager',    ar: 'مدير التوظيف' },
  manager:         { en: 'Manager',           ar: 'مدير' },
  it_admin:        { en: 'IT Admin',          ar: 'مدير تقنية المعلومات' },
  employee:        { en: 'Employee',          ar: 'موظف' },
}

interface AgentAccessResponse {
  agents: Array<{ name: string }>
  employee_role: string
}

export default function Sidebar() {
  const { agentId, setAgentId, visibleAgents, unreadByAgent, locale, user } = useCurrentAgent()
  const { selectedPeerId, conversations, unreadByPeer, totalUnread } = usePeople()
  const isAr = locale === 'ar'
  const [peopleExpanded, setPeopleExpanded] = useState(true)
  const [teamsExpanded, setTeamsExpanded] = useState(true)
  const [expandedDepts, setExpandedDepts] = useState<Set<string>>(new Set())
  const [teams, setTeams] = useState<Array<{ department_id: string; name: string; name_ar: string | null; human_count: number; ai_agent_count: number; total_members: number; }>>([])
  const [teamMembers, setTeamMembers] = useState<Record<string, Array<{ id: string; type: string; name: string; name_ar: string | null; job_title: string; job_title_ar: string | null }>>>({})
  const [showNewDm, setShowNewDm] = useState(false)

  // Fetch accessible agents + role from backend on mount
  useEffect(() => {
    apiFetch<AgentAccessResponse>('/chat/agent-access/me')
      .then((data) => {
        if (data && Array.isArray(data.agents)) {
          setAccessibleAgentIds(data.agents.map((a) => a.name))
        }
        // Update user session with role from backend
        if (data?.employee_role) {
          const session = getUserSession()
          if (session) {
            session.role = data.employee_role
            setUser({ ...session })
            try {
              sessionStorage.setItem('krew_user', JSON.stringify(session))
            } catch { /* ignore */ }
          }
        }
      })
      .catch(() => {})
  }, [])

  // Fetch teams on mount
  useEffect(() => {
    apiFetch<Array<{ department_id: string; name: string; name_ar: string | null; human_count: number; ai_agent_count: number; total_members: number; }>>('/teams/my')
      .then((data) => {
        if (Array.isArray(data)) setTeams(data)
      })
      .catch(() => {})
  }, [])

  function toggleDept(deptId: string) {
    setExpandedDepts((prev) => {
      const next = new Set(prev)
      if (next.has(deptId)) {
        next.delete(deptId)
      } else {
        if (!teamMembers[deptId]) {
          apiFetch<Array<{ id: string; type: string; name: string; name_ar: string | null; job_title: string; job_title_ar: string | null }>>(`/teams/my/${deptId}/members`)
            .then((data) => {
              if (Array.isArray(data)) {
                setTeamMembers((prev) => ({ ...prev, [deptId]: data }))
              }
            })
            .catch(() => {})
        }
        next.add(deptId)
      }
      return next
    })
  }

  // Fetch DM conversations on mount
  useEffect(() => {
    apiFetch<Array<{
      id: string
      peer_id: string
      peer_name: string
      peer_name_ar: string | null
      peer_job_title: string
      last_message: string | null
      last_message_at: string | null
      unread_count: number
    }>>('/dm/conversations')
      .then((data) => {
        if (Array.isArray(data)) {
          setConversations(data.map((c) => ({
            id: c.id,
            peerId: c.peer_id,
            peerName: c.peer_name,
            peerNameAr: c.peer_name_ar,
            peerJobTitle: c.peer_job_title,
            lastMessage: c.last_message,
            lastMessageAt: c.last_message_at,
            unreadCount: c.unread_count,
          })))
        }
      })
      .catch(() => {})
  }, [])

  // Resolve display name — sync store from sessionStorage if needed
  useEffect(() => {
    if (!user) {
      const session = getUserSession()
      if (session) setUser(session)
    }
  }, [user])

  const displayName = user
    ? isAr && user.nameAr ? user.nameAr : user.name
    : null

  const roleLabel = user?.role
    ? isAr
      ? ROLE_LABELS[user.role]?.ar ?? user.role
      : ROLE_LABELS[user.role]?.en ?? user.role
    : null

  return (
    <aside dir={isAr ? 'rtl' : 'ltr'} className="w-[260px] shrink-0 bg-surface-2 border-e border-border flex flex-col relative">
      <div className="p-4 border-b border-border">
        <div className="text-sm font-semibold text-ink">{isAr ? 'مساحة العمل' : 'Workspace'}</div>
        <div className="text-xs text-ink-dim mt-0.5">Krew HR</div>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {/* ── Agents section ── */}
        <div className="px-4 py-2 text-[11px] font-semibold text-ink-dim uppercase tracking-wider">
          {isAr ? 'الوكلاء' : 'Agents'}
        </div>
        {visibleAgents.map((a) => {
          const isActive = a.id === agentId && !selectedPeerId
          const unread = unreadByAgent[a.id] ?? 0
          return (
            <button
              key={a.id}
              onClick={() => {
                clearSelectedPeer()
                setAgentId(a.id)
              }}
              className={`w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors text-start border-s-2 ${
                isActive
                  ? `${a.colorClass}/10 border-s-current ${a.textColorClass}`
                  : 'text-ink hover:bg-surface-3 border-s-transparent'
              }`}
            >
              <span
                className={`w-6 h-6 rounded-full ${a.colorClass} text-white text-[10px] font-semibold flex items-center justify-center shrink-0`}
              >
                {a.initial}
              </span>
              <span className="flex-1 min-w-0 truncate">
                <span className="font-medium">{isAr ? a.nameAr : a.name}</span>
                <span className="text-ink-dim"> — {isAr ? a.roleAr : a.role}</span>
              </span>
              <span
                className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"
                title="online"
              />
              {unread > 0 && (
                <span
                  className={`ms-1 text-[10px] ${a.colorClass} text-white rounded-full min-w-[16px] h-4 px-1 flex items-center justify-center font-semibold shrink-0`}
                >
                  {unread}
                </span>
              )}
            </button>
          )
        })}

        {/* ── My Teams section ── */}
        {teams.length > 0 && (
          <>
            <button
              onClick={() => setTeamsExpanded((v) => !v)}
              className="w-full flex items-center gap-1 px-4 py-2 mt-2 text-[11px] font-semibold text-ink-dim uppercase tracking-wider hover:text-ink transition-colors"
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" className={`transition-transform ${teamsExpanded ? 'rotate-90' : ''}`}>
                <path d="M3 1l4 4-4 4z" />
              </svg>
              {isAr ? 'فرقي' : 'My Teams'}
            </button>
            {teamsExpanded && teams.map((t) => {
              const isExpanded = expandedDepts.has(t.department_id)
              const members = teamMembers[t.department_id] ?? []
              const humans = members.filter((m) => m.type === 'human')
              const bots = members.filter((m) => m.type === 'ai_agent')
              return (
                <div key={t.department_id}>
                  <button
                    onClick={() => toggleDept(t.department_id)}
                    className="w-full flex items-center gap-1.5 px-4 py-1.5 text-sm text-ink hover:bg-surface-3 transition-colors text-start"
                  >
                    <svg width="8" height="8" viewBox="0 0 10 10" fill="currentColor" className={`transition-transform shrink-0 ${isExpanded ? 'rotate-90' : ''}`}>
                      <path d="M3 1l4 4-4 4z" />
                    </svg>
                    <span className="flex-1 min-w-0 truncate font-medium">
                      {isAr && t.name_ar ? t.name_ar : t.name}
                    </span>
                    <span className="text-[11px] text-ink-dim shrink-0">{t.total_members}</span>
                  </button>
                  {isExpanded && members.length > 0 && (
                    <div className="border-s border-border ms-5">
                      {humans.map((m) => (
                        <button
                          key={m.id}
                          onClick={() => setSelectedPeer(m.id, { id: m.id, name: m.name, nameAr: m.name_ar, jobTitle: m.job_title })}
                          className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-ink hover:bg-surface-3 transition-colors text-start"
                        >
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                          <span className="flex-1 min-w-0 truncate">{isAr && m.name_ar ? m.name_ar : m.name}</span>
                          <span className="text-[10px] text-ink-dim truncate max-w-[60px]">{isAr && m.job_title_ar ? m.job_title_ar : m.job_title}</span>
                        </button>
                      ))}
                      {bots.length > 0 && humans.length > 0 && (
                        <div className="border-t border-border mx-3 my-1" />
                      )}
                      {bots.map((m) => (
                        <button
                          key={m.id}
                          onClick={() => setSelectedPeer(m.id, { id: m.id, name: m.name, nameAr: m.name_ar, jobTitle: m.job_title })}
                          className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-ink hover:bg-surface-3 transition-colors text-start"
                        >
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                          <span className="flex-1 min-w-0">
                            <span className="truncate block">{isAr && m.name_ar ? m.name_ar : m.name}</span>
                            <span className="text-[10px] text-ink-dim truncate block">{isAr && m.job_title_ar ? m.job_title_ar : m.job_title}</span>
                          </span>
                          <span className="text-[9px] font-medium text-emerald-600 bg-emerald-50 px-1 py-0.5 rounded shrink-0">BOT</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </>
        )}

        {/* ── People section ── */}
        <button
          onClick={() => setPeopleExpanded((v) => !v)}
          className="w-full flex items-center gap-1 px-4 py-2 mt-2 text-[11px] font-semibold text-ink-dim uppercase tracking-wider hover:text-ink transition-colors"
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            fill="currentColor"
            className={`transition-transform ${peopleExpanded ? 'rotate-90' : ''}`}
          >
            <path d="M3 1l4 4-4 4z" />
          </svg>
          {isAr ? 'الأشخاص' : 'People'}
          {totalUnread > 0 && (
            <span className="ms-auto text-[10px] bg-rose-500 text-white rounded-full min-w-[16px] h-4 px-1 flex items-center justify-center font-semibold">
              {totalUnread}
            </span>
          )}
        </button>
        {peopleExpanded && conversations.map((c) => {
          const isActive = selectedPeerId === c.peerId
          const unread = unreadByPeer[c.peerId] ?? 0
          const peerInitial = (isAr && c.peerNameAr ? c.peerNameAr : c.peerName).charAt(0).toUpperCase()
          return (
            <button
              key={c.peerId}
              onClick={() => setSelectedPeer(c.peerId, { id: c.peerId, name: c.peerName, nameAr: c.peerNameAr, jobTitle: c.peerJobTitle })}
              className={`w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors text-start border-s-2 ${
                isActive
                  ? 'bg-surface-3 border-s-[#1264a3] text-ink'
                  : 'text-ink hover:bg-surface-3 border-s-transparent'
              }`}
            >
              <span className="w-6 h-6 rounded-full bg-[#1264a3]/20 text-[#1264a3] text-[10px] font-semibold flex items-center justify-center shrink-0">
                {peerInitial}
              </span>
              <span className="flex-1 min-w-0">
                <span className="font-medium truncate block">
                  {isAr && c.peerNameAr ? c.peerNameAr : c.peerName}
                </span>
                {c.lastMessage && (
                  <span className="text-[11px] text-ink-dim truncate block">
                    {c.lastMessage.slice(0, 40)}
                  </span>
                )}
              </span>
              {unread > 0 && (
                <span className="ms-1 text-[10px] bg-rose-500 text-white rounded-full min-w-[16px] h-4 px-1 flex items-center justify-center font-semibold shrink-0">
                  {unread}
                </span>
              )}
            </button>
          )
        })}
        {peopleExpanded && (
          <button
            onClick={() => setShowNewDm(true)}
            className="w-full flex items-center gap-2 px-4 py-1.5 text-[11px] text-ink-dim hover:text-ink transition-colors"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            {isAr ? 'رسالة جديدة' : 'New message'}
          </button>
        )}
        {peopleExpanded && conversations.length === 0 && (
          <div className="px-4 py-3 text-[11px] text-ink-dim">
            {isAr ? 'لا توجد محادثات بعد' : 'No conversations yet'}
          </div>
        )}
      </div>

      {/* New DM search overlay */}
      {showNewDm && <NewDmSearch onClose={() => setShowNewDm(false)} />}
      <div className="p-3 border-t border-border">
        {displayName && (
          <div className="flex items-center gap-2 px-3 py-2 mb-1">
            <span className="w-7 h-7 rounded-full bg-agent-deema/20 text-agent-deema text-[11px] font-bold flex items-center justify-center shrink-0">
              {displayName.charAt(0).toUpperCase()}
            </span>
            <div className="min-w-0">
              <div className="text-sm font-medium text-ink truncate">{displayName}</div>
              {roleLabel && (
                <div className="text-[11px] text-ink-dim truncate">{roleLabel}</div>
              )}
            </div>
          </div>
        )}
        <button
          onClick={() => {
            logout().catch(() => {}).finally(() => {
              sessionStorage.clear()
              window.location.href = '/login'
            })
          }}
          className="w-full flex items-center gap-2 px-3 py-2 text-xs text-ink-dim hover:text-ink hover:bg-surface-3 rounded-md transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          {isAr ? 'تسجيل الخروج' : 'Sign out'}
        </button>
      </div>
    </aside>
  )
}
