'use client'

import { useState, type ReactNode } from 'react'

export type ToolStatus = 'running' | 'success' | 'error'
export type Locale = 'en' | 'ar'

export interface ToolCardProps {
  toolName: string
  displayNameEn: string
  displayNameAr: string
  status: ToolStatus
  resultSummary?: string
  resultData?: Record<string, unknown> | null
  durationMs?: number | null
  agent: string
  locale?: Locale
  onAction?: (text: string) => void
}

// ── Label translation map ───────────────────────────────────────
const AR_LABELS: Record<string, string> = {
  // Status
  'Running...': 'جارٍ...',
  'Done': 'تم',
  'Error': 'خطأ',
  // Common
  'Name': 'الاسم',
  'Status': 'الحالة',
  'Department': 'القسم',
  'Employee': 'الموظف',
  'Period': 'الفترة',
  'Type': 'النوع',
  'Date': 'التاريخ',
  'Note': 'ملاحظة',
  'Role': 'الدور',
  'Email': 'البريد الإلكتروني',
  'Phone': 'الهاتف',
  'Manager': 'المدير',
  'Title': 'المسمى',
  // Leave
  'Annual Leave Balance': 'رصيد الإجازة السنوية',
  'days': 'أيام',
  'Request ID': 'رقم الطلب',
  'Leave Type': 'نوع الإجازة',
  'Start': 'البداية',
  'End': 'النهاية',
  'Days': 'الأيام',
  'Reason': 'السبب',
  'Approved By': 'تمت الموافقة بواسطة',
  'Cancel this request': 'إلغاء هذا الطلب',
  'Leave': 'إجازة',
  'No leave requests found': 'لا توجد طلبات إجازات',
  'No upcoming leaves': 'لا توجد إجازات قادمة',
  // Profile
  'Employee #': 'رقم الموظف',
  'Job Title': 'المسمى الوظيفي',
  'Hire Date': 'تاريخ التعيين',
  'Nationality': 'الجنسية',
  // Payslip
  'Basic Salary': 'الراتب الأساسي',
  'Housing Allowance': 'بدل السكن',
  'Transport Allowance': 'بدل النقل',
  'Allowances': 'البدلات',
  'Deductions': 'الخصومات',
  'GOSI': 'التأمينات الاجتماعية',
  'Net Pay': 'صافي الراتب',
  // Tickets
  'Ticket ID': 'رقم التذكرة',
  'Subject': 'الموضوع',
  'Ticket': 'تذكرة',
  'No tickets found': 'لا توجد تذاكر',
  'Category': 'الفئة',
  'Priority': 'الأولوية',
  'Created': 'تاريخ الإنشاء',
  'Assigned To': 'مسند إلى',
  'Last Update': 'آخر تحديث',
  'Description': 'الوصف',
  // Documents
  'Document': 'مستند',
  'Expiry Date': 'تاريخ الانتهاء',
  'Issued': 'تاريخ الإصدار',
  'Issuer': 'جهة الإصدار',
  'Doc #': 'رقم المستند',
  'Info': 'معلومات',
  'No documents found': 'لا توجد مستندات',
  // Team
  'Team Member': 'عضو الفريق',
  'No team members found': 'لا يوجد أعضاء في الفريق',
  'Joined': 'تاريخ الانضمام',
  // Approvals
  'No pending approvals': 'لا توجد موافقات معلقة',
  'Pending': 'قيد الانتظار',
  // Candidates
  'Candidate': 'المرشح',
  'candidates found': 'مرشحين',
  'Current Title': 'المسمى الحالي',
  'Company': 'الشركة',
  'Experience': 'الخبرة',
  'Education': 'التعليم',
  'Skills': 'المهارات',
  'Match Score': 'نسبة التطابق',
  'Applied': 'تاريخ التقديم',
  'Notes': 'ملاحظات',
  // Jobs
  'Position': 'المنصب',
  'Salary': 'الراتب',
  'Location': 'الموقع',
  'Applicants': 'المتقدمين',
  'Posted': 'تاريخ النشر',
  'Closes': 'تاريخ الإغلاق',
  'No job postings found': 'لا توجد وظائف شاغرة',
  // Interviews
  'Date/Time': 'التاريخ/الوقت',
  'Interviewers': 'المقابلين',
  // Pipeline
  'Stage': 'المرحلة',
  'Count': 'العدد',
  'Candidates': 'المرشحين',
  'Avg Days in Stage': 'متوسط الأيام في المرحلة',
  'Conversion Rate': 'نسبة التحويل',
  'Total Candidates': 'إجمالي المرشحين',
  'Open Positions': 'المناصب الشاغرة',
  'Interviews Scheduled': 'المقابلات المجدولة',
  'Offers Pending': 'العروض المعلقة',
  // Onboarding
  'Onboarding Progress': 'تقدم التأهيل',
  'tasks': 'مهام',
  // Team Dashboard
  'Team Size': 'حجم الفريق',
  'Saudi': 'سعودي',
  'Non-Saudi': 'غير سعودي',
  'Saudization': 'نسبة السعودة',
  'Pending Approvals': 'الموافقات المعلقة',
  'Active Onboarding': 'التأهيل النشط',
  'On Leave This Week': 'في إجازة هذا الأسبوع',
  'Expiring Documents': 'مستندات قاربت على الانتهاء',
  'Probation Ending Soon': 'فترة التجربة توشك على الانتهاء',
  // Attendance
  'Avg Attendance': 'متوسط الحضور',
  'Total Late': 'إجمالي التأخير',
  'Per Employee': 'لكل موظف',
  // Compensation
  'Avg Salary': 'متوسط الراتب',
  'Median Salary': 'الراتب المتوسط',
  'Min Salary': 'أقل راتب',
  'Max Salary': 'أعلى راتب',
  'Monthly Cost': 'التكلفة الشهرية',
  'Annual Cost': 'التكلفة السنوية',
  'By Nationality': 'حسب الجنسية',
  'Salary Distribution': 'توزيع الرواتب',
  'Budget Utilization': 'استخدام الميزانية',
  'Below 10K': 'أقل من 10 آلاف',
  '10K – 15K': '10 – 15 ألف',
  '15K – 20K': '15 – 20 ألف',
  '20K – 30K': '20 – 30 ألف',
  'Above 30K': 'أكثر من 30 ألف',
  // Flight Risk
  'High Risk': 'خطر عالي',
  'Medium Risk': 'خطر متوسط',
  'Low Risk': 'خطر منخفض',
  'Risk Score': 'درجة الخطر',
  'Tenure': 'مدة الخدمة',
  'months': 'أشهر',
  'Risk Factors': 'عوامل الخطر',
  'Recommendations': 'التوصيات',
  'No flight risk data available': 'لا تتوفر بيانات مخاطر المغادرة',
  // Action Items
  'items': 'عناصر',
  'urgent': 'عاجل',
  'No pending action items — you\'re all caught up!': 'لا توجد إجراءات معلقة — أنت منجز!',
  // Compliance
  'Compliant': 'ملتزم',
  'Non-Compliant': 'غير ملتزم',
  'Expired Documents': 'مستندات منتهية',
  'Missing GOSI': 'تأمينات ناقصة',
  // PIP
  'Performance Improvement Plan': 'خطة تحسين الأداء',
  'Start Date': 'تاريخ البداية',
  'End Date': 'تاريخ النهاية',
  'Duration': 'المدة',
  'Performance Issues': 'مشاكل الأداء',
  'Improvement Objectives': 'أهداف التحسين',
  'Target:': 'الهدف:',
  'Measured by:': 'يُقاس بـ:',
  '90-Day Timeline': 'الجدول الزمني — 90 يوم',
  'Review:': 'المراجعة:',
  'Support Provided': 'الدعم المقدم',
  'Consequences': 'العواقب',
  'Review Schedule': 'جدول المراجعة',
  'Send as Email': 'إرسال بالبريد',
  'Schedule 1:1': 'جدولة اجتماع',
  // 1:1 Prep
  'Last 1:1': 'آخر اجتماع',
  'Talking Points': 'نقاط النقاش',
  'Recent Leaves': 'الإجازات الأخيرة',
  // Headcount
  'employees': 'موظفين',
  'Headcount': 'عدد الموظفين',
  'Budget': 'الميزانية',
  // Turnover
  'turnover rate': 'معدل الدوران',
  'Voluntary': 'طوعي',
  'Involuntary': 'غير طوعي',
  // Saudization
  'Saudization Rate': 'نسبة السعودة',
  'Target': 'المستهدف',
  'Compliance': 'الالتزام',
  'Below Target': 'أقل من المستهدف',
  // Salary
  'Average': 'المتوسط',
  'Median': 'الوسيط',
  'Minimum': 'الأدنى',
  'Maximum': 'الأقصى',
  'Total Payroll': 'إجمالي الرواتب',
  // Agents
  'Agent': 'الوكيل',
  'Conversations': 'المحادثات',
  'Resolution Rate': 'نسبة الحل',
  'Avg Response': 'متوسط الاستجابة',
  'Deployed': 'تاريخ النشر',
  'Last Active': 'آخر نشاط',
  'No agents found': 'لا يوجد وكلاء',
  'Total Conversations': 'إجمالي المحادثات',
  'Avg Response Time': 'متوسط وقت الاستجابة',
  'Satisfaction': 'الرضا',
  'Escalation Rate': 'نسبة التصعيد',
  // Generic
  'on probation': 'في فترة التجربة',
  'No employees currently on probation': 'لا يوجد موظفين في فترة التجربة حالياً',
}

/** Translate a label. Returns Arabic if locale is 'ar' and a translation exists, otherwise returns the original. */
function t(label: string, locale: Locale): string {
  if (locale !== 'ar') return label
  return AR_LABELS[label] ?? label
}

// ── Agent color mapping for gradients ────────────────────────────
const AGENT_GRADIENT: Record<string, string> = {
  deema: 'from-[#6366f1] to-[#8b5cf6]',
  mohammad: 'from-[#10b981] to-[#34d399]',
  waleed: 'from-[#f59e0b] to-[#fbbf24]',
  yara: 'from-[#f43f5e] to-[#fb7185]',
  ahmad: 'from-[#3b82f6] to-[#60a5fa]',
}

const AGENT_ICON_BG: Record<string, string> = {
  deema: 'bg-[#6366f1]/15 text-[#6366f1]',
  mohammad: 'bg-[#10b981]/15 text-[#10b981]',
  waleed: 'bg-[#f59e0b]/15 text-[#f59e0b]',
  yara: 'bg-[#f43f5e]/15 text-[#f43f5e]',
  ahmad: 'bg-[#3b82f6]/15 text-[#3b82f6]',
}

// ── Helpers ──────────────────────────────────────────────────────

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function safeGet(data: Record<string, unknown> | null | undefined, key: string): unknown {
  if (!data || typeof data !== 'object') return undefined
  return data[key]
}

function safeNum(val: unknown): number {
  if (typeof val === 'number') return val
  if (typeof val === 'string') {
    const n = parseFloat(val)
    return isNaN(n) ? 0 : n
  }
  return 0
}

function safeStr(val: unknown): string {
  if (val === null || val === undefined) return ''
  return String(val)
}

function formatSAR(val: unknown): string {
  const n = safeNum(val)
  return `SAR ${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

// ── Sub-components ───────────────────────────────────────────────

function ResultRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between items-center mb-2.5 last:mb-0">
      <span className="text-xs text-ink-dim">{label}</span>
      <span className="text-sm font-bold text-ink">{children}</span>
    </div>
  )
}

function ProgressBar({ value, max, agent }: { value: number; max: number; agent: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  const gradient = AGENT_GRADIENT[agent] ?? AGENT_GRADIENT.deema
  return (
    <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden mt-1.5 mb-3">
      <div
        className={`h-full rounded-full bg-gradient-to-r ${gradient}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function StatusBadge({ text, variant }: { text: string; variant: 'success' | 'warning' | 'error' }) {
  const cls =
    variant === 'success'
      ? 'bg-emerald-500/15 text-emerald-500'
      : variant === 'warning'
      ? 'bg-amber-500/15 text-amber-500'
      : 'bg-rose-500/15 text-rose-500'
  return (
    <span className={`inline-block text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase ${cls}`}>
      {text}
    </span>
  )
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div dir="auto" className="flex justify-between items-center mb-2.5 last:mb-0">
      <span className="text-xs text-ink-dim">{label}</span>
      <span className="text-[13px] font-semibold text-ink">{value}</span>
    </div>
  )
}

