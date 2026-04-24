/**
 * Shared metadata for Krew's 5 super agents.
 *
 * Keep this file dependency-free — it's imported by both client components
 * (Sidebar, MainChat, AgentStatusRail) and the agent store.
 */

export interface AgentMeta {
  id: string
  name: string
  nameAr: string
  role: string
  roleAr: string
  initial: string
  colorClass: string
  textColorClass: string
  greeting: string
  greetingAr: string
}

export const AGENTS: readonly AgentMeta[] = [
  {
    id: 'deema',
    name: 'Deema',
    nameAr: 'ديما',
    role: 'Employee Services',
    roleAr: 'خدمات الموظفين',
    initial: 'D',
    colorClass: 'bg-agent-deema',
    textColorClass: 'text-agent-deema',
    greeting:
      "Hi! I'm Deema, your Employee Services agent. How can I help you today?",
    greetingAr:
      'أهلاً! أنا ديما، وكيلة خدمات الموظفين. كيف أقدر أساعدك اليوم؟',
  },
  {
    id: 'mohammad',
    name: 'Mohammad',
    nameAr: 'محمد',
    role: 'Recruitment',
    roleAr: 'التوظيف',
    initial: 'M',
    colorClass: 'bg-agent-mohammad',
    textColorClass: 'text-agent-mohammad',
    greeting: "Hi! I'm Mohammad — I handle recruitment and hiring.",
    greetingAr: 'أهلاً! أنا محمد — مسؤول التوظيف والاستقطاب.',
  },
  {
    id: 'waleed',
    name: 'Waleed',
    nameAr: 'وليد',
    role: 'HRBP — HR Business Partner',
    roleAr: 'شريك أعمال الموارد البشرية',
    initial: 'W',
    colorClass: 'bg-agent-waleed',
    textColorClass: 'text-agent-waleed',
    greeting: 'Hey, Waleed here — your HR Business Partner for onboarding and team management.',
    greetingAr: 'أهلاً، أنا وليد — شريك أعمال الموارد البشرية لإدارة الفريق والتأهيل.',
  },
  {
    id: 'yara',
    name: 'Yara',
    nameAr: 'يارا',
    role: 'AI Workforce Architect',
    roleAr: 'مهندسة القوى العاملة الذكية',
    initial: 'Y',
    colorClass: 'bg-agent-yara',
    textColorClass: 'text-agent-yara',
    greeting: "Hi, I'm Yara — AI workforce architecture and governance.",
    greetingAr: 'أهلاً، أنا يارا — مهندسة القوى العاملة الذكية والحوكمة.',
  },
  {
    id: 'ahmad',
    name: 'Ahmad',
    nameAr: 'أحمد',
    role: 'CHRO',
    roleAr: 'الرئيس التنفيذي للموارد البشرية',
    initial: 'A',
    colorClass: 'bg-agent-ahmad',
    textColorClass: 'text-agent-ahmad',
    greeting: "Hello, I'm Ahmad — strategic HR and analytics.",
    greetingAr: 'أهلاً، أنا أحمد — التحليلات الاستراتيجية للموارد البشرية.',
  },
] as const

export function getAgent(id: string): AgentMeta | undefined {
  return AGENTS.find((a) => a.id === id)
}

export const DEFAULT_AGENT_ID = 'deema'
