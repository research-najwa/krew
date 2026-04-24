'use client'

import MainChat from '@/components/nerve-center/MainChat'
import DmChat from '@/components/nerve-center/DmChat'
import { usePeople } from '@/lib/people-store'

export default function ChatPage() {
  const { selectedPeerId } = usePeople()

  if (selectedPeerId) {
    return <DmChat />
  }
  return <MainChat />
}
