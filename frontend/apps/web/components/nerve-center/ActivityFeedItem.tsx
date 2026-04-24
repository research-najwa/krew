/**
 * Single row in the Live Activity Feed. Memoized to avoid re-rendering
 * all 100 items when a new one is appended.
 */
'use client'

import { memo } from 'react'

import { getAgent } from '@/lib/agents'
import { useRelativeTime } from '@/hooks/useRelativeTime'
import type { FeedItem } from '@/lib/activity-feed-store'

function AgentDot({ agentId }: { agentId: string }) {
  const agent = getAgent(agentId)
  if (!agent) return null
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${agent.colorClass} shrink-0`}
    />
  )
}

const KIND_ICON: Record<string, string> = {
  tool_start: '\u2699',
  tool_result: '\u2699',
  message: '\u25C0',
  user_message: '\u25B6',
  agent_switch: '\u21C4',
  error: '\u26A0',
  connection: '\u26A1',
}

function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

function FeedItemRow({ item }: { item: FeedItem }) {
  const timeAgo = useRelativeTime(item.timestamp)
  const agent = getAgent(item.agent)
  const agentName = agent?.name ?? item.agent

  let label: string
  switch (item.kind) {
    case 'tool_start':
      label = `${agentName} → ${item.displayNameEn ?? item.toolName}`
      break
    case 'tool_result':
      label = item.toolSuccess
        ? `${item.displayNameEn ?? item.toolName} done${item.durationMs != null ? ` (${formatDuration(item.durationMs)})` : ''}`
        : `${item.displayNameEn ?? item.toolName} failed`
      break
    case 'message':
      label = `${agentName || 'Agent'} replied`
      break
    case 'user_message':
      label = `You → ${agentName || 'agent'}`
      break
    case 'agent_switch': {
      const to = getAgent(item.toAgent ?? '')?.name ?? item.toAgent ?? 'agent'
      label = `Switched to ${to}`
      break
    }
    case 'error':
      label = item.errorMessage ?? 'Error'
      break
    case 'connection':
      label =
        item.connectionStatus === 'open'
          ? 'Connected'
          : item.connectionStatus === 'closed'
            ? 'Disconnected'
            : item.connectionStatus === 'connecting'
              ? 'Reconnecting…'
              : `Connection: ${item.connectionStatus}`
      break
    default:
      label = 'Activity'
  }

  const isError =
    item.kind === 'error' ||
    (item.kind === 'tool_result' && !item.toolSuccess)
  const isConnection = item.kind === 'connection'
  const isSuccess = item.kind === 'tool_result' && item.toolSuccess

  return (
    <div className="flex items-start gap-2 py-1.5 text-[12px] leading-tight">
      <span className="mt-0.5 text-[10px] shrink-0 w-4 text-center text-ink-faint">
        {KIND_ICON[item.kind] ?? '\u2022'}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          {item.agent && <AgentDot agentId={item.agent} />}
          <span
            className={`truncate ${
              isError
                ? 'text-rose-400'
                : isSuccess
                  ? 'text-emerald-400'
                  : isConnection
                    ? 'text-ink-faint'
                    : 'text-ink-dim'
            }`}
          >
            {label}
          </span>
        </div>
        {item.kind === 'tool_result' && item.resultSummary && (
          <div className="text-[11px] text-ink-faint truncate mt-0.5 ps-3.5">
            {item.resultSummary}
          </div>
        )}
      </div>
      <span className="text-[10px] text-ink-faint shrink-0 mt-0.5 tabular-nums">
        {timeAgo}
      </span>
    </div>
  )
}

export default memo(FeedItemRow)
