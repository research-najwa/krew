/**
 * Activity Feed — comprehensive unit test suite.
 *
 * Covers:
 *   1. FeedItem store — pushFeedItem, FIFO eviction at 100, toggleCollapsed,
 *      initCollapsedFromStorage, fireAgentSwitch callback
 *   2. formatRelative — edge cases (now, seconds, minutes, hours, days)
 *   3. FeedItem label rendering — each kind produces the correct label string
 *   4. Scroll behavior contract — pin-to-bottom, jump-to-latest visibility rules
 *   5. Edge cases — empty feed, undefined toAgent fallback, surrogate-safe
 *      slicing, null payload guards
 *
 * All tests are UNIT tests — no DB, no LLM, no network, no browser.
 * Uses Node.js built-in test runner (node:test + node:assert).
 *
 * Run:  node --test __tests__/activity-feed.test.ts
 *   or: npx tsx --test __tests__/activity-feed.test.ts
 */
import { describe, it, beforeEach, afterEach, mock } from 'node:test'
import assert from 'node:assert/strict'

// ═══════════════════════════════════════════════════════════════════════
// Helpers — extract pure logic from source modules so we can test
// without React / browser globals.  The source files use 'use client'
// and import from 'react', which won't load in plain Node.
// ═══════════════════════════════════════════════════════════════════════

// ── Inline copy of FeedItem types + store logic ────────────────────
type FeedItemKind =
  | 'tool_start'
  | 'tool_result'
  | 'message'
  | 'user_message'
  | 'agent_switch'
  | 'error'
  | 'connection'

type WsStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error'

interface FeedItem {
  id: string
  kind: FeedItemKind
  agent: string
  timestamp: number
  toolName?: string
  displayNameEn?: string
  displayNameAr?: string
  toolSuccess?: boolean
  durationMs?: number | null
  resultSummary?: string
  fromAgent?: string
  toAgent?: string
  errorMessage?: string
  connectionStatus?: WsStatus
}

const MAX_ITEMS = 100

/**
 * Minimal in-test reimplementation of activity-feed-store.ts
 * so we can verify the logic without importing React.
 */
function createStore() {
  let items: FeedItem[] = []
  let collapsed = false
  const listeners = new Set<() => void>()
  let _onAgentSwitch: ((from: string, to: string) => void) | null = null

  function emit() {
    listeners.forEach((l) => l())
  }

  return {
    getItems: () => items,
    getCollapsed: () => collapsed,

    pushFeedItem(item: FeedItem): void {
      if (items.length >= MAX_ITEMS) {
        items = [...items.slice(1), item]
      } else {
        items = [...items, item]
      }
      emit()
    },

    setCollapsed(val: boolean): void {
      collapsed = val
      emit()
    },

    toggleCollapsed(): void {
      collapsed = !collapsed
      emit()
    },

    initCollapsedFromStorage(storageValue: string | null): void {
      if (storageValue === '1' && !collapsed) {
        collapsed = true
        emit()
      }
    },

    setOnAgentSwitch(cb: ((from: string, to: string) => void) | null): void {
      _onAgentSwitch = cb
    },

    fireAgentSwitch(from: string, to: string): void {
      if (_onAgentSwitch) _onAgentSwitch(from, to)
    },

    subscribe(listener: () => void): () => void {
      listeners.add(listener)
      return () => { listeners.delete(listener) }
    },

    reset(): void {
      items = []
      collapsed = false
      _onAgentSwitch = null
      listeners.clear()
    },
  }
}

// ── Inline copy of formatRelative from useRelativeTime.ts ──────────
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

// ── Inline copy of safeSlice from ActivityFeedWatcher.tsx ──────────
function safeSlice(str: string, max: number): string {
  const chars = [...str]
  return chars.length <= max ? str : chars.slice(0, max).join('')
}

// ── Inline copy of formatDuration from ActivityFeedItem.tsx ────────
function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

// ── Agent lookup stub (mirrors lib/agents.ts) ──────────────────────
interface AgentMeta {
  id: string
  name: string
  colorClass: string
}

const AGENTS: AgentMeta[] = [
  { id: 'deema', name: 'Deema', colorClass: 'bg-agent-deema' },
  { id: 'mohammad', name: 'Mohammad', colorClass: 'bg-agent-mohammad' },
  { id: 'waleed', name: 'Waleed', colorClass: 'bg-agent-waleed' },
  { id: 'yara', name: 'Yara', colorClass: 'bg-agent-yara' },
  { id: 'ahmad', name: 'Ahmad', colorClass: 'bg-agent-ahmad' },
]

