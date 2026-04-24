'use client'

import { AGENTS } from '@/lib/agents'
import { useCurrentAgent } from '@/lib/agent-store'

// Static per-agent ring class map so Tailwind JIT picks up the exact strings.
const RING_CLASS: Record<string, string> = {
  deema: 'ring-2 ring-agent-deema ring-offset-2 ring-offset-surface-3',
  mohammad: 'ring-2 ring-agent-mohammad ring-offset-2 ring-offset-surface-3',
  waleed: 'ring-2 ring-agent-waleed ring-offset-2 ring-offset-surface-3',
  yara: 'ring-2 ring-agent-yara ring-offset-2 ring-offset-surface-3',
  ahmad: 'ring-2 ring-agent-ahmad ring-offset-2 ring-offset-surface-3',
}

export default function AgentStatusRail() {
  const { agentId, setAgentId } = useCurrentAgent()

  return (
    <aside className="w-16 shrink-0 bg-surface-3 border-e border-border flex flex-col items-center py-4 gap-3">
      <div className="text-[10px] font-bold text-ink uppercase tracking-wider mb-2">
        Krew
      </div>
      {AGENTS.map((a) => {
        const isActive = a.id === agentId
        return (
          <button
            key={a.id}
            onClick={() => setAgentId(a.id)}
            className={`w-10 h-10 rounded-full ${a.colorClass} text-white font-semibold flex items-center justify-center transition-all ${
              isActive ? `${RING_CLASS[a.id]} scale-110` : 'hover:scale-105'
            }`}
            title={a.name}
          >
            {a.initial}
          </button>
        )
      })}
    </aside>
  )
}
