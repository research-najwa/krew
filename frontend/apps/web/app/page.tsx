'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { getAuthToken } from '@/lib/auth'

export default function RootPage() {
  const router = useRouter()

  useEffect(() => {
    if (getAuthToken()) {
      router.replace('/chat')
    } else {
      router.replace('/login')
    }
  }, [router])

  return null
}