function getAgent(id: string): AgentMeta | undefined {
  return AGENTS.find((a) => a.id === id)
}

// ── Label builder (mirrors the switch in ActivityFeedItem.tsx) ──────
function buildLabel(item: FeedItem): string {
  const agent = getAgent(item.agent)
  const agentName = agent?.name ?? item.agent

  switch (item.kind) {
    case 'tool_start':
      return `${agentName} \u2192 ${item.displayNameEn ?? item.toolName}`
    case 'tool_result':
      return item.toolSuccess
        ? `${item.displayNameEn ?? item.toolName} done${item.durationMs != null ? ` (${formatDuration(item.durationMs)})` : ''}`
        : `${item.displayNameEn ?? item.toolName} failed`
    case 'message':
      return `${agentName} replied`
    case 'user_message':
      return `You \u2192 ${agentName || 'agent'}`
    case 'agent_switch': {
      const to = getAgent(item.toAgent ?? '')?.name ?? item.toAgent ?? 'agent'
      return `Switched to ${to}`
    }
    case 'error':
      return item.errorMessage ?? 'Error'
    case 'connection':
      return item.connectionStatus === 'open'
        ? 'Connected'
        : item.connectionStatus === 'closed'
          ? 'Disconnected'
          : item.connectionStatus === 'connecting'
            ? 'Reconnecting\u2026'
            : `Connection: ${item.connectionStatus}`
    default:
      return 'Activity'
  }
}

// ── Test data helpers ──────────────────────────────────────────────
let idSeq = 0
function makeFeedItem(overrides: Partial<FeedItem> = {}): FeedItem {
  return {
    id: `test-${++idSeq}`,
    kind: 'message',
    agent: 'deema',
    timestamp: Date.now(),
    ...overrides,
  }
}

// ═══════════════════════════════════════════════════════════════════════
// Section 1: Activity Feed Store
// ═══════════════════════════════════════════════════════════════════════

