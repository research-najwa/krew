import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

export default function RootPage() {
  const token = cookies().get('krew_chat_jwt')?.value
  if (token) {
    redirect('/chat')
  }
  redirect('/login')
}
