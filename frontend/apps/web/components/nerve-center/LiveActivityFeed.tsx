'use client'

import { useCurrentAgent, type Locale } from '@/lib/agent-store'
import { AGENT_CAPABILITIES, type ToolCategory } from '@/lib/agent-capabilities'
import { getAgent } from '@/lib/agents'

function sendPrompt(text: string) {
  window.dispatchEvent(new CustomEvent<string>('krew:send-prompt', { detail: text }))
}

function ToolCategorySection({ cat, locale }: { cat: ToolCategory; locale: Locale }) {
  const isAr = locale === 'ar'
  return (
    <div className="mb-1">
      <div className="text-[11px] font-semibold text-ink-dim mb-1 flex items-center gap-1.5 px-2.5 pt-3 pb-1">
        <span>{cat.icon}</span>
        {isAr ? cat.nameAr : cat.name}
      </div>
      <div className="mx-2 rounded-lg border border-border bg-surface overflow-hidden divide-y divide-border">
        {cat.actions.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={() => sendPrompt(isAr ? action.promptAr : action.prompt)}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-ink hover:bg-surface-3 transition-colors text-start cursor-pointer group"
          >
            <span className="text-sm shrink-0">{action.icon}</span>
            <span className="flex-1 min-w-0 truncate font-medium">
              {isAr ? action.labelAr : action.label}
            </span>
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`shrink-0 text-ink-faint opacity-0 group-hover:opacity-100 transition-opacity ${isAr ? 'rotate-180' : ''}`}
            >
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
        ))}
      </div>
    </div>
  )
}

export default function LiveActivityFeed() {
  const { agentId, locale } = useCurrentAgent()
  const agent = getAgent(agentId)
  const capabilities = AGENT_CAPABILITIES[agentId] ?? []
  const isAr = locale === 'ar'

  if (!agent) return null

  return (
    <aside dir={isAr ? 'rtl' : 'ltr'} className="w-[260px] shrink-0 bg-surface-2 border-s border-border flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center gap-2">
          <div
            className={`w-7 h-7 rounded-lg ${agent.colorClass} flex items-center justify-center text-white text-[10px] font-bold shrink-0`}
          >
            {agent.initial}
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-ink">
              {isAr ? agent.nameAr : agent.name}
            </div>
            <div className="text-[11px] text-ink-dim truncate">
              {isAr ? agent.roleAr : agent.role}
            </div>
          </div>
        </div>
      </div>

      {/* Tools list */}
      <div className="flex-1 overflow-y-auto px-2 py-3">
        {capabilities.length === 0 ? (
          <div className="text-xs text-ink-faint text-center mt-8 px-4">
            {isAr ? 'لا توجد أدوات لهذا الوكيل' : 'No tools configured for this agent'}
          </div>
        ) : (
          capabilities.map((cat) => (
            <ToolCategorySection key={cat.name} cat={cat} locale={locale} />
          ))
        )}
      </div>
    </aside>
  )
}