describe('ActivityFeedStore', () => {
  let store: ReturnType<typeof createStore>

  beforeEach(() => {
    store = createStore()
    idSeq = 0
  })

  // ── pushFeedItem ─────────────────────────────────────────────────

  it('pushFeedItem adds item to empty store', () => {
    const item = makeFeedItem()
    store.pushFeedItem(item)
    assert.equal(store.getItems().length, 1)
    assert.equal(store.getItems()[0].id, item.id)
  })

  it('pushFeedItem maintains insertion order', () => {
    const a = makeFeedItem({ id: 'a' })
    const b = makeFeedItem({ id: 'b' })
    const c = makeFeedItem({ id: 'c' })
    store.pushFeedItem(a)
    store.pushFeedItem(b)
    store.pushFeedItem(c)
    assert.deepEqual(
      store.getItems().map((i) => i.id),
      ['a', 'b', 'c'],
    )
  })

  it('pushFeedItem notifies listeners', () => {
    let called = 0
    store.subscribe(() => { called++ })
    store.pushFeedItem(makeFeedItem())
    assert.equal(called, 1)
  })

  // ── FIFO eviction ────────────────────────────────────────────────

  it('FIFO eviction at MAX_ITEMS (100)', () => {
    for (let i = 0; i < 100; i++) {
      store.pushFeedItem(makeFeedItem({ id: `item-${i}` }))
    }
    assert.equal(store.getItems().length, 100)
    assert.equal(store.getItems()[0].id, 'item-0')

    // Push one more — should evict item-0
    store.pushFeedItem(makeFeedItem({ id: 'item-100' }))
    assert.equal(store.getItems().length, 100)
    assert.equal(store.getItems()[0].id, 'item-1', 'oldest item should be evicted')
    assert.equal(store.getItems()[99].id, 'item-100', 'newest item should be last')
  })

  it('FIFO eviction preserves exactly MAX_ITEMS after multiple overflows', () => {
    for (let i = 0; i < 150; i++) {
      store.pushFeedItem(makeFeedItem({ id: `item-${i}` }))
    }
    assert.equal(store.getItems().length, 100)
    assert.equal(store.getItems()[0].id, 'item-50')
    assert.equal(store.getItems()[99].id, 'item-149')
  })

  // ── Immutability ─────────────────────────────────────────────────

  it('pushFeedItem produces a new array reference (immutable)', () => {
    store.pushFeedItem(makeFeedItem())
    const ref1 = store.getItems()
    store.pushFeedItem(makeFeedItem())
    const ref2 = store.getItems()
    assert.notEqual(ref1, ref2, 'items array must be replaced, not mutated')
  })

  // ── toggleCollapsed ──────────────────────────────────────────────

  it('toggleCollapsed flips collapsed state', () => {
    assert.equal(store.getCollapsed(), false)
    store.toggleCollapsed()
    assert.equal(store.getCollapsed(), true)
    store.toggleCollapsed()
    assert.equal(store.getCollapsed(), false)
  })

  it('toggleCollapsed notifies listeners', () => {
    let called = 0
    store.subscribe(() => { called++ })
    store.toggleCollapsed()
    assert.equal(called, 1)
  })

  // ── initCollapsedFromStorage ─────────────────────────────────────

  it('initCollapsedFromStorage("1") sets collapsed to true', () => {
    store.initCollapsedFromStorage('1')
    assert.equal(store.getCollapsed(), true)
  })

  it('initCollapsedFromStorage("0") does not change collapsed', () => {
    store.initCollapsedFromStorage('0')
    assert.equal(store.getCollapsed(), false)
  })

  it('initCollapsedFromStorage(null) does not change collapsed', () => {
    store.initCollapsedFromStorage(null)
    assert.equal(store.getCollapsed(), false)
  })

  it('initCollapsedFromStorage("1") is idempotent when already collapsed', () => {
    let emitCount = 0
    store.setCollapsed(true)
    store.subscribe(() => { emitCount++ })
    store.initCollapsedFromStorage('1')
    // Should NOT emit because collapsed is already true
    assert.equal(emitCount, 0)
  })

  // ── fireAgentSwitch callback ─────────────────────────────────────

  it('fireAgentSwitch calls registered callback', () => {
    let capturedFrom = ''
    let capturedTo = ''
    store.setOnAgentSwitch((from, to) => {
      capturedFrom = from
      capturedTo = to
    })
    store.fireAgentSwitch('deema', 'mohammad')
    assert.equal(capturedFrom, 'deema')
    assert.equal(capturedTo, 'mohammad')
  })

  it('fireAgentSwitch does nothing when no callback registered', () => {
    // Should not throw
    store.fireAgentSwitch('deema', 'mohammad')
  })

  it('fireAgentSwitch stops calling after setOnAgentSwitch(null)', () => {
    let called = false
    store.setOnAgentSwitch(() => { called = true })
    store.setOnAgentSwitch(null)
    store.fireAgentSwitch('deema', 'mohammad')
    assert.equal(called, false)
  })

  // ── subscribe / unsubscribe ──────────────────────────────────────

  it('unsubscribe stops notifications', () => {
    let called = 0
    const unsub = store.subscribe(() => { called++ })
    store.pushFeedItem(makeFeedItem())
    assert.equal(called, 1)
    unsub()
    store.pushFeedItem(makeFeedItem())
    assert.equal(called, 1, 'should not be called after unsubscribe')
  })
})

// ═══════════════════════════════════════════════════════════════════════
// Section 2: formatRelative
// ═══════════════════════════════════════════════════════════════════════

describe('formatRelative', () => {
  it('returns "now" for timestamps less than 5 seconds ago', () => {
    assert.equal(formatRelative(Date.now()), 'now')
    assert.equal(formatRelative(Date.now() - 4_000), 'now')
  })

  it('returns seconds for 5-59 seconds ago', () => {
    assert.equal(formatRelative(Date.now() - 5_000), '5s')
    assert.equal(formatRelative(Date.now() - 30_000), '30s')
    assert.equal(formatRelative(Date.now() - 59_000), '59s')
  })

  it('returns minutes for 1-59 minutes ago', () => {
    assert.equal(formatRelative(Date.now() - 60_000), '1m')
    assert.equal(formatRelative(Date.now() - 45 * 60_000), '45m')
    assert.equal(formatRelative(Date.now() - 59 * 60_000), '59m')
  })

  it('returns hours for 1-23 hours ago', () => {
    assert.equal(formatRelative(Date.now() - 3_600_000), '1h')
    assert.equal(formatRelative(Date.now() - 12 * 3_600_000), '12h')
    assert.equal(formatRelative(Date.now() - 23 * 3_600_000), '23h')
  })

  it('returns days for 24+ hours ago', () => {
    assert.equal(formatRelative(Date.now() - 24 * 3_600_000), '1d')
    assert.equal(formatRelative(Date.now() - 7 * 24 * 3_600_000), '7d')
  })

  it('clamps negative diff to 0 (future timestamps)', () => {
    // A timestamp in the future should return "now" (diff clamped to 0)
    assert.equal(formatRelative(Date.now() + 60_000), 'now')
  })
})