function CompactList({ items }: { items: Array<{ label: string; detail: string; badge?: { text: string; variant: 'success' | 'warning' | 'error' } }> }) {
  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={i} className="flex items-center justify-between gap-2 text-xs">
          <span className="text-ink font-medium truncate">{item.label}</span>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-ink-dim">{item.detail}</span>
            {item.badge && <StatusBadge text={item.badge.text} variant={item.badge.variant} />}
          </div>
        </div>
      ))}
    </div>
  )
}

/** Clickable row that expands to show detail fields on click */
function ExpandableRow({ summary, details, badge, action }: {
  summary: { label: string; subtitle?: string }
  details: Array<[string, string]>
  badge?: { text: string; variant: 'success' | 'warning' | 'error' }
  action?: { label: string; onClick: () => void; variant?: 'danger' | 'default' }
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-surface-3 transition-colors cursor-pointer"
      >
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-ink truncate">{summary.label}</div>
          {Boolean(summary.subtitle) && (
            <div className="text-[11px] text-ink-dim truncate mt-0.5">{summary.subtitle}</div>
          )}
        </div>
        {badge && <StatusBadge text={badge.text} variant={badge.variant} />}
        <svg
          width="12"
          height="12"
          viewBox="0 0 16 16"
          fill="currentColor"
          className={`text-ink-faint transition-transform shrink-0 ${open ? 'rotate-180' : ''}`}
        >
          <path d="M4.3 5.7a1 1 0 0 1 1.4 0L8 8.08l2.3-2.38a1 1 0 1 1 1.4 1.4l-3 3.1a1 1 0 0 1-1.4 0l-3-3.1a1 1 0 0 1 0-1.4z" />
        </svg>
      </button>
      {open && (
        <div className="px-3 pb-2.5 pt-1 border-t border-border bg-surface-2 space-y-1.5">
          {details.map(([k, v]) => (
            <div key={k} className="flex justify-between text-[11px]">
              <span className="text-ink-dim">{k}</span>
              <span className="text-ink font-medium text-right max-w-[60%] truncate">{v}</span>
            </div>
          ))}
          {action && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); action.onClick() }}
              className={`mt-1.5 w-full px-3 py-1.5 text-[11px] font-semibold rounded-lg transition-colors cursor-pointer ${
                action.variant === 'danger'
                  ? 'bg-rose-500/15 text-rose-500 hover:bg-rose-500/25'
                  : 'bg-surface-3 text-ink-dim hover:bg-surface-2'
              }`}
            >
              {action.label}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/** Table-style list with clickable rows for drill-down */
function InteractiveTable({ columns, rows }: {
  columns: string[]
  rows: Array<{
    cells: string[]
    details: Array<[string, string]>
    badge?: { text: string; variant: 'success' | 'warning' | 'error' }
    action?: { label: string; onClick: () => void; variant?: 'danger' | 'default' }
  }>
}) {
  return (
    <div className="space-y-1.5">
      {/* Column headers */}
      <div className="flex items-center gap-2 px-3 pb-1 border-b border-border">
        {columns.map((col, i) => (
          <span key={col} className={`text-[10px] uppercase tracking-wider text-ink-faint font-semibold ${i === 0 ? 'flex-1 min-w-0' : 'shrink-0'}`}>
            {col}
          </span>
        ))}
        <span className="w-3 shrink-0" /> {/* space for chevron */}
      </div>
      {/* Rows */}
      {rows.map((row, i) => (
        <ExpandableRow
          key={i}
          summary={{ label: row.cells[0] ?? '', subtitle: row.cells.length > 2 ? row.cells.slice(1, -1).join(' · ') : undefined }}
          details={row.details}
          badge={row.badge}
          action={row.action}
        />
      ))}
    </div>
  )
}

function BigNumber({ value, unit, trend }: { value: string; unit?: string; trend?: 'up' | 'down' | null }) {
  return (
    <div className="flex items-baseline gap-2 mb-2">
      <span className="text-2xl font-bold text-ink">{value}</span>
      {unit && <span className="text-xs text-ink-dim font-medium">{unit}</span>}
      {trend === 'up' && <span className="text-rose-500 text-sm font-semibold ml-1">&#8593;</span>}
      {trend === 'down' && <span className="text-emerald-500 text-sm font-semibold ml-1">&#8595;</span>}
    </div>
  )
}

// ── Tool Renderers ───────────────────────────────────────────────

type ToolRenderer = (data: Record<string, unknown>, agent: string, onAction?: (text: string) => void, locale?: Locale) => ReactNode

// -- Deema tools --

function renderLeaveBalance(data: Record<string, unknown>, agent: string, _onAction?: (text: string) => void, locale: Locale = 'en'): ReactNode {
  const balances = (data.balances ?? data.items) as Array<Record<string, unknown>> | undefined
  if (Array.isArray(balances) && balances.length > 0) {
    return (
      <>
        {balances.map((b, i) => {
          const used = safeNum(b.used ?? b.used_days ?? b.taken)
          const total = safeNum(b.total ?? b.total_days ?? b.entitled ?? b.entitlement)
          const remaining = safeNum(b.remaining ?? b.remaining_days ?? b.balance ?? (total - used))
          const typeName = safeStr(b.type ?? b.leave_type ?? b.name ?? 'Leave')
          return (
            <div key={i}>
              <ResultRow label={typeName}>
                {remaining} <span className="text-[11px] text-ink-dim font-medium">/ {total} {t('days', locale)}</span>
              </ResultRow>
              <ProgressBar value={remaining} max={total} agent={agent} />
            </div>
          )
        })}
      </>
    )
  }
  const balance = safeNum(data.balance ?? data.remaining ?? data.available)
  const total = safeNum(data.total ?? data.entitled ?? data.entitlement ?? 30)
  return (
    <>
      <ResultRow label={t('Annual Leave Balance', locale)}>
        {balance} <span className="text-[11px] text-ink-dim font-medium">/ {total} {t('days', locale)}</span>
      </ResultRow>
      <ProgressBar value={balance} max={total} agent={agent} />
    </>
  )
}

function renderSubmitLeave(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const reqId = safeStr(data.request_id ?? data.id ?? data.leave_request_id ?? '')
  const startDate = safeStr(data.start_date ?? data.from ?? '')
  const endDate = safeStr(data.end_date ?? data.to ?? '')
  const days = safeNum(data.days ?? data.total_days ?? data.duration ?? 0)
  const leaveType = safeStr(data.leave_type ?? data.type ?? '')
  const statusVal = safeStr(data.status ?? data.approval_status ?? 'pending')
  const isApproved = statusVal.toLowerCase().includes('approved') || statusVal.toLowerCase().includes('auto')
  const period = startDate && endDate ? `${startDate} → ${endDate}${days ? ` · ${days} ${t('days', locale)}` : ''}` : ''

  return (
    <>
      {reqId && <KeyValue label={t('Request ID', locale)} value={reqId} />}
      {period && <KeyValue label={t('Period', locale)} value={period} />}
      {leaveType && <KeyValue label={t('Type', locale)} value={leaveType} />}
      <div className="flex justify-between items-center mb-2.5">
        <span className="text-xs text-ink-dim">{t('Status', locale)}</span>
        <span className={`text-[13px] font-semibold ${isApproved ? 'text-emerald-500' : 'text-amber-500'}`}>
          {isApproved ? '✓ ' : ''}{statusVal}
        </span>
      </div>
      {safeStr(data.message) && (
        <div className="text-xs text-ink-dim mt-1">{safeStr(data.message)}</div>
      )}
    </>
  )
}

function renderEmployeeProfile(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const fields: Array<[string, string]> = []
  if (data.name ?? data.full_name ?? data.employee_name) fields.push([t('Name', locale), safeStr(data.name ?? data.full_name ?? data.employee_name)])
  if (data.employee_number ?? data.employee_id ?? data.id) fields.push([t('Employee #', locale), safeStr(data.employee_number ?? data.employee_id ?? data.id)])
  if (data.department ?? data.department_name) fields.push([t('Department', locale), safeStr(data.department ?? data.department_name)])
  if (data.job_title ?? data.position ?? data.title) fields.push([t('Job Title', locale), safeStr(data.job_title ?? data.position ?? data.title)])
  if (data.hire_date ?? data.join_date ?? data.start_date) fields.push([t('Hire Date', locale), safeStr(data.hire_date ?? data.join_date ?? data.start_date)])
  if (data.email) fields.push([t('Email', locale), safeStr(data.email)])
  if (data.phone ?? data.mobile) fields.push([t('Phone', locale), safeStr(data.phone ?? data.mobile)])
  if (data.manager ?? data.manager_name) fields.push([t('Manager', locale), safeStr(data.manager ?? data.manager_name)])
  if (data.nationality) fields.push([t('Nationality', locale), safeStr(data.nationality)])
  return <>{fields.map(([k, v]) => <KeyValue key={k} label={k} value={v} />)}</>
}

function renderPayslip(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const fields: Array<[string, string]> = []
  if (data.employee_name) fields.push([t('Employee', locale), safeStr(data.employee_name)])
  if (data.period ?? data.month) fields.push([t('Period', locale), safeStr(data.period ?? data.month)])
  if (data.salary_sar !== undefined) fields.push([t('Basic Salary', locale), formatSAR(data.salary_sar)])
  if (data.basic_salary !== undefined) fields.push([t('Basic Salary', locale), formatSAR(data.basic_salary)])
  if (data.housing_allowance !== undefined) fields.push([t('Housing Allowance', locale), formatSAR(data.housing_allowance)])
  if (data.transport_allowance ?? data.transportation_allowance) fields.push([t('Transport Allowance', locale), formatSAR(data.transport_allowance ?? data.transportation_allowance)])
  if (data.allowances !== undefined) fields.push([t('Allowances', locale), formatSAR(data.allowances)])
  if (data.deductions !== undefined) fields.push([t('Deductions', locale), formatSAR(data.deductions)])
  if (data.gosi_deduction !== undefined) fields.push([t('GOSI', locale), formatSAR(data.gosi_deduction)])
  if (data.net_salary ?? data.net_pay ?? data.total) fields.push([t('Net Pay', locale), formatSAR(data.net_salary ?? data.net_pay ?? data.total)])
  if (data.note) fields.push([t('Note', locale), safeStr(data.note)])
  return <>{fields.map(([k, v]) => <KeyValue key={k} label={k} value={v} />)}</>
}

function renderPolicy(data: Record<string, unknown>): ReactNode {
  const title = safeStr(data.title ?? data.policy_title ?? data.name ?? '')
  const summary = safeStr(data.summary ?? data.content ?? data.text ?? data.policy_text ?? data.message ?? '')
  if (!title && !summary) {
    const fallback = safeStr(data.found !== undefined ? (data.policy_text ?? data.message ?? '') : '')
    if (fallback) return (
      <div className="max-h-[300px] overflow-y-auto">
        <div className="text-xs text-ink-dim leading-relaxed whitespace-pre-wrap">{fallback}</div>
      </div>
    )
    return null
  }
  return (
    <div className="max-h-[300px] overflow-y-auto">
      {title && <div className="text-sm font-semibold text-ink mb-2">{title}</div>}
      {summary && <div className="text-xs text-ink-dim leading-relaxed whitespace-pre-wrap">{summary}</div>}
    </div>
  )
}

function renderCreateTicket(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const ticketId = safeStr(data.ticket_id ?? data.id ?? data.escalation_id ?? '')
  const subject = safeStr(data.subject ?? data.title ?? data.reason ?? '')
  const statusVal = safeStr(data.status ?? 'open')
  const variant = statusVal.toLowerCase() === 'open' ? 'warning' : statusVal.toLowerCase() === 'resolved' ? 'success' : 'warning'
  return (
    <>
      {ticketId && <KeyValue label={t('Ticket ID', locale)} value={ticketId} />}
      {subject && <KeyValue label={t('Subject', locale)} value={subject} />}
      <div className="flex justify-between items-center">
        <span className="text-xs text-ink-dim">{t('Status', locale)}</span>
        <StatusBadge text={statusVal} variant={variant} />
      </div>
      {safeStr(data.message) && (
        <div className="text-xs text-ink-dim mt-2">{safeStr(data.message)}</div>
      )}
    </>
  )
}

function renderListTickets(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const tickets = (data.tickets ?? data.escalations ?? data.requests ?? data.items) as Array<Record<string, unknown>> | undefined
  if (!Array.isArray(tickets) || tickets.length === 0) {
    return <div className="text-xs text-ink-dim">{t('No tickets found', locale)}</div>
  }
  const rows = tickets.slice(0, 10).map((tk) => {
    const st = safeStr(tk.status ?? 'open').toLowerCase()
    const variant = st === 'resolved' || st === 'closed' ? 'success' : st === 'open' || st === 'pending' ? 'warning' : 'error'
    const details: Array<[string, string]> = []
    if (tk.ticket_id ?? tk.id) details.push([t('Ticket ID', locale), safeStr(tk.ticket_id ?? tk.id)])
    if (tk.subject ?? tk.title) details.push([t('Subject', locale), safeStr(tk.subject ?? tk.title)])
    if (tk.category ?? tk.type) details.push([t('Category', locale), safeStr(tk.category ?? tk.type)])
    if (tk.priority) details.push([t('Priority', locale), safeStr(tk.priority)])
    if (tk.created_at ?? tk.date) details.push([t('Created', locale), safeStr(tk.created_at ?? tk.date)])
    if (tk.assigned_to ?? tk.assignee) details.push([t('Assigned To', locale), safeStr(tk.assigned_to ?? tk.assignee)])
    if (tk.last_update ?? tk.updated_at) details.push([t('Last Update', locale), safeStr(tk.last_update ?? tk.updated_at)])
    if (tk.description ?? tk.message) details.push([t('Description', locale), safeStr(tk.description ?? tk.message).slice(0, 200)])
    return {
      cells: [safeStr(tk.subject ?? tk.title ?? tk.ticket_id ?? tk.id ?? t('Ticket', locale))],
      details,
      badge: { text: safeStr(tk.status ?? 'open'), variant: variant as 'success' | 'warning' | 'error' },
    }
  })
  return <InteractiveTable columns={[t('Ticket', locale), t('Status', locale)]} rows={rows} />
}

function renderLeaveRequests(data: Record<string, unknown>, _agent: string, onAction?: (text: string) => void, locale: Locale = 'en'): ReactNode {
  const requests = (data.requests ?? data.leave_requests ?? data.items) as Array<Record<string, unknown>> | undefined
  if (!Array.isArray(requests) || requests.length === 0) {
    return <div className="text-xs text-ink-dim">{t('No leave requests found', locale)}</div>
  }
  const rows = requests.slice(0, 10).map((r) => {
    const st = safeStr(r.status ?? 'pending').toLowerCase()
    const variant = st === 'approved' ? 'success' : st === 'rejected' || st === 'cancelled' ? 'error' : 'warning'
    const details: Array<[string, string]> = []
    if (r.leave_type ?? r.type) details.push([t('Type', locale), safeStr(r.leave_type ?? r.type)])
    if (r.start_date ?? r.from) details.push([t('Start', locale), safeStr(r.start_date ?? r.from)])
    if (r.end_date ?? r.to) details.push([t('End', locale), safeStr(r.end_date ?? r.to)])
    if (r.days ?? r.total_days ?? r.duration) details.push([t('Days', locale), `${safeNum(r.days ?? r.total_days ?? r.duration)}`])
    if (r.reason) details.push([t('Reason', locale), safeStr(r.reason).slice(0, 150)])
    if (r.approved_by ?? r.approver) details.push([t('Approved By', locale), safeStr(r.approved_by ?? r.approver)])
    if (r.request_id ?? r.id) details.push([t('Request ID', locale), safeStr(r.request_id ?? r.id)])
    const cancellable = st === 'pending' || st === 'approved' || st === 'pending_approval' || st === 'auto_approved'
    const reqId = safeStr(r.request_id ?? r.id ?? '')
    return {
      cells: [
        `${safeStr(r.leave_type ?? r.type ?? t('Leave', locale))} · ${safeStr(r.start_date ?? r.from ?? '')}`,
        `${safeNum(r.days ?? r.total_days ?? r.duration ?? 0)}d`,
      ],
      details,
      badge: { text: safeStr(r.status ?? 'pending'), variant: variant as 'success' | 'warning' | 'error' },
      action: cancellable && onAction && reqId ? {
        label: t('Cancel this request', locale),
        onClick: () => onAction(`Cancel my leave request ${reqId}`),
        variant: 'danger' as const,
      } : undefined,
    }
  })
  return <InteractiveTable columns={[t('Leave', locale), t('Status', locale)]} rows={rows} />
}

function renderDocuments(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const docs = (data.documents ?? data.items) as Array<Record<string, unknown>> | undefined
  if (!Array.isArray(docs) || docs.length === 0) {
    return <div className="text-xs text-ink-dim">{t('No documents found', locale)}</div>
  }
  const rows = docs.slice(0, 10).map((d) => {
    const details: Array<[string, string]> = []
    if (d.type ?? d.document_type) details.push([t('Type', locale), safeStr(d.type ?? d.document_type)])
    if (d.expiry_date ?? d.expires_at) details.push([t('Expiry Date', locale), safeStr(d.expiry_date ?? d.expires_at)])
    if (d.issued_date ?? d.issue_date) details.push([t('Issued', locale), safeStr(d.issued_date ?? d.issue_date)])
    if (d.issuer ?? d.issued_by) details.push([t('Issuer', locale), safeStr(d.issuer ?? d.issued_by)])
    if (d.document_number ?? d.number) details.push([t('Doc #', locale), safeStr(d.document_number ?? d.number)])
    if (d.status) details.push([t('Status', locale), safeStr(d.status)])
    const expiry = safeStr(d.expiry_date ?? d.expires_at ?? '')
    return {
      cells: [safeStr(d.name ?? d.title ?? d.document_name ?? t('Document', locale))],
      details,
      badge: expiry ? { text: `Exp: ${expiry}`, variant: 'warning' as const } : undefined,
    }
  })
  return <InteractiveTable columns={[t('Document', locale), t('Info', locale)]} rows={rows} />
}

// -- Mohammad tools --

function renderSearchCandidates(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const candidates = (data.candidates ?? data.results ?? data.items) as Array<Record<string, unknown>> | undefined
  const count = safeNum(data.count ?? data.total ?? (candidates ? candidates.length : 0))
  if (!Array.isArray(candidates) || candidates.length === 0) {
    return <BigNumber value={String(count)} unit={t('candidates found', locale)} />
  }
  const rows = candidates.slice(0, 10).map((c) => {
    const details: Array<[string, string]> = []
    if (c.email) details.push([t('Email', locale), safeStr(c.email)])
    if (c.phone ?? c.mobile) details.push([t('Phone', locale), safeStr(c.phone ?? c.mobile)])
    if (c.current_title ?? c.job_title ?? c.position) details.push([t('Current Title', locale), safeStr(c.current_title ?? c.job_title ?? c.position)])
    if (c.current_company ?? c.company) details.push([t('Company', locale), safeStr(c.current_company ?? c.company)])
    if (c.experience ?? c.years_experience) details.push([t('Experience', locale), `${safeStr(c.experience ?? c.years_experience)} years`])
    if (c.education ?? c.degree) details.push([t('Education', locale), safeStr(c.education ?? c.degree)])
    if (c.skills) details.push([t('Skills', locale), safeStr(c.skills)])
    if (c.match_score !== undefined) details.push([t('Match Score', locale), `${safeNum(c.match_score)}%`])
    if (c.nationality) details.push([t('Nationality', locale), safeStr(c.nationality)])
    if (c.applied_date ?? c.date) details.push([t('Applied', locale), safeStr(c.applied_date ?? c.date)])
    if (c.notes ?? c.summary) details.push([t('Notes', locale), safeStr(c.notes ?? c.summary).slice(0, 200)])
    const st = safeStr(c.status ?? c.stage ?? '').toLowerCase()
    const badge = st ? {
      text: safeStr(c.status ?? c.stage ?? ''),
      variant: (st === 'hired' || st === 'offered' ? 'success' : st === 'rejected' ? 'error' : 'warning') as 'success' | 'warning' | 'error',
    } : undefined
    return {
      cells: [safeStr(c.name ?? c.candidate_name ?? 'Candidate')],
      details,
      badge,
    }
  })
  return (
    <>
      <div className="text-[11px] text-ink-dim mb-2">{count} {t('candidates found', locale)}</div>
      <InteractiveTable columns={[t('Candidate', locale), t('Status', locale)]} rows={rows} />
    </>
  )
}

function renderJobPostings(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const postings = (data.postings ?? data.jobs ?? data.items) as Array<Record<string, unknown>> | undefined
  if (!Array.isArray(postings) || postings.length === 0) {
    return <div className="text-xs text-ink-dim">{t('No job postings found', locale)}</div>
  }
  const count = postings.length
  const rows = postings.slice(0, 10).map((p) => {
    const st = safeStr(p.status ?? 'open').toLowerCase()
    const variant = st === 'open' || st === 'active' ? 'success' : st === 'closed' || st === 'filled' ? 'error' : 'warning'
    const details: Array<[string, string]> = []
    if (p.department ?? p.department_name) details.push([t('Department', locale), safeStr(p.department ?? p.department_name)])
    if (p.salary ?? p.salary_range ?? p.min_salary !== undefined) {
      const salary = p.salary_range ? safeStr(p.salary_range) :
        p.min_salary !== undefined && p.max_salary !== undefined ? `${formatSAR(p.min_salary)} – ${formatSAR(p.max_salary)}` :
        p.salary ? formatSAR(p.salary) : ''
      if (salary) details.push([t('Salary', locale), salary])
    }
    if (p.location ?? p.city) details.push([t('Location', locale), safeStr(p.location ?? p.city)])
    if (p.applicants !== undefined || p.applicant_count !== undefined) details.push([t('Applicants', locale), String(safeNum(p.applicants ?? p.applicant_count))])
    if (p.posted_date ?? p.created_at ?? p.date) details.push([t('Posted', locale), safeStr(p.posted_date ?? p.created_at ?? p.date)])
    if (p.closing_date ?? p.deadline) details.push([t('Closes', locale), safeStr(p.closing_date ?? p.deadline)])
    if (p.employment_type ?? p.type ?? p.contract_type) details.push([t('Type', locale), safeStr(p.employment_type ?? p.type ?? p.contract_type)])
    if (p.experience ?? p.experience_required) details.push([t('Experience', locale), safeStr(p.experience ?? p.experience_required)])
    if (p.description) details.push([t('Description', locale), safeStr(p.description).slice(0, 200)])
    return {
      cells: [safeStr(p.title ?? p.job_title ?? 'Position'), safeStr(p.department ?? '')],
      details,
      badge: { text: safeStr(p.status ?? 'open'), variant: variant as 'success' | 'warning' | 'error' },
    }
  })
  return (
    <>
      <div className="text-[11px] text-ink-dim mb-2">{count} {t('Position', locale)}{count !== 1 && locale !== 'ar' ? 's' : ''}</div>
      <InteractiveTable columns={[t('Position', locale), t('Status', locale)]} rows={rows} />
    </>
  )
}

function renderJobOpening(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  return (
    <>
      {(data.title ?? data.job_title) && <KeyValue label={t('Job Title', locale)} value={safeStr(data.title ?? data.job_title)} />}
      {Boolean(data.department) && <KeyValue label={t('Department', locale)} value={safeStr(data.department)} />}
      {Boolean(data.status) && <KeyValue label={t('Status', locale)} value={safeStr(data.status)} />}
      {(data.applicants !== undefined || data.applicant_count !== undefined) && (
        <KeyValue label={t('Applicants', locale)} value={String(safeNum(data.applicants ?? data.applicant_count))} />
      )}
    </>
  )
}

function renderScheduleInterview(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  return (
    <>
      {(data.candidate ?? data.candidate_name) && <KeyValue label={t('Candidate', locale)} value={safeStr(data.candidate ?? data.candidate_name)} />}
      {(data.date ?? data.interview_date) && <KeyValue label={t('Date/Time', locale)} value={safeStr(data.date ?? data.interview_date)} />}
      {(data.interviewers ?? data.interviewer) && <KeyValue label={t('Interviewers', locale)} value={safeStr(data.interviewers ?? data.interviewer)} />}
      {Boolean(data.status) && <KeyValue label={t('Status', locale)} value={safeStr(data.status)} />}
    </>
  )
}

function renderPipelineSummary(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const stages = (data.stages ?? data.pipeline ?? data.items) as Array<Record<string, unknown>> | undefined
  if (Array.isArray(stages) && stages.length > 0) {
    const rows = stages.map((s) => {
      const details: Array<[string, string]> = []
      details.push([t('Candidates', locale), String(safeNum(s.count ?? s.candidates ?? 0))])
      if (s.avg_days !== undefined) details.push([t('Avg Days in Stage', locale), String(safeNum(s.avg_days))])
      if (s.conversion_rate !== undefined) details.push([t('Conversion Rate', locale), `${safeNum(s.conversion_rate).toFixed(1)}%`])
      return {
        cells: [safeStr(s.name ?? s.stage ?? ''), String(safeNum(s.count ?? s.candidates ?? 0))],
        details,
      }
    })
    return <InteractiveTable columns={[t('Stage', locale), t('Count', locale)]} rows={rows} />
  }
  const fields: Array<[string, string]> = []
  if (data.total_candidates !== undefined) fields.push([t('Total Candidates', locale), String(safeNum(data.total_candidates))])
  if (data.open_positions !== undefined) fields.push([t('Open Positions', locale), String(safeNum(data.open_positions))])
  if (data.interviews_scheduled !== undefined) fields.push([t('Interviews Scheduled', locale), String(safeNum(data.interviews_scheduled))])
  if (data.offers_pending !== undefined) fields.push([t('Offers Pending', locale), String(safeNum(data.offers_pending))])
  return <>{fields.map(([k, v]) => <KeyValue key={k} label={k} value={v} />)}</>
}

// -- Waleed tools --

function renderOnboardingStatus(data: Record<string, unknown>, agent: string, _onAction?: (text: string) => void, locale: Locale = 'en'): ReactNode {
  const done = safeNum(data.completed ?? data.tasks_done ?? data.completed_tasks ?? data.completed_steps ?? 0)
  const total = safeNum(data.total ?? data.total_tasks ?? data.task_count ?? data.total_steps ?? 0)
  const tasks = (data.tasks ?? data.steps ?? data.checklist ?? data.items) as Array<Record<string, unknown>> | undefined
  return (
    <>
      <ResultRow label={t('Onboarding Progress', locale)}>
        {done} <span className="text-[11px] text-ink-dim font-medium">/ {total} {t('tasks', locale)}</span>
      </ResultRow>
      {total > 0 && <ProgressBar value={done} max={total} agent={agent} />}
      {Array.isArray(tasks) && tasks.length > 0 && (
        <div className="space-y-1.5 mt-1">
          {tasks.slice(0, 6).map((t, i) => {
            const isDone = !!t.completed || t.status === 'done' || t.status === 'completed'
            return (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className={isDone ? 'text-emerald-500' : 'text-ink-faint'}>{isDone ? '✓' : '○'}</span>
                <span className={`${isDone ? 'text-ink-dim line-through' : 'text-ink'}`}>{safeStr(t.name ?? t.title ?? t.task ?? t.step ?? '')}</span>
              </div>
            )
          })}
        </div>
      )}
    </>
  )
}

function memberName(m: Record<string, unknown>): string {
  if (m.name) return safeStr(m.name)
  if (m.full_name) return safeStr(m.full_name)
  if (m.employee_name) return safeStr(m.employee_name)
  const first = safeStr(m.first_name ?? '')
  const last = safeStr(m.last_name ?? '')
  if (first || last) return `${first} ${last}`.trim()
  return 'Employee'
}

function renderTeamMembers(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const members = (data.members ?? data.team ?? data.employees ?? data.items ?? data.direct_reports) as Array<Record<string, unknown>> | undefined
  if (!Array.isArray(members) || members.length === 0) {
    return <div className="text-xs text-ink-dim">{t('No team members found', locale)}</div>
  }
  const rows = members.slice(0, 10).map((m) => {
    const details: Array<[string, string]> = []
    if (m.job_title ?? m.position ?? m.role) details.push([t('Title', locale), safeStr(m.job_title ?? m.position ?? m.role)])
    if (m.department ?? m.department_name) details.push([t('Department', locale), safeStr(m.department ?? m.department_name)])
    if (m.email) details.push([t('Email', locale), safeStr(m.email)])
    if (m.phone ?? m.mobile) details.push([t('Phone', locale), safeStr(m.phone ?? m.mobile)])
    if (m.employee_number ?? m.employee_id) details.push([t('Employee #', locale), safeStr(m.employee_number ?? m.employee_id)])
    if (m.nationality) details.push([t('Nationality', locale), safeStr(m.nationality)])
    if (m.hire_date ?? m.join_date) details.push([t('Joined', locale), safeStr(m.hire_date ?? m.join_date)])
    return {
      cells: [memberName(m)],
      details,
      badge: m.status ? { text: safeStr(m.status), variant: 'success' as const } : undefined,
    }
  })
  return <InteractiveTable columns={[t('Team Member', locale), t('Info', locale)]} rows={rows} />
}

function renderPendingApprovals(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const approvals = (data.approvals ?? data.pending_requests ?? data.requests ?? data.pending ?? data.items) as Array<Record<string, unknown>> | undefined
  if (!Array.isArray(approvals) || approvals.length === 0) {
    return <div className="text-xs text-ink-dim">{t('No pending approvals', locale)}</div>
  }
  const rows = approvals.slice(0, 10).map((a) => {
    const details: Array<[string, string]> = []
    if (a.leave_type ?? a.type) details.push([t('Leave Type', locale), safeStr(a.leave_type ?? a.type)])
    if (a.start_date ?? a.from) details.push([t('Start', locale), safeStr(a.start_date ?? a.from)])
    if (a.end_date ?? a.to) details.push([t('End', locale), safeStr(a.end_date ?? a.to)])
    if (a.days ?? a.total_days) details.push([t('Days', locale), `${safeNum(a.days ?? a.total_days)}`])
    if (a.reason) details.push([t('Reason', locale), safeStr(a.reason).slice(0, 150)])
    if (a.department ?? a.department_name) details.push([t('Department', locale), safeStr(a.department ?? a.department_name)])
    if (a.request_id ?? a.id) details.push([t('Request ID', locale), safeStr(a.request_id ?? a.id)])
    return {
      cells: [safeStr(a.employee_name ?? a.name ?? t('Employee', locale)), `${safeStr(a.leave_type ?? a.type ?? t('Leave', locale))} · ${safeNum(a.days ?? a.total_days ?? 0)}d`],
      details,
      badge: { text: t('Pending', locale), variant: 'warning' as const },
    }
  })
  return <InteractiveTable columns={[t('Employee', locale), t('Status', locale)]} rows={rows} />
}

/** Color palette for calendar bars */
const CALENDAR_COLORS = [
  'bg-[#6366f1]', 'bg-[#10b981]', 'bg-[#f59e0b]', 'bg-[#f43f5e]',
  'bg-[#3b82f6]', 'bg-[#8b5cf6]', 'bg-[#ec4899]', 'bg-[#14b8a6]',
]

function renderTeamCalendar(data: Record<string, unknown>): ReactNode {
  const entries = (data.on_leave ?? data.entries ?? data.calendar ?? data.leaves ?? data.items) as Array<Record<string, unknown>> | undefined
  const periodStart = safeStr(data.period_start ?? '')
  const periodEnd = safeStr(data.period_end ?? '')

  if (!Array.isArray(entries) || entries.length === 0) {
    return <div className="text-xs text-ink-dim">{safeStr(data.message ?? 'No upcoming leaves')}</div>
  }

  // Build date range for columns
  let startDate: Date
  let endDate: Date
  if (periodStart && periodEnd) {
    startDate = new Date(periodStart + 'T00:00:00')
    endDate = new Date(periodEnd + 'T00:00:00')
  } else {
    // Derive from entries
    const allDates = entries.flatMap((e) => {
      const s = safeStr(e.start_date ?? e.from ?? '')
      const en = safeStr(e.end_date ?? e.to ?? '')
      return [s, en].filter(Boolean)
    }).map((d) => new Date(d + 'T00:00:00'))
    startDate = new Date(Math.min(...allDates.map((d) => d.getTime())))
    endDate = new Date(Math.max(...allDates.map((d) => d.getTime())))
  }

  // Generate day columns
  const days: Date[] = []
  const cur = new Date(startDate)
  while (cur <= endDate && days.length <= 14) {
    days.push(new Date(cur))
    cur.setDate(cur.getDate() + 1)
  }

  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

  // Assign colors to employees
  const nameColorMap: Record<string, string> = {}
  let colorIdx = 0

  return (
    <div className="overflow-x-auto">
      {/* Period label */}
      {periodStart && periodEnd && (
        <div className="text-[10px] text-ink-faint mb-2">
          {monthNames[startDate.getMonth()]} {startDate.getDate()} – {monthNames[endDate.getMonth()]} {endDate.getDate()}, {endDate.getFullYear()}
        </div>
      )}
      {/* Calendar grid */}
      <div className="min-w-0">
        {/* Day headers */}
        <div className="flex items-end gap-0 mb-1" style={{ paddingLeft: '80px' }}>
          {days.map((d, i) => {
            const isWeekend = d.getDay() === 5 || d.getDay() === 6 // Fri-Sat
            return (
              <div key={i} className={`flex-1 min-w-[28px] text-center ${isWeekend ? 'opacity-40' : ''}`}>
                <div className="text-[9px] text-ink-faint">{dayNames[d.getDay()]}</div>
                <div className="text-[10px] font-semibold text-ink-dim">{d.getDate()}</div>
              </div>
            )
          })}
        </div>
        {/* Employee rows */}
        {entries.slice(0, 10).map((e, ei) => {
          const name = safeStr(e.employee_name ?? e.name ?? 'Employee')
          if (!nameColorMap[name]) {
            nameColorMap[name] = CALENDAR_COLORS[colorIdx % CALENDAR_COLORS.length]
            colorIdx++
          }
          const barColor = nameColorMap[name]
          const leaveStart = new Date(safeStr(e.start_date ?? e.from ?? '') + 'T00:00:00')
          const leaveEnd = new Date(safeStr(e.end_date ?? e.to ?? '') + 'T00:00:00')
          const leaveType = safeStr(e.leave_type ?? e.type ?? 'leave')

          return (
            <div key={ei} className="flex items-center gap-0 mb-0.5 group">
              <div className="w-[80px] shrink-0 text-[11px] text-ink truncate pr-2 font-medium" title={name}>
                {name.split(' ')[0]}
              </div>
              <div className="flex flex-1 gap-0">
                {days.map((d, di) => {
                  const ts = d.getTime()
                  const isInRange = ts >= leaveStart.getTime() && ts <= leaveEnd.getTime()
                  const isWeekend = d.getDay() === 5 || d.getDay() === 6
                  const isFirst = ts === leaveStart.getTime()
                  const isLast = ts === leaveEnd.getTime()
                  return (
                    <div
                      key={di}
                      className={`flex-1 min-w-[28px] h-6 ${isWeekend ? 'opacity-30' : ''}`}
                      title={isInRange ? `${name} — ${leaveType}` : ''}
                    >
                      {isInRange ? (
                        <div
                          className={`h-full ${barColor} opacity-80 ${isFirst ? 'rounded-l-md' : ''} ${isLast ? 'rounded-r-md' : ''}`}
                        />
                      ) : (
                        <div className="h-full bg-surface-3 opacity-30 rounded-sm" />
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
      {/* Legend */}
      <div className="flex flex-wrap gap-3 mt-2 pt-2 border-t border-border">
        {Object.entries(nameColorMap).map(([name, color]) => (
          <div key={name} className="flex items-center gap-1.5 text-[10px] text-ink-dim">
            <span className={`w-2.5 h-2.5 rounded-sm ${color} opacity-80`} />
            {name}
          </div>
        ))}
      </div>
    </div>
  )
}

// -- Ahmad tools --

function renderTurnoverRate(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const rate = safeNum(data.rate ?? data.turnover_rate ?? data.attrition_rate ?? 0)
  const trendVal = data.trend as string | undefined
  const trend = trendVal === 'up' || trendVal === 'increasing' ? 'up' : trendVal === 'down' || trendVal === 'decreasing' ? 'down' : null
  return (
    <>
      <BigNumber value={`${rate.toFixed(1)}%`} unit={t('turnover rate', locale)} trend={trend} />
      {Boolean(data.period) && <KeyValue label={t('Period', locale)} value={safeStr(data.period)} />}
      {Boolean(data.department) && <KeyValue label={t('Department', locale)} value={safeStr(data.department)} />}
      {data.voluntary !== undefined && <KeyValue label={t('Voluntary', locale)} value={`${safeNum(data.voluntary).toFixed(1)}%`} />}
      {data.involuntary !== undefined && <KeyValue label={t('Involuntary', locale)} value={`${safeNum(data.involuntary).toFixed(1)}%`} />}
    </>
  )
}

function renderSaudizationRate(data: Record<string, unknown>, agent: string, _onAction?: (text: string) => void, locale: Locale = 'en'): ReactNode {
  const rate = safeNum(data.rate ?? data.saudization_rate ?? data.percentage ?? 0)
  const target = safeNum(data.target ?? data.required ?? 100)
  const compliant = data.compliant !== undefined ? !!data.compliant : rate >= target
  return (
    <>
      <ResultRow label={t('Saudization Rate', locale)}>
        <span className={compliant ? 'text-emerald-500' : 'text-rose-500'}>{rate.toFixed(1)}%</span>
      </ResultRow>
      <ProgressBar value={rate} max={100} agent={agent} />
      {data.target !== undefined && <KeyValue label={t('Target', locale)} value={`${target}%`} />}
      <div className="flex justify-between items-center">
        <span className="text-xs text-ink-dim">{t('Compliance', locale)}</span>
        <StatusBadge text={compliant ? t('Compliant', locale) : t('Below Target', locale)} variant={compliant ? 'success' : 'error'} />
      </div>
    </>
  )
}

function renderSalaryDistribution(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const fields: Array<[string, string]> = []
  if (data.average !== undefined || data.avg_salary !== undefined) fields.push([t('Average', locale), formatSAR(data.average ?? data.avg_salary)])
  if (data.median !== undefined || data.median_salary !== undefined) fields.push([t('Median', locale), formatSAR(data.median ?? data.median_salary)])
  if (data.min !== undefined || data.min_salary !== undefined) fields.push([t('Minimum', locale), formatSAR(data.min ?? data.min_salary)])
  if (data.max !== undefined || data.max_salary !== undefined) fields.push([t('Maximum', locale), formatSAR(data.max ?? data.max_salary)])
  if (data.total_payroll !== undefined) fields.push([t('Total Payroll', locale), formatSAR(data.total_payroll)])
  if (data.department) fields.push([t('Department', locale), safeStr(data.department)])
  return <>{fields.map(([k, v]) => <KeyValue key={k} label={k} value={v} />)}</>
}

function renderHeadcount(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const total = safeNum(data.total ?? data.headcount ?? data.count ?? 0)
  const breakdown = (data.departments ?? data.by_department ?? data.breakdown) as Array<Record<string, unknown>> | undefined
  if (!Array.isArray(breakdown) || breakdown.length === 0) {
    return <BigNumber value={String(total)} unit={t('employees', locale)} />
  }
  const rows = breakdown.slice(0, 10).map((d) => {
    const details: Array<[string, string]> = []
    details.push([t('Headcount', locale), String(safeNum(d.count ?? d.headcount ?? d.total))])
    if (d.saudi_count !== undefined || d.saudi !== undefined) details.push([t('Saudi', locale), String(safeNum(d.saudi_count ?? d.saudi))])
    if (d.non_saudi_count !== undefined || d.non_saudi !== undefined) details.push([t('Non-Saudi', locale), String(safeNum(d.non_saudi_count ?? d.non_saudi))])
    if (d.saudization_rate !== undefined || d.saudization !== undefined) details.push([t('Saudization', locale), `${safeNum(d.saudization_rate ?? d.saudization).toFixed(1)}%`])
    if (d.budget !== undefined) details.push([t('Budget', locale), formatSAR(d.budget)])
    if (d.avg_salary !== undefined) details.push([t('Avg Salary', locale), formatSAR(d.avg_salary)])
    if (d.open_positions !== undefined) details.push([t('Open Positions', locale), String(safeNum(d.open_positions))])
    return {
      cells: [safeStr(d.name ?? d.department ?? d.dept ?? ''), String(safeNum(d.count ?? d.headcount ?? d.total))],
      details,
    }
  })
  return (
    <>
      <BigNumber value={String(total)} unit={t('employees', locale)} />
      <InteractiveTable columns={[t('Department', locale), t('Count', locale)]} rows={rows} />
    </>
  )
}

// -- Yara tools --

function renderDeployedAgents(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const agents = (data.agents ?? data.items ?? data.deployed) as Array<Record<string, unknown>> | undefined
  if (!Array.isArray(agents) || agents.length === 0) {
    return <div className="text-xs text-ink-dim">{t('No agents found', locale)}</div>
  }
  const rows = agents.slice(0, 10).map((a) => {
    const st = safeStr(a.status ?? 'active').toLowerCase()
    const variant = st === 'active' || st === 'running' ? 'success' : st === 'error' || st === 'failed' ? 'error' : 'warning'
    const details: Array<[string, string]> = []
    if (a.role ?? a.role_title ?? a.type) details.push([t('Role', locale), safeStr(a.role ?? a.role_title ?? a.type)])
    if (a.department ?? a.department_name) details.push([t('Department', locale), safeStr(a.department ?? a.department_name)])
    if (a.total_conversations !== undefined) details.push([t('Conversations', locale), String(safeNum(a.total_conversations))])
    if (a.resolution_rate !== undefined) details.push([t('Resolution Rate', locale), `${safeNum(a.resolution_rate).toFixed(1)}%`])
    if (a.avg_response_time !== undefined) details.push([t('Avg Response', locale), `${safeNum(a.avg_response_time).toFixed(1)}s`])
    if (a.created_at ?? a.deployed_at) details.push([t('Deployed', locale), safeStr(a.created_at ?? a.deployed_at)])
    if (a.last_active ?? a.last_used) details.push([t('Last Active', locale), safeStr(a.last_active ?? a.last_used)])
    return {
      cells: [safeStr(a.name ?? a.agent_name ?? '')],
      details,
      badge: { text: safeStr(a.status ?? 'active'), variant: variant as 'success' | 'warning' | 'error' },
    }
  })
  return <InteractiveTable columns={[t('Agent', locale), t('Status', locale)]} rows={rows} />
}

function renderAgentPerformance(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const fields: Array<[string, string]> = []
  if (data.agent_name ?? data.name) fields.push([t('Agent', locale), safeStr(data.agent_name ?? data.name)])
  if (data.total_conversations !== undefined) fields.push([t('Total Conversations', locale), String(safeNum(data.total_conversations))])
  if (data.avg_response_time !== undefined) fields.push([t('Avg Response Time', locale), `${safeNum(data.avg_response_time).toFixed(1)}s`])
  if (data.satisfaction_score !== undefined) fields.push([t('Satisfaction', locale), `${safeNum(data.satisfaction_score).toFixed(1)}%`])
  if (data.resolution_rate !== undefined) fields.push([t('Resolution Rate', locale), `${safeNum(data.resolution_rate).toFixed(1)}%`])
  if (data.escalation_rate !== undefined) fields.push([t('Escalation Rate', locale), `${safeNum(data.escalation_rate).toFixed(1)}%`])
  return <>{fields.map(([k, v]) => <KeyValue key={k} label={k} value={v} />)}</>
}

// -- Waleed HRBP tools --

function renderTeamDashboard(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const d = (data.dashboard ?? data) as Record<string, unknown>
  const hc = (d.headcount ?? {}) as Record<string, unknown>
  const prob = (d.probation_ending_soon ?? {}) as Record<string, unknown>
  const probEmps = (prob.employees ?? []) as Array<Record<string, unknown>>
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-surface-3 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-ink">{safeNum(hc.total)}</div>
          <div className="text-[10px] text-ink-dim">{t('Team Size', locale)}</div>
        </div>
        <div className="bg-surface-3 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-ink">{safeNum(hc.saudi)}</div>
          <div className="text-[10px] text-ink-dim">{t('Saudi', locale)}</div>
        </div>
        <div className="bg-surface-3 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-ink">{safeNum(hc.non_saudi)}</div>
          <div className="text-[10px] text-ink-dim">{t('Non-Saudi', locale)}</div>
        </div>
      </div>
      <div className="space-y-1.5">
        <KeyValue label={t('Saudization', locale)} value={`${safeNum(hc.saudization_pct).toFixed(0)}%`} />
        <KeyValue label={t('Pending Approvals', locale)} value={String(safeNum(d.pending_approvals))} />
        <KeyValue label={t('Active Onboarding', locale)} value={String(safeNum(d.active_onboarding))} />
        <KeyValue label={t('On Leave This Week', locale)} value={String(safeNum(d.team_leave_this_week))} />
        <KeyValue label={t('Expiring Documents', locale)} value={String(safeNum(d.expiring_documents))} />
      </div>
      {probEmps.length > 0 && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1.5">{t('Probation Ending Soon', locale)}</div>
          <CompactList items={probEmps.map((e) => ({
            label: safeStr(e.name),
            detail: `${safeNum(e.days_remaining)}d left`,
            badge: safeNum(e.days_remaining) <= 7
              ? { text: 'Urgent', variant: 'error' as const }
              : { text: `${safeNum(e.days_remaining)}d`, variant: 'warning' as const },
          }))} />
        </div>
      )}
    </div>
  )
}

function renderProbationTracker(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const onProb = (data.on_probation ?? []) as Array<Record<string, unknown>>
  const confirmDue = (data.confirmation_due ?? []) as Array<Record<string, unknown>>
  if (onProb.length === 0 && confirmDue.length === 0) {
    return <div className="text-xs text-ink-dim">{t('No employees currently on probation', locale)}</div>
  }
  const allItems = [
    ...confirmDue.map((e) => ({
      label: memberName(e),
      detail: safeStr(e.job_title),
      badge: { text: `${safeNum(e.days_overdue)}d overdue`, variant: 'error' as const },
    })),
    ...onProb.map((e) => ({
      label: memberName(e),
      detail: safeStr(e.job_title),
      badge: safeNum(e.days_remaining) <= 14
        ? { text: `${safeNum(e.days_remaining)}d left`, variant: 'warning' as const }
        : { text: `${safeNum(e.days_remaining)}d left`, variant: 'success' as const },
    })),
  ]
  return (
    <div>
      <div className="text-[10px] text-ink-faint mb-2">
        {safeNum(data.count)} employee{safeNum(data.count) !== 1 ? 's' : ''} on probation
      </div>
      <CompactList items={allItems} />
    </div>
  )
}

function renderTeamAttendance(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const summary = (data.summary ?? {}) as Record<string, unknown>
  const attendance = (data.attendance ?? []) as Array<Record<string, unknown>>
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-surface-3 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-ink">{safeNum(summary.avg_attendance_rate).toFixed(0)}%</div>
          <div className="text-[10px] text-ink-dim">{t('Avg Attendance', locale)}</div>
        </div>
        <div className="bg-surface-3 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-ink">{safeNum(summary.total_late_count)}</div>
          <div className="text-[10px] text-ink-dim">{t('Total Late', locale)}</div>
        </div>
      </div>
      {attendance.length > 0 && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1.5">{t('Per Employee', locale)}</div>
          <div className="space-y-1">
            {attendance.slice(0, 15).map((e, i) => (
              <div key={i} className="flex items-center justify-between text-xs px-1 py-1 rounded hover:bg-surface-3">
                <span className="text-ink font-medium truncate flex-1 min-w-0">{memberName(e)}</span>
                <div className="flex items-center gap-3 shrink-0 text-ink-dim">
                  <span title="Present">{safeNum(e.present_days)}d</span>
                  <span title="Absent" className={safeNum(e.absent_days) > 0 ? 'text-rose-500' : ''}>{safeNum(e.absent_days)}a</span>
                  <span title="Late" className={safeNum(e.late_count) > 0 ? 'text-amber-500' : ''}>{safeNum(e.late_count)}L</span>
                  <span title="Remote">{safeNum(e.remote_days)}r</span>
                  <span className={`font-semibold ${safeNum(e.attendance_rate) >= 90 ? 'text-emerald-500' : safeNum(e.attendance_rate) >= 75 ? 'text-amber-500' : 'text-rose-500'}`}>
                    {safeNum(e.attendance_rate).toFixed(0)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {data.date_range ? <div className="text-[10px] text-ink-faint">{safeStr(data.date_range)}</div> : null}
      {data.note ? <div className="text-[10px] text-ink-dim italic">{safeStr(data.note)}</div> : null}
    </div>
  )
}

function renderCompensationOverview(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const comp = (data.compensation ?? {}) as Record<string, unknown>
  const nat = (data.nationality_breakdown ?? {}) as Record<string, unknown>
  const dist = (data.salary_distribution ?? {}) as Record<string, unknown>
  const budget = (data.budget ?? {}) as Record<string, unknown>
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-surface-3 rounded-lg p-2 text-center">
          <div className="text-sm font-bold text-ink">{formatSAR(comp.average_salary_sar)}</div>
          <div className="text-[10px] text-ink-dim">{t('Avg Salary', locale)}</div>
        </div>
        <div className="bg-surface-3 rounded-lg p-2 text-center">
          <div className="text-sm font-bold text-ink">{formatSAR(comp.median_salary_sar)}</div>
          <div className="text-[10px] text-ink-dim">{t('Median Salary', locale)}</div>
        </div>
      </div>
      <div className="space-y-1.5">
        <KeyValue label={t('Min Salary', locale)} value={formatSAR(comp.min_salary_sar)} />
        <KeyValue label={t('Max Salary', locale)} value={formatSAR(comp.max_salary_sar)} />
        <KeyValue label={t('Monthly Cost', locale)} value={formatSAR(comp.total_monthly_cost_sar)} />
        <KeyValue label={t('Annual Cost', locale)} value={formatSAR(comp.total_annual_cost_sar)} />
      </div>
      {(safeNum(nat.saudi_count) > 0 || safeNum(nat.non_saudi_count) > 0) && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1.5">{t('By Nationality', locale)}</div>
          <div className="space-y-1.5">
            <KeyValue label={`${t('Saudi', locale)} (${safeNum(nat.saudi_count)})`} value={nat.saudi_avg_salary_sar ? formatSAR(nat.saudi_avg_salary_sar) : 'N/A'} />
            <KeyValue label={`${t('Non-Saudi', locale)} (${safeNum(nat.non_saudi_count)})`} value={nat.non_saudi_avg_salary_sar ? formatSAR(nat.non_saudi_avg_salary_sar) : 'N/A'} />
          </div>
        </div>
      )}
      {Object.keys(dist).length > 0 && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1.5">{t('Salary Distribution', locale)}</div>
          <CompactList items={[
            { label: t('Below 10K', locale), detail: String(safeNum(dist.below_10k)) },
            { label: t('10K – 15K', locale), detail: String(safeNum(dist['10k_15k'])) },
            { label: t('15K – 20K', locale), detail: String(safeNum(dist['15k_20k'])) },
            { label: t('20K – 30K', locale), detail: String(safeNum(dist['20k_30k'])) },
            { label: t('Above 30K', locale), detail: String(safeNum(dist.above_30k)) },
          ]} />
        </div>
      )}
      {Boolean(budget.status) && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-ink-dim">{t('Budget Utilization', locale)}</span>
          <StatusBadge
            text={`${safeNum(budget.utilization_pct).toFixed(0)}% — ${safeStr(budget.status).replace(/_/g, ' ')}`}
            variant={safeStr(budget.status) === 'over_budget' ? 'error' : 'success'}
          />
        </div>
      )}
    </div>
  )
}

function renderFlightRisk(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const summary = (data.summary ?? {}) as Record<string, unknown>
  const employees = (data.employees ?? []) as Array<Record<string, unknown>>
  if (employees.length === 0) {
    return <div className="text-xs text-ink-dim">{t('No flight risk data available', locale)}</div>
  }
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-rose-500/10 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-rose-500">{safeNum(summary.high_risk)}</div>
          <div className="text-[10px] text-ink-dim">{t('High Risk', locale)}</div>
        </div>
        <div className="bg-amber-500/10 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-amber-500">{safeNum(summary.medium_risk)}</div>
          <div className="text-[10px] text-ink-dim">{t('Medium Risk', locale)}</div>
        </div>
        <div className="bg-emerald-500/10 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-emerald-500">{safeNum(summary.low_risk)}</div>
          <div className="text-[10px] text-ink-dim">{t('Low Risk', locale)}</div>
        </div>
      </div>
      <div className="space-y-1.5">
        {employees.slice(0, 10).map((e, i) => {
          const risk = safeStr(e.risk_level)
          const variant = risk === 'high' ? 'error' as const : risk === 'medium' ? 'warning' as const : 'success' as const
          const factors = (e.risk_factors ?? []) as string[]
          const recs = (e.recommendations ?? []) as string[]
          const details: Array<[string, string]> = [
            [t('Risk Score', locale), `${safeNum(e.risk_score)}/100`],
            [t('Tenure', locale), `${safeNum(e.tenure_months)} ${t('months', locale)}`],
          ]
          if (factors.length > 0) details.push([t('Risk Factors', locale), factors.join(', ')])
          if (recs.length > 0) details.push([t('Recommendations', locale), recs.join(', ')])
          return (
            <ExpandableRow
              key={i}
              summary={{ label: memberName(e), subtitle: safeStr(e.job_title) }}
              details={details}
              badge={{ text: `${risk} risk`, variant }}
            />
          )
        })}
      </div>
    </div>
  )
}

function renderActionItems(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const items = (data.action_items ?? []) as Array<Record<string, unknown>>
  if (items.length === 0) {
    return <div className="text-xs text-ink-dim">{t('No pending action items — you\'re all caught up!', locale)}</div>
  }

  const categoryIcon: Record<string, string> = {
    leave_approval: '\u23F3',
    probation_review: '\u23F1\uFE0F',
    onboarding_overdue: '\u26A0\uFE0F',
    expiring_document: '\uD83D\uDCC4',
  }

  return (
    <div className="space-y-3">
      {/* Summary bar */}
      <div className="flex items-center gap-2">
        <div className="bg-surface-3 rounded-lg px-3 py-1.5 text-center">
          <span className="text-lg font-bold text-ink">{safeNum(data.total)}</span>
          <span className="text-[10px] text-ink-dim ml-1">{t('items', locale)}</span>
        </div>
        {safeNum(data.urgent) > 0 && (
          <div className="bg-rose-500/10 rounded-lg px-3 py-1.5 text-center">
            <span className="text-lg font-bold text-rose-500">{safeNum(data.urgent)}</span>
            <span className="text-[10px] text-rose-500 ml-1">{t('urgent', locale)}</span>
          </div>
        )}
      </div>
      {/* Items */}
      <div className="space-y-1.5">
        {items.slice(0, 15).map((item, i) => {
          const cat = safeStr(item.category)
          const details: Array<[string, string]> = []
          const det = (item.details ?? {}) as Record<string, unknown>
          if (det.employee_name) details.push([t('Employee', locale), safeStr(det.employee_name)])
          if (det.leave_type) details.push([t('Type', locale), safeStr(det.leave_type)])
          if (det.dates) details.push([t('Date', locale), safeStr(det.dates)])
          if (det.business_days) details.push([t('Days', locale), String(safeNum(det.business_days))])
          if (det.probation_end_date) details.push([t('End Date', locale), safeStr(det.probation_end_date)])
          if (det.days_remaining !== undefined) details.push([t('Days', locale), String(safeNum(det.days_remaining))])
          if (det.document_type) details.push([t('Document', locale), safeStr(det.document_type)])
          if (det.expires_at) details.push([t('Expiry Date', locale), safeStr(det.expires_at)])
          if (det.days_until_expiry !== undefined) details.push([t('Days', locale), String(safeNum(det.days_until_expiry))])
          if (det.step_name) details.push([t('Stage', locale), safeStr(det.step_name)])
          if (det.days_overdue !== undefined) details.push([t('Duration', locale), `${safeNum(det.days_overdue)} ${t('days', locale)}`])
          return (
            <ExpandableRow
              key={i}
              summary={{
                label: `${categoryIcon[cat] ?? '\uD83D\uDD14'} ${safeStr(item.title)}`,
                subtitle: cat.replace(/_/g, ' '),
              }}
              details={details}
              badge={{
                text: safeStr(item.priority),
                variant: safeStr(item.priority) === 'urgent' ? 'error' as const : 'warning' as const,
              }}
            />
          )
        })}
      </div>
    </div>
  )
}

function renderTeamCompliance(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const summary = (data.summary ?? data) as Record<string, unknown>
  const issues = (data.issues ?? data.compliance_issues ?? []) as Array<Record<string, unknown>>
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        {Boolean(summary.total_employees) && <KeyValue label={t('Team Size', locale)} value={String(safeNum(summary.total_employees))} />}
        {summary.compliant_count !== undefined && <KeyValue label={t('Compliant', locale)} value={String(safeNum(summary.compliant_count))} />}
        {summary.non_compliant_count !== undefined && <KeyValue label={t('Non-Compliant', locale)} value={String(safeNum(summary.non_compliant_count))} />}
        {summary.expiring_documents !== undefined && <KeyValue label={t('Expiring Documents', locale)} value={String(safeNum(summary.expiring_documents))} />}
        {summary.expired_documents !== undefined && <KeyValue label={t('Expired Documents', locale)} value={String(safeNum(summary.expired_documents))} />}
        {summary.missing_gosi !== undefined && <KeyValue label={t('Missing GOSI', locale)} value={String(safeNum(summary.missing_gosi))} />}
      </div>
      {issues.length > 0 && (
        <CompactList items={issues.slice(0, 10).map((item) => ({
          label: memberName(item),
          detail: safeStr(item.issue ?? item.type ?? item.category),
          badge: { text: safeStr(item.severity ?? 'issue'), variant: safeStr(item.severity) === 'critical' ? 'error' as const : 'warning' as const },
        }))} />
      )}
    </div>
  )
}

function renderPIPReport(data: Record<string, unknown>, agent: string, onAction?: (text: string) => void, locale: Locale = 'en'): ReactNode {
  const pip = (data.pip_draft ?? data) as Record<string, unknown>
  const emp = (pip.employee ?? {}) as Record<string, unknown>
  const mgr = (pip.manager ?? {}) as Record<string, unknown>
  const objectives = (pip.improvement_objectives ?? []) as Array<Record<string, unknown>>
  const timeline = (pip.timeline ?? []) as Array<Record<string, unknown>>
  const support = (pip.support_provided ?? []) as Array<Record<string, unknown>>
  const consequences = (pip.consequences ?? {}) as Record<string, unknown>
  const potentialActions = (consequences.potential_actions ?? []) as string[]
  const reviewDates = (pip.review_dates ?? []) as Array<Record<string, unknown>>

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="bg-surface-3 rounded-lg p-3">
        <div className="text-xs font-bold text-ink mb-2">{t('Performance Improvement Plan', locale)}</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
          {Boolean(emp.name) && (
            <><span className="text-ink-dim">{t('Employee', locale)}</span><span className="text-ink font-medium">{safeStr(emp.name)}</span></>
          )}
          {Boolean(emp.job_title) && (
            <><span className="text-ink-dim">{t('Role', locale)}</span><span className="text-ink font-medium">{safeStr(emp.job_title)}</span></>
          )}
          {Boolean(emp.department) && (
            <><span className="text-ink-dim">{t('Department', locale)}</span><span className="text-ink font-medium">{safeStr(emp.department)}</span></>
          )}
          {Boolean(mgr.name) && (
            <><span className="text-ink-dim">{t('Manager', locale)}</span><span className="text-ink font-medium">{safeStr(mgr.name)}</span></>
          )}
          {Boolean(pip.pip_start_date) && (
            <><span className="text-ink-dim">{t('Start Date', locale)}</span><span className="text-ink font-medium">{safeStr(pip.pip_start_date)}</span></>
          )}
          {Boolean(pip.pip_end_date) && (
            <><span className="text-ink-dim">{t('End Date', locale)}</span><span className="text-ink font-medium">{safeStr(pip.pip_end_date)}</span></>
          )}
          {Boolean(pip.pip_duration_days) && (
            <><span className="text-ink-dim">{t('Duration', locale)}</span><span className="text-ink font-medium">{safeNum(pip.pip_duration_days)} {t('days', locale)}</span></>
          )}
        </div>
      </div>

      {/* Performance Issues */}
      {Boolean(pip.performance_issues) && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1">{t('Performance Issues', locale)}</div>
          <div dir="auto" className="text-xs text-ink leading-relaxed bg-rose-500/5 rounded-lg p-2.5 border border-rose-500/10">
            {safeStr(pip.performance_issues)}
          </div>
        </div>
      )}

      {/* Improvement Objectives */}
      {objectives.length > 0 && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1.5">{t('Improvement Objectives', locale)}</div>
          <div className="space-y-2">
            {objectives.map((obj, i) => (
              <div key={i} className="bg-surface-3 rounded-lg p-2.5">
                <div className="text-[11px] font-semibold text-ink mb-1">{i + 1}. {safeStr(obj.area)}</div>
                <div className="text-[11px] text-ink-dim"><span className="font-medium">{t('Target:', locale)}</span> {safeStr(obj.target)}</div>
                <div className="text-[11px] text-ink-dim"><span className="font-medium">{t('Measured by:', locale)}</span> {safeStr(obj.measurement)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Timeline */}
      {timeline.length > 0 && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1.5">{t('90-Day Timeline', locale)}</div>
          <div className="space-y-2">
            {timeline.map((phase, i) => {
              const goals = (phase.goals ?? []) as string[]
              return (
                <div key={i} className="border-s-2 border-amber-400 ps-3">
                  <div className="text-[11px] font-semibold text-ink">{safeStr(phase.phase)}</div>
                  <div className="text-[10px] text-ink-dim mb-1">{t('Review:', locale)} {safeStr(phase.review_date)}</div>
                  <ul className="space-y-0.5">
                    {goals.map((g, j) => (
                      <li key={j} className="text-[11px] text-ink-dim flex items-start gap-1.5">
                        <span className="text-ink-faint mt-0.5">•</span>
                        <span>{g}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Support */}
      {support.length > 0 && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1.5">{t('Support Provided', locale)}</div>
          <div className="space-y-1">
            {support.map((s, i) => (
              <div key={i} className="flex items-start gap-2 text-[11px]">
                <span className="text-emerald-500 mt-0.5">✓</span>
                <span className="text-ink-dim">{safeStr(s.description)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Consequences */}
      {Boolean(consequences.description) && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1">{t('Consequences', locale)}</div>
          <div className="bg-amber-500/5 rounded-lg p-2.5 border border-amber-500/10">
            <div className="text-[11px] text-ink-dim mb-1.5">{safeStr(consequences.description)}</div>
            {potentialActions.length > 0 && (
              <ul className="space-y-0.5 mb-1.5">
                {potentialActions.map((a, i) => (
                  <li key={i} className="text-[11px] text-ink-dim flex items-start gap-1.5">
                    <span className="text-amber-500 mt-0.5">•</span><span>{a}</span>
                  </li>
                ))}
              </ul>
            )}
            {Boolean(consequences.legal_reference) && (
              <div className="text-[10px] text-ink-faint italic border-t border-amber-500/10 pt-1.5 mt-1.5">
                {safeStr(consequences.legal_reference)}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Review Dates */}
      {reviewDates.length > 0 && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1.5">{t('Review Schedule', locale)}</div>
          <div className="flex gap-2">
            {reviewDates.map((r, i) => (
              <div key={i} className="flex-1 bg-surface-3 rounded-lg p-2 text-center">
                <div className="text-[10px] text-ink-dim">{safeStr(r.type)}</div>
                <div className="text-[11px] font-semibold text-ink">{safeStr(r.date)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Note */}
      {Boolean(data.note) && (
        <div className="text-[10px] text-ink-faint italic">{safeStr(data.note)}</div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-2 pt-1 border-t border-border">
        <button
          type="button"
          onClick={() => onAction?.(`Send the PIP for ${safeStr(emp.name)} as an email to HR`)}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-[11px] font-semibold rounded-lg bg-[#1264a3] text-white hover:bg-[#0b4f8a] transition-colors cursor-pointer"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
            <polyline points="22,6 12,13 2,6"/>
          </svg>
          {t('Send as Email', locale)}
        </button>
        <button
          type="button"
          onClick={() => onAction?.(`Schedule a 1:1 meeting with ${safeStr(emp.name)} to discuss the PIP`)}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-[11px] font-semibold rounded-lg bg-surface-3 text-ink hover:bg-surface-2 border border-border transition-colors cursor-pointer"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
            <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
            <line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          {t('Schedule 1:1', locale)}
        </button>
      </div>
    </div>
  )
}

function renderOneOnOnePrep(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  const topics = (data.talking_points ?? data.topics ?? []) as Array<Record<string, unknown> | string>
  const emp = (data.employee ?? {}) as Record<string, unknown>
  return (
    <div className="space-y-2">
      {(data.employee_name || emp.name) && <KeyValue label={t('Employee', locale)} value={safeStr(data.employee_name ?? emp.name)} />}
      {(data.job_title || emp.job_title) && <KeyValue label={t('Role', locale)} value={safeStr(data.job_title ?? emp.job_title)} />}
      {Boolean(data.tenure) && <KeyValue label={t('Tenure', locale)} value={safeStr(data.tenure)} />}
      {Boolean(data.last_meeting) && <KeyValue label={t('Last 1:1', locale)} value={safeStr(data.last_meeting)} />}
      {topics.length > 0 && (
        <div>
          <div className="text-[10px] text-ink-faint uppercase font-semibold mb-1.5">{t('Talking Points', locale)}</div>
          <div className="space-y-1">
            {topics.map((t, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className="text-ink-dim shrink-0 mt-0.5">{i + 1}.</span>
                <span className="text-ink">{typeof t === 'string' ? t : safeStr((t as Record<string, unknown>).topic ?? (t as Record<string, unknown>).title ?? (t as Record<string, unknown>).text)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {data.recent_leaves !== undefined && <KeyValue label={t('Recent Leaves', locale)} value={String(safeNum(data.recent_leaves))} />}
      {data.pending_approvals !== undefined && <KeyValue label={t('Pending Approvals', locale)} value={String(safeNum(data.pending_approvals))} />}
    </div>
  )
}

function renderHeadcountRequest(data: Record<string, unknown>, locale: Locale = 'en'): ReactNode {
  return (
    <div className="space-y-1.5">
      {Boolean(data.request_id) && <KeyValue label={t('Request ID', locale)} value={safeStr(data.request_id)} />}
      {Boolean(data.job_title) && <KeyValue label={t('Role', locale)} value={safeStr(data.job_title)} />}
      {Boolean(data.department) && <KeyValue label={t('Department', locale)} value={safeStr(data.department)} />}
      {Boolean(data.status) && <StatusBadge text={safeStr(data.status)} variant={safeStr(data.status) === 'submitted' ? 'success' : 'warning'} />}
      {Boolean(data.message) && <div className="text-xs text-ink-dim mt-1">{safeStr(data.message)}</div>}
    </div>
  )
}

// -- Generic fallback renderer for unregistered tools --

function renderGenericData(data: Record<string, unknown>): ReactNode {
  // Try to render meaningful fields from any tool result
  if (data.message && typeof data.message === 'string') {
    return <div className="text-xs text-ink-dim leading-relaxed">{data.message}</div>
  }
  const fields: Array<[string, string]> = []
  for (const [key, val] of Object.entries(data)) {
    if (val === null || val === undefined || key === 'error') continue
    if (typeof val === 'object') continue
    const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
    fields.push([label, String(val)])
    if (fields.length >= 6) break
  }
  if (fields.length === 0) return null
  return <>{fields.map(([k, v]) => <KeyValue key={k} label={k} value={v} />)}</>
}

// ── Renderer registry ────────────────────────────────────────────

const toolRenderers: Record<string, ToolRenderer> = {
  // Deema
  get_leave_balance: (d, a, _o, l) => renderLeaveBalance(d, a, _o, l),
  view_vacation_balance: (d, a, _o, l) => renderLeaveBalance(d, a, _o, l),
  preview_leave_request: (d, _a, _o, l) => renderSubmitLeave(d, l),
  submit_leave_request: (d, _a, _o, l) => renderSubmitLeave(d, l),
  cancel_leave_request: (d, _a, _o, l) => renderSubmitLeave(d, l),
  get_leave_requests: (d, a, onAction, l) => renderLeaveRequests(d, a, onAction, l),
  list_my_leave_requests: (d, a, onAction, l) => renderLeaveRequests(d, a, onAction, l),
  get_employee_info: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  view_my_profile: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  view_payslip: (d, _a, _o, l) => renderPayslip(d, l),
  view_salary_info: (d, _a, _o, l) => renderPayslip(d, l),
  view_contract_info: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  search_policy: (d) => renderPolicy(d),
  escalate_to_human: (d, _a, _o, l) => renderCreateTicket(d, l),
  get_escalation_status: (d, _a, _o, l) => renderCreateTicket(d, l),
  list_my_escalations: (d, _a, _o, l) => renderListTickets(d, l),
  list_my_documents: (d, _a, _o, l) => renderDocuments(d, l),
  check_expiring_documents: (d, _a, _o, l) => renderDocuments(d, l),
  get_team_calendar: (d) => renderTeamCalendar(d),
  update_employee_info: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  // Mohammad
  search_candidates_web: (d, _a, _o, l) => renderSearchCandidates(d, l),
  view_candidates: (d, _a, _o, l) => renderSearchCandidates(d, l),
  get_job_postings: (d, _a, _o, l) => renderJobPostings(d, l),
  get_job_posting: (d, _a, _o, l) => renderJobOpening(d, l),
  create_job_posting: (d, _a, _o, l) => renderJobOpening(d, l),
  generate_job_description: (d) => renderPolicy(d),
  screen_candidate: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  update_candidate_stage: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  schedule_interview: (d, _a, _o, l) => renderScheduleInterview(d, l),
  get_pipeline_summary: (d, _a, _o, l) => renderPipelineSummary(d, l),
  add_candidate: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  search_employee: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  start_screening_interview: (d, _a, _o, l) => renderScheduleInterview(d, l),
  generate_assessment: (d) => renderPolicy(d),
  score_interview: (d) => renderPolicy(d),
  compare_candidates: (d, _a, _o, l) => renderSearchCandidates(d, l),
  generate_offer_recommendation: (d) => renderPolicy(d),
  // Waleed
  get_onboarding_checklist: renderOnboardingStatus,
  get_onboarding_dashboard: renderOnboardingStatus,
  get_overdue_onboarding_steps: renderOnboardingStatus,
  complete_onboarding_step: renderOnboardingStatus,
  assign_onboarding: renderOnboardingStatus,
  get_new_hire_info: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  view_team: (d, _a, _o, l) => renderTeamMembers(d, l),
  view_pending_approvals: (d, _a, _o, l) => renderPendingApprovals(d, l),
  approve_leave: (d, _a, _o, l) => renderSubmitLeave(d, l),
  reject_leave: (d, _a, _o, l) => renderSubmitLeave(d, l),
  get_team_leave_calendar: (d) => renderTeamCalendar(d),
  get_team_headcount: (d, _a, _o, l) => renderHeadcount(d, l),
  send_checkin: (d, _a, _o, l) => renderCreateTicket(d, l),
  // Waleed HRBP
  get_team_dashboard: (d, _a, _o, l) => renderTeamDashboard(d, l),
  get_probation_tracker: (d, _a, _o, l) => renderProbationTracker(d, l),
  get_team_attendance: (d, _a, _o, l) => renderTeamAttendance(d, l),
  get_compensation_overview: (d, _a, _o, l) => renderCompensationOverview(d, l),
  get_flight_risk: (d, _a, _o, l) => renderFlightRisk(d, l),
  prepare_one_on_one: (d, _a, _o, l) => renderOneOnOnePrep(d, l),
  get_team_compliance: (d, _a, _o, l) => renderTeamCompliance(d, l),
  request_headcount: (d, _a, _o, l) => renderHeadcountRequest(d, l),
  get_manager_action_items: (d, _a, _o, l) => renderActionItems(d, l),
  generate_pip: (d, a, onAction, l) => renderPIPReport(d, a, onAction, l),
  // Ahmad
  get_turnover_metrics: (d, _a, _o, l) => renderTurnoverRate(d, l),
  predict_attrition_risk: (d, _a, _o, l) => renderTurnoverRate(d, l),
  get_saudization_status: renderSaudizationRate,
  get_salary_distribution: (d, _a, _o, l) => renderSalaryDistribution(d, l),
  get_headcount_summary: (d, _a, _o, l) => renderHeadcount(d, l),
  get_workforce_overview: (d, _a, _o, l) => renderHeadcount(d, l),
  get_department_budget: (d, _a, _o, l) => renderSalaryDistribution(d, l),
  get_compliance_status: (d) => renderPolicy(d),
  get_recruitment_analytics: (d, _a, _o, l) => renderHeadcount(d, l),
  get_leave_analytics: (d, _a, _o, l) => renderHeadcount(d, l),
  get_attendance_analytics: (d, _a, _o, l) => renderHeadcount(d, l),
  get_onboarding_analytics: (d, _a, _o, l) => renderHeadcount(d, l),
  get_payroll_summary: (d, _a, _o, l) => renderSalaryDistribution(d, l),
  forecast_budget: (d, _a, _o, l) => renderSalaryDistribution(d, l),
  audit_gosi_compliance: (d) => renderPolicy(d),
  get_policy_acknowledgments: (d) => renderPolicy(d),
  generate_custom_report: (d) => renderPolicy(d),
  // Yara
  list_deployed_agents: (d, _a, _o, l) => renderDeployedAgents(d, l),
  get_agent_performance: (d, _a, _o, l) => renderAgentPerformance(d, l),
  get_department_overview: (d, _a, _o, l) => renderHeadcount(d, l),
  analyze_department: (d) => renderPolicy(d),
  recommend_workforce_mix: (d) => renderPolicy(d),
  simulate_scenario: (d) => renderPolicy(d),
  estimate_agent_roi: (d) => renderPolicy(d),
  design_agent: (d) => renderPolicy(d),
  create_agent: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  activate_agent: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  deactivate_agent: (d, _a, _o, l) => renderEmployeeProfile(d, l),
  update_agent_prompt: (d) => renderPolicy(d),
  detect_drift: (d) => renderPolicy(d),
  configure_agent_tools: (d) => renderPolicy(d),
  set_escalation_rules: (d) => renderPolicy(d),
  generate_governance_report: (d) => renderPolicy(d),
}

// ── Tool icon by domain ──────────────────────────────────────────
const TOOL_ICON: Record<string, string> = {
  // Deema
  get_leave_balance: '\u26A1',
  view_vacation_balance: '\u26A1',
  preview_leave_request: '\uD83D\uDCCB',
  submit_leave_request: '\uD83D\uDCCB',
  cancel_leave_request: '\u274C',
  get_leave_requests: '\uD83D\uDCCB',
  list_my_leave_requests: '\uD83D\uDCCB',
  get_employee_info: '\uD83D\uDC64',
  view_my_profile: '\uD83D\uDC64',
  view_payslip: '\uD83D\uDCB0',
  view_salary_info: '\uD83D\uDCB0',
  view_contract_info: '\uD83D\uDCDC',
  search_policy: '\uD83D\uDCD6',
  escalate_to_human: '\uD83C\uDFAB',
  get_escalation_status: '\uD83C\uDFAB',
  list_my_escalations: '\uD83C\uDFAB',
  list_my_documents: '\uD83D\uDCC2',
  check_expiring_documents: '\uD83D\uDCC2',
  get_team_calendar: '\uD83D\uDCC5',
  update_employee_info: '\u270F\uFE0F',
  // Mohammad
  get_job_postings: '\uD83D\uDCBC',
  get_job_posting: '\uD83D\uDCBC',
  create_job_posting: '\u2795',
  generate_job_description: '\uD83D\uDCDD',
  search_candidates_web: '\uD83D\uDD0D',
  view_candidates: '\uD83D\uDD0D',
  screen_candidate: '\uD83D\uDCCB',
  update_candidate_stage: '\u27A1\uFE0F',
  schedule_interview: '\uD83D\uDCC5',
  get_pipeline_summary: '\uD83D\uDCCA',
  add_candidate: '\u2795',
  search_employee: '\uD83D\uDD0D',
  start_screening_interview: '\uD83C\uDFA4',
  generate_assessment: '\uD83D\uDCCB',
  score_interview: '\u2B50',
  compare_candidates: '\u2696\uFE0F',
  // Waleed
  get_onboarding_checklist: '\u2705',
  get_onboarding_dashboard: '\u2705',
  get_overdue_onboarding_steps: '\u26A0\uFE0F',
  complete_onboarding_step: '\u2705',
  assign_onboarding: '\uD83D\uDCCB',
  get_new_hire_info: '\uD83D\uDC64',
  view_team: '\uD83D\uDC65',
  view_pending_approvals: '\u23F3',
  approve_leave: '\u2705',
  reject_leave: '\u274C',
  get_team_leave_calendar: '\uD83D\uDCC5',
  get_team_headcount: '\uD83D\uDC65',
  send_checkin: '\uD83D\uDCAC',
  get_team_dashboard: '\uD83C\uDFE0',
  get_probation_tracker: '\u23F1\uFE0F',
  get_team_attendance: '\uD83D\uDCCB',
  get_compensation_overview: '\uD83D\uDCB0',
  get_flight_risk: '\u26A0\uFE0F',
  prepare_one_on_one: '\uD83E\uDD1D',
  get_team_compliance: '\u2705',
  request_headcount: '\u2795',
  get_manager_action_items: '\uD83D\uDD14',
  generate_pip: '\uD83D\uDCDD',
  // Ahmad
  get_turnover_metrics: '\uD83D\uDCCA',
  predict_attrition_risk: '\uD83D\uDCCA',
  get_saudization_status: '\uD83C\uDDF8\uD83C\uDDE6',
  get_headcount_summary: '\uD83D\uDC65',
  get_workforce_overview: '\uD83D\uDC65',
  get_salary_distribution: '\uD83D\uDCB0',
  get_department_budget: '\uD83D\uDCB0',
  get_compliance_status: '\u2696\uFE0F',
  get_payroll_summary: '\uD83D\uDCB0',
  forecast_budget: '\uD83D\uDCC8',
  audit_gosi_compliance: '\u2696\uFE0F',
  generate_custom_report: '\uD83D\uDCDD',
  // Yara
  list_deployed_agents: '\uD83E\uDD16',
  get_agent_performance: '\uD83D\uDCCA',
  design_agent: '\uD83D\uDCD0',
  create_agent: '\u2795',
  activate_agent: '\u25B6\uFE0F',
  deactivate_agent: '\u23F8\uFE0F',
  detect_drift: '\u26A0\uFE0F',
  generate_governance_report: '\uD83D\uDCDD',
}

// ── Main ToolCard component ──────────────────────────────────────

export default function ToolCard({
  toolName,
  displayNameEn,
  displayNameAr,
  status,
  resultSummary,
  resultData,
  durationMs,
  agent,
  locale = 'en',
  onAction,
}: ToolCardProps) {
  const [expanded, setExpanded] = useState(true)
  const iconBg = AGENT_ICON_BG[agent] ?? AGENT_ICON_BG.deema
  const icon = TOOL_ICON[toolName] ?? '\u2699\uFE0F'
  const isAr = locale === 'ar'
  const displayName = isAr && displayNameAr ? displayNameAr : (displayNameEn || toolName)

  // Status badge rendering
  let statusBadge: ReactNode
  if (status === 'running') {
    statusBadge = (
      <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase bg-amber-500/15 text-amber-500">
        {t('Running...', locale)}
      </span>
    )
  } else if (status === 'error') {
    statusBadge = (
      <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase bg-rose-500/15 text-rose-500">
        {t('Error', locale)}
      </span>
    )
  } else {
    const durationText = durationMs != null ? ` \u00B7 ${formatDuration(durationMs)}` : ''
    statusBadge = (
      <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase bg-emerald-500/15 text-emerald-500">
        {t('Done', locale)}{durationText}
      </span>
    )
  }

  // Try to render rich content
  let richBody: ReactNode = null
  if (status !== 'running' && resultData && typeof resultData === 'object') {
    const renderer = toolRenderers[toolName]
    if (renderer) {
      try {
        richBody = renderer(resultData, agent, onAction, locale)
      } catch {
        richBody = null
      }
    }
    // Generic fallback for unregistered tools with data
    if (!richBody) {
      try {
        richBody = renderGenericData(resultData)
      } catch {
        richBody = null
      }
    }
  }

  // Fallback to text summary
  const showFallback = !richBody && status !== 'running' && resultSummary

  const hasDetails = status !== 'running' && (richBody || showFallback || (status === 'error' && resultSummary))
  const isClickable = hasDetails

  return (
    <div dir={isAr ? 'rtl' : 'ltr'} className="flex justify-start">
      <div className="max-w-[480px] w-full rounded-xl border border-border bg-surface overflow-hidden">
        {/* Tool header — clickable to expand/collapse */}
        <button
          type="button"
          onClick={isClickable ? () => setExpanded((v) => !v) : undefined}
          className={`w-full px-3.5 py-2.5 flex items-center gap-2.5 border-b border-border bg-surface-2 text-start ${
            isClickable ? 'cursor-pointer hover:bg-surface-3 transition-colors' : ''
          }`}
        >
          <div className={`w-7 h-7 rounded-[7px] flex items-center justify-center text-sm ${iconBg}`}>
            {icon}
          </div>
          <div className="flex-1 text-xs font-semibold text-ink">
            {displayName}
          </div>
          {statusBadge}
          {isClickable && (
            <svg
              width="12"
              height="12"
              viewBox="0 0 16 16"
              fill="currentColor"
              className={`text-ink-faint transition-transform ${expanded ? 'rotate-180' : ''}`}
            >
              <path d="M4.3 5.7a1 1 0 0 1 1.4 0L8 8.08l2.3-2.38a1 1 0 1 1 1.4 1.4l-3 3.1a1 1 0 0 1-1.4 0l-3-3.1a1 1 0 0 1 0-1.4z" />
            </svg>
          )}
        </button>

        {/* Tool body — expanded or running */}
        {(status === 'running' || expanded) && (
          <div className="px-3.5 py-3 max-h-[400px] overflow-y-auto">
            {status === 'running' && (
              <div className="flex items-center justify-center py-3 gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-ink-dim animate-blink" />
                <span className="w-1.5 h-1.5 rounded-full bg-ink-dim animate-blink [animation-delay:0.2s]" />
                <span className="w-1.5 h-1.5 rounded-full bg-ink-dim animate-blink [animation-delay:0.4s]" />
              </div>
            )}

            {expanded && richBody}

            {expanded && showFallback && (
              <div dir="auto" className="text-xs text-ink-dim leading-relaxed">
                {resultSummary}
              </div>
            )}

            {expanded && status === 'error' && resultSummary && (
              <div dir="auto" className="text-xs text-rose-500 leading-relaxed">
                {resultSummary}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
