import AgentStatusRail from '@/components/nerve-center/AgentStatusRail'
import Sidebar from '@/components/nerve-center/Sidebar'
import LiveActivityFeed from '@/components/nerve-center/LiveActivityFeed'
import ActivityFeedWatcher from '@/components/nerve-center/ActivityFeedWatcher'

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg text-ink">
      <AgentStatusRail />
      <Sidebar />
      <main className="flex-1 min-w-0 min-h-0 flex flex-col">{children}</main>
      <ActivityFeedWatcher />
      <LiveActivityFeed />
    </div>
  )
}