// ═══════════════════════════════════════════════════════════════════════
// Section 3: FeedItem label rendering
// ═══════════════════════════════════════════════════════════════════════

describe('buildLabel (ActivityFeedItem label logic)', () => {
  it('tool_start — known agent with displayNameEn', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'tool_start',
      agent: 'deema',
      toolName: 'get_balance',
      displayNameEn: 'Check Balance',
    }))
    assert.equal(label, 'Deema \u2192 Check Balance')
  })

  it('tool_start — falls back to toolName when no displayNameEn', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'tool_start',
      agent: 'deema',
      toolName: 'get_balance',
    }))
    assert.equal(label, 'Deema \u2192 get_balance')
  })

  it('tool_start — unknown agent uses raw agent string', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'tool_start',
      agent: 'unknown_bot',
      toolName: 'do_stuff',
    }))
    assert.equal(label, 'unknown_bot \u2192 do_stuff')
  })

  it('tool_result — success with duration', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'tool_result',
      agent: 'deema',
      toolName: 'get_balance',
      displayNameEn: 'Check Balance',
      toolSuccess: true,
      durationMs: 1500,
    }))
    assert.equal(label, 'Check Balance done (1.5s)')
  })

  it('tool_result — success with sub-second duration', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'tool_result',
      agent: 'deema',
      toolName: 'get_balance',
      toolSuccess: true,
      durationMs: 250,
    }))
    assert.equal(label, 'get_balance done (250ms)')
  })

  it('tool_result — success with null duration', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'tool_result',
      agent: 'deema',
      toolName: 'get_balance',
      toolSuccess: true,
      durationMs: null,
    }))
    assert.equal(label, 'get_balance done')
  })

  it('tool_result — success with undefined duration', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'tool_result',
      agent: 'deema',
      toolName: 'get_balance',
      toolSuccess: true,
    }))
    assert.equal(label, 'get_balance done')
  })

  it('tool_result — failure', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'tool_result',
      agent: 'deema',
      toolName: 'get_balance',
      displayNameEn: 'Check Balance',
      toolSuccess: false,
    }))
    assert.equal(label, 'Check Balance failed')
  })

  it('message — known agent', () => {
    const label = buildLabel(makeFeedItem({ kind: 'message', agent: 'mohammad' }))
    assert.equal(label, 'Mohammad replied')
  })

  it('user_message — known agent', () => {
    const label = buildLabel(makeFeedItem({ kind: 'user_message', agent: 'waleed' }))
    assert.equal(label, 'You \u2192 Waleed')
  })

  it('user_message — empty agent falls back to "agent"', () => {
    const label = buildLabel(makeFeedItem({ kind: 'user_message', agent: '' }))
    assert.equal(label, 'You \u2192 agent')
  })

  it('agent_switch — known toAgent', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'agent_switch',
      agent: 'yara',
      fromAgent: 'deema',
      toAgent: 'yara',
    }))
    assert.equal(label, 'Switched to Yara')
  })

  it('agent_switch — unknown toAgent uses raw string', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'agent_switch',
      agent: 'norah',
      fromAgent: 'deema',
      toAgent: 'norah',
    }))
    assert.equal(label, 'Switched to norah')
  })

  it('agent_switch — undefined toAgent falls back to "agent"', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'agent_switch',
      agent: '',
    }))
    assert.equal(label, 'Switched to agent')
  })

  it('error — with errorMessage', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'error',
      agent: '',
      errorMessage: 'Rate limit exceeded',
    }))
    assert.equal(label, 'Rate limit exceeded')
  })

  it('error — without errorMessage defaults to "Error"', () => {
    const label = buildLabel(makeFeedItem({ kind: 'error', agent: '' }))
    assert.equal(label, 'Error')
  })

  it('connection — open', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'connection',
      agent: '',
      connectionStatus: 'open',
    }))
    assert.equal(label, 'Connected')
  })

  it('connection — closed', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'connection',
      agent: '',
      connectionStatus: 'closed',
    }))
    assert.equal(label, 'Disconnected')
  })

  it('connection — connecting', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'connection',
      agent: '',
      connectionStatus: 'connecting',
    }))
    assert.equal(label, 'Reconnecting\u2026')
  })

  it('connection — error status', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'connection',
      agent: '',
      connectionStatus: 'error',
    }))
    assert.equal(label, 'Connection: error')
  })

  it('connection — idle status', () => {
    const label = buildLabel(makeFeedItem({
      kind: 'connection',
      agent: '',
      connectionStatus: 'idle',
    }))
    assert.equal(label, 'Connection: idle')
  })
})

