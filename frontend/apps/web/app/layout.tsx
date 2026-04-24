import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Krew',
  description: 'AI-powered HR department for the Saudi market.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" dir="ltr" className={`dark ${inter.variable}`}>
      <body className="bg-bg text-ink">{children}</body>
    </html>
  )
}
