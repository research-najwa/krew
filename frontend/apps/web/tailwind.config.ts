import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: 'hsl(var(--bg) / <alpha-value>)',
        surface: 'hsl(var(--surface) / <alpha-value>)',
        'surface-2': 'hsl(var(--surface-2) / <alpha-value>)',
        'surface-3': 'hsl(var(--surface-3) / <alpha-value>)',
        border: 'hsl(var(--border) / <alpha-value>)',
        ink: 'hsl(var(--text) / <alpha-value>)',
        'ink-dim': 'hsl(var(--text-dim) / <alpha-value>)',
        'ink-faint': 'hsl(var(--text-faint) / <alpha-value>)',
        agent: {
          deema: '#6366f1',
          mohammad: '#10b981',
          waleed: '#f59e0b',
          yara: '#f43f5e',
          ahmad: '#3b82f6',
        },
        success: '#10b981',
        warning: '#f59e0b',
        danger: '#ef4444',
        info: '#3b82f6',
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        ar: [
          'IBM Plex Sans Arabic',
          'Inter',
          'ui-sans-serif',
          'system-ui',
          'sans-serif',
        ],
      },
      keyframes: {
        pulseRing: {
          '0%': { boxShadow: '0 0 0 0 rgba(99, 102, 241, 0.6)' },
          '70%': { boxShadow: '0 0 0 8px rgba(99, 102, 241, 0)' },
          '100%': { boxShadow: '0 0 0 0 rgba(99, 102, 241, 0)' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
      },
      animation: {
        'pulse-ring': 'pulseRing 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        blink: 'blink 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}

export default config