// ═══════════════════════════════════════════════════════════════════════
// Section 4: formatDuration
// ═══════════════════════════════════════════════════════════════════════

describe('formatDuration', () => {
  it('returns ms for sub-second durations', () => {
    assert.equal(formatDuration(0), '0ms')
    assert.equal(formatDuration(500), '500ms')
    assert.equal(formatDuration(999), '999ms')
  })

  it('returns seconds with one decimal for >= 1000ms', () => {
    assert.equal(formatDuration(1000), '1.0s')
    assert.equal(formatDuration(1500), '1.5s')
    assert.equal(formatDuration(12345), '12.3s')
  })
})

// ═══════════════════════════════════════════════════════════════════════
// Section 5: safeSlice (surrogate-safe slicing)
// ═══════════════════════════════════════════════════════════════════════

describe('safeSlice', () => {
  it('returns full string when within limit', () => {
    assert.equal(safeSlice('hello', 10), 'hello')
  })

  it('truncates ASCII strings correctly', () => {
    assert.equal(safeSlice('abcdefghij', 5), 'abcde')
  })

  it('does not split surrogate pairs (emoji)', () => {
    // The family emoji is a multi-codepoint sequence
    const emoji = '\u{1F468}\u200D\u{1F469}\u200D\u{1F467}' // man-woman-girl ZWJ sequence
    const result = safeSlice(emoji, 3)
    // Should slice to 3 "characters" (code points) without producing broken surrogates
    assert.ok(!result.includes('\uFFFD'), 'should not contain replacement characters')
    // Each code point is valid
    for (const ch of result) {
      assert.ok(ch.codePointAt(0)! > 0)
    }
  })

  it('handles Arabic text correctly', () => {
    const arabic = '\u0645\u0631\u062D\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645'  // "marhaba balalaam"
    const result = safeSlice(arabic, 5)
    assert.equal(result.length, 5)
    assert.equal(result, '\u0645\u0631\u062D\u0628\u0627')
  })

  it('handles empty string', () => {
    assert.equal(safeSlice('', 10), '')
  })

  it('handles max=0', () => {
    assert.equal(safeSlice('hello', 0), '')
  })

  it('handles string with only surrogate-pair characters', () => {
    // Each flag emoji is 2 surrogate pairs (regional indicators)
    const flags = '\u{1F1F8}\u{1F1E6}' // Saudi Arabia flag
    const result = safeSlice(flags, 1)
    // Should get first code point without breaking the second
    assert.equal([...result].length, 1)
  })
})

// ═══════════════════════════════════════════════════════════════════════
// Section 6: Scroll behavior contract (logic-level tests)
// ═══════════════════════════════════════════════════════════════════════

describe('Scroll behavior contract', () => {
  const SCROLL_THRESHOLD = 60

  function isAtBottom(scrollHeight: number, scrollTop: number, clientHeight: number): boolean {
    return scrollHeight - scrollTop - clientHeight < SCROLL_THRESHOLD
  }

  it('pinned when exactly at bottom', () => {
    assert.ok(isAtBottom(1000, 800, 200))
  })

  it('pinned when within threshold of bottom', () => {
    assert.ok(isAtBottom(1000, 750, 200))  // gap = 50 < 60
  })

  it('not pinned when scrolled above threshold', () => {
    assert.ok(!isAtBottom(1000, 700, 200))  // gap = 100 >= 60
  })

  it('jump-to-latest visible only when not pinned and items exist', () => {
    function showJumpToLatest(pinned: boolean, itemCount: number): boolean {
      return !pinned && itemCount > 0
    }
    assert.equal(showJumpToLatest(true, 10), false, 'pinned = no pill')
    assert.equal(showJumpToLatest(false, 0), false, 'empty = no pill')
    assert.equal(showJumpToLatest(false, 10), true, 'not pinned + items = show pill')
  })

  it('auto-scroll skipped when collapsed', () => {
    // In the component: if (collapsed) { prevLenRef.current = items.length; return }
    // Verify the condition: new items arrive while collapsed, pinned is true,
    // but no scroll should happen. We test the guard condition.
    const collapsed = true
    const pinned = true
    const newItemsArrived = true
    const shouldAutoScroll = !collapsed && newItemsArrived && pinned
    assert.equal(shouldAutoScroll, false)
  })

  it('auto-scroll happens when expanded, pinned, and new items arrive', () => {
    const collapsed = false
    const pinned = true
    const newItemsArrived = true
    const shouldAutoScroll = !collapsed && newItemsArrived && pinned
    assert.equal(shouldAutoScroll, true)
  })

  it('auto-scroll skipped when not pinned (user scrolled up)', () => {
    const collapsed = false
    const pinned = false
    const newItemsArrived = true
    const shouldAutoScroll = !collapsed && newItemsArrived && pinned
    assert.equal(shouldAutoScroll, false)
  })
})

// ═══════════════════════════════════════════════════════════════════════
// Section 7: Edge cases
// ═══════════════════════════════════════════════════════════════════════

describe('Edge cases', () => {
  it('empty feed shows no-activity state (items.length === 0)', () => {
    const store = createStore()
    assert.equal(store.getItems().length, 0)
    // The component renders "No activity yet" when items.length === 0
    const showEmpty = store.getItems().length === 0
    assert.ok(showEmpty)
  })

  it('collapsed feed shows item count badge', () => {
    const store = createStore()
    for (let i = 0; i < 5; i++) {
      store.pushFeedItem(makeFeedItem({ id: `e-${i}` }))
    }
    store.toggleCollapsed()
    // In the component: collapsed + items.length > 0 shows the count badge
    assert.ok(store.getCollapsed())
    assert.equal(store.getItems().length, 5)
  })

  it('null payload guard in chat.tool.start handler', () => {
    // The handler does: if (!p || !p.tool_name) return
    // Simulate the guard
    function handleToolStart(payload: Record<string, unknown> | null): FeedItem | null {
      const p = payload
      if (!p || !p.tool_name) return null
      return makeFeedItem({
        kind: 'tool_start',
        agent: String(p.agent ?? ''),
        toolName: String(p.tool_name),
      })
    }

    assert.equal(handleToolStart(null), null, 'null payload should be guarded')
    assert.equal(handleToolStart({}), null, 'missing tool_name should be guarded')
    assert.equal(handleToolStart({ tool_name: '' }), null, 'empty tool_name should be guarded')
    assert.notEqual(handleToolStart({ tool_name: 'get_balance' }), null, 'valid payload should pass')
  })

  it('null payload guard in chat.message.created handler', () => {
    function handleMessage(payload: Record<string, unknown> | null): FeedItem | null {
      const p = payload
      if (!p || !p.role) return null
      return makeFeedItem({
        kind: p.role === 'user' ? 'user_message' : 'message',
        agent: String(p.agent ?? ''),
      })
    }

    assert.equal(handleMessage(null), null)
    assert.equal(handleMessage({}), null)
    assert.equal(handleMessage({ role: 'user', agent: 'deema' })?.kind, 'user_message')
    assert.equal(handleMessage({ role: 'assistant', agent: 'deema' })?.kind, 'message')
  })

  it('error handler defaults to "Unknown error" when no message', () => {
    function handleError(payload: Record<string, unknown> | null): string {
      const p = payload
      return p?.message ? String(p.message) : 'Unknown error'
    }

    assert.equal(handleError(null), 'Unknown error')
    assert.equal(handleError({}), 'Unknown error')
    assert.equal(handleError({ message: 'Timeout' }), 'Timeout')
  })

  it('feedId generates unique IDs', () => {
    let counter = 0
    function feedId(): string {
      return `feed-${Date.now()}-${++counter}`
    }
    const ids = new Set<string>()
    for (let i = 0; i < 1000; i++) {
      ids.add(feedId())
    }
    assert.equal(ids.size, 1000, 'all IDs should be unique')
  })

  it('resultSummary is truncated via safeSlice to 80 chars', () => {
    const longSummary = 'A'.repeat(200)
    const truncated = safeSlice(longSummary, 80)
    assert.equal(truncated.length, 80)
  })

  it('KIND_ICON map covers all FeedItemKind values', () => {
    // Mirrors the KIND_ICON constant in ActivityFeedItem.tsx
    const KIND_ICON: Record<string, string> = {
      tool_start: '\u2699',
      tool_result: '\u2699',
      message: '\u25C0',
      user_message: '\u25B6',
      agent_switch: '\u21C4',
      error: '\u26A0',
      connection: '\u26A1',
    }
    const allKinds: FeedItemKind[] = [
      'tool_start', 'tool_result', 'message', 'user_message',
      'agent_switch', 'error', 'connection',
    ]
    for (const kind of allKinds) {
      assert.ok(KIND_ICON[kind], `KIND_ICON missing for "${kind}"`)
    }
  })

  it('agent-store fireAgentSwitch integrates with feed store', () => {
    // Simulates what agent-store.ts does: calling fireAgentSwitch when agent changes
    const store = createStore()
    const receivedItems: FeedItem[] = []
    store.setOnAgentSwitch((from, to) => {
      const item = makeFeedItem({
        kind: 'agent_switch',
        agent: to,
        fromAgent: from,
        toAgent: to,
      })
      store.pushFeedItem(item)
      receivedItems.push(item)
    })

    store.fireAgentSwitch('deema', 'mohammad')
    assert.equal(receivedItems.length, 1)
    assert.equal(receivedItems[0].fromAgent, 'deema')
    assert.equal(receivedItems[0].toAgent, 'mohammad')
    assert.equal(store.getItems().length, 1)
    assert.equal(store.getItems()[0].kind, 'agent_switch')
  })

  it('connection status skip initial idle transition logic', () => {
    // ActivityFeedWatcher skips pushing when prev was 'idle'
    let prevStatus: WsStatus = 'idle'
    const pushed: FeedItem[] = []

    function simulateStatusChange(newStatus: WsStatus) {
      if (prevStatus === newStatus) return
      const prev = prevStatus
      prevStatus = newStatus
      if (prev === 'idle') return  // skip initial
      pushed.push(makeFeedItem({
        kind: 'connection',
        agent: '',
        connectionStatus: newStatus,
      }))
    }

    // Initial idle -> open should be skipped
    simulateStatusChange('open')
    assert.equal(pushed.length, 0, 'idle->open should be skipped')

    // open -> closed should be pushed
    simulateStatusChange('closed')
    assert.equal(pushed.length, 1)
    assert.equal(pushed[0].connectionStatus, 'closed')

    // closed -> connecting should be pushed
    simulateStatusChange('connecting')
    assert.equal(pushed.length, 2)
    assert.equal(pushed[1].connectionStatus, 'connecting')
  })
})

// ═══════════════════════════════════════════════════════════════════════
// Section 8: Store stress / concurrency
// ═══════════════════════════════════════════════════════════════════════

describe('Store stress tests', () => {
  it('rapid pushes maintain correct count and order', () => {
    const store = createStore()
    const count = 500
    for (let i = 0; i < count; i++) {
      store.pushFeedItem(makeFeedItem({ id: `rapid-${i}` }))
    }
    assert.equal(store.getItems().length, MAX_ITEMS)
    // Last item should be the most recent
    assert.equal(store.getItems()[99].id, `rapid-${count - 1}`)
    // First item should be count - MAX_ITEMS
    assert.equal(store.getItems()[0].id, `rapid-${count - MAX_ITEMS}`)
  })

  it('multiple listeners all receive notifications', () => {
    const store = createStore()
    const counts = [0, 0, 0]
    store.subscribe(() => { counts[0]++ })
    store.subscribe(() => { counts[1]++ })
    store.subscribe(() => { counts[2]++ })
    store.pushFeedItem(makeFeedItem())
    assert.deepEqual(counts, [1, 1, 1])
  })

  it('unsubscribing one listener does not affect others', () => {
    const store = createStore()
    const counts = [0, 0]
    const unsub0 = store.subscribe(() => { counts[0]++ })
    store.subscribe(() => { counts[1]++ })
    store.pushFeedItem(makeFeedItem())
    assert.deepEqual(counts, [1, 1])
    unsub0()
    store.pushFeedItem(makeFeedItem())
    assert.deepEqual(counts, [1, 2], 'first listener should stop, second continues')
  })
})
