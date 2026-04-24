'use client'

import { useState, type ReactNode } from 'react'

// ── Form field definitions ──────────────────────────────────────

export interface FormFieldOption {
  value: string
  label: string
}

export interface FormField {
  name: string
  label: string
  type: 'select' | 'date' | 'text' | 'textarea'
  options?: FormFieldOption[]
  required?: boolean
  placeholder?: string
}

export interface FormSchema {
  title: string
  icon: string
  fields: FormField[]
}

export interface FormCardProps {
  schema: FormSchema
  prefilled?: Record<string, string>
  agent: string
  onConfirm: (data: Record<string, string>) => void
  onReset: () => void
}

// ── Agent colors (same as ToolCard) ─────────────────────────────

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

const AGENT_BTN: Record<string, string> = {
  deema: 'bg-[#6366f1] hover:bg-[#5558e6]',
  mohammad: 'bg-[#10b981] hover:bg-[#0ea572]',
  waleed: 'bg-[#f59e0b] hover:bg-[#e5900a]',
  yara: 'bg-[#f43f5e] hover:bg-[#e03553]',
  ahmad: 'bg-[#3b82f6] hover:bg-[#2b6fe0]',
}

// ── Form schemas registry ───────────────────────────────────────

const LEAVE_TYPES: FormFieldOption[] = [
  { value: 'annual', label: 'Annual Leave' },
  { value: 'sick', label: 'Sick Leave' },
  { value: 'emergency', label: 'Emergency Leave' },
  { value: 'maternity', label: 'Maternity Leave' },
  { value: 'paternity', label: 'Paternity Leave' },
  { value: 'hajj', label: 'Hajj Leave' },
  { value: 'bereavement', label: 'Bereavement Leave' },
  { value: 'unpaid', label: 'Unpaid Leave' },
]

export const FORM_SCHEMAS: Record<string, FormSchema> = {
  submit_leave_request: {
    title: 'Apply for Leave',
    icon: '📋',
    fields: [
      { name: 'leave_type', label: 'Leave Type', type: 'select', options: LEAVE_TYPES, required: true },
      { name: 'start_date', label: 'Start Date', type: 'date', required: true },
      { name: 'end_date', label: 'End Date', type: 'date', required: true },
      { name: 'reason', label: 'Reason (optional)', type: 'textarea', placeholder: 'Enter reason for leave...' },
    ],
  },
  escalate_to_human: {
    title: 'Escalate to HR',
    icon: '🎫',
    fields: [
      { name: 'subject', label: 'Subject', type: 'text', required: true, placeholder: 'Brief description...' },
      { name: 'category', label: 'Category', type: 'select', options: [
        { value: 'payroll', label: 'Payroll' },
        { value: 'benefits', label: 'Benefits' },
        { value: 'policy', label: 'Policy Question' },
        { value: 'complaint', label: 'Complaint' },
        { value: 'other', label: 'Other' },
      ], required: true },
      { name: 'description', label: 'Details', type: 'textarea', required: true, placeholder: 'Describe your issue...' },
    ],
  },
  create_job_posting: {
    title: 'Create Job Posting',
    icon: '💼',
    fields: [
      { name: 'title', label: 'Job Title', type: 'text', required: true, placeholder: 'e.g. Senior Software Engineer' },
      { name: 'department', label: 'Department', type: 'text', required: true, placeholder: 'e.g. Engineering' },
      { name: 'employment_type', label: 'Employment Type', type: 'select', options: [
        { value: 'full_time', label: 'Full-time' },
        { value: 'part_time', label: 'Part-time' },
        { value: 'contract', label: 'Contract' },
      ], required: true },
      { name: 'experience', label: 'Experience Required', type: 'text', placeholder: 'e.g. 3-5 years' },
      { name: 'salary_range', label: 'Salary Range (SAR)', type: 'text', placeholder: 'e.g. 15,000 - 25,000' },
      { name: 'description', label: 'Job Description', type: 'textarea', required: true, placeholder: 'Describe the role...' },
    ],
  },
}

// ── Map suggestion text to form action ──────────────────────────

const SUGGESTION_TO_FORM: Record<string, string> = {
  'Submit annual leave request': 'submit_leave_request',
  'Submit leave request': 'submit_leave_request',
  'Apply for annual leave': 'submit_leave_request',
  'Apply for leave': 'submit_leave_request',
  'Request annual leave': 'submit_leave_request',
  'Request leave': 'submit_leave_request',
  'Apply for sick leave': 'submit_leave_request',
  'Apply for emergency leave': 'submit_leave_request',
  'Escalate to HR': 'escalate_to_human',
  'Create a ticket': 'escalate_to_human',
  'Create new job posting': 'create_job_posting',
  'Create a new job posting': 'create_job_posting',
  'Post a new job': 'create_job_posting',
}

/** Check if a suggestion text should open a form instead of sending a message */
export function getFormAction(suggestion: string): string | null {
  // Exact match
  if (SUGGESTION_TO_FORM[suggestion]) return SUGGESTION_TO_FORM[suggestion]
  // Case-insensitive match
  const lower = suggestion.toLowerCase()
  for (const [key, action] of Object.entries(SUGGESTION_TO_FORM)) {
    if (key.toLowerCase() === lower) return action
  }
  // Fuzzy: contains "submit" + "leave" or "apply" + "leave"
  if ((lower.includes('submit') || lower.includes('apply') || lower.includes('request')) && lower.includes('leave')) {
    return 'submit_leave_request'
  }
  if ((lower.includes('escalate') || lower.includes('ticket')) && (lower.includes('hr') || lower.includes('human'))) {
    return 'escalate_to_human'
  }
  if (lower.includes('create') && (lower.includes('job') || lower.includes('posting'))) {
    return 'create_job_posting'
  }
  return null
}

/** Build a natural language message from form data for the agent */
export function buildFormMessage(formAction: string, data: Record<string, string>): string {
  switch (formAction) {
    case 'submit_leave_request': {
      const type = data.leave_type ? data.leave_type.replace('_', ' ') : 'annual'
      let msg = `CONFIRMED: Submit my ${type} leave from ${data.start_date} to ${data.end_date}`
      if (data.reason) msg += `. Reason: ${data.reason}`
      return msg
    }
    case 'escalate_to_human': {
      let msg = `Please escalate to HR. Subject: ${data.subject}`
      if (data.category) msg += `. Category: ${data.category}`
      if (data.description) msg += `. Details: ${data.description}`
      return msg
    }
    case 'create_job_posting': {
      let msg = `Create a job posting for ${data.title} in ${data.department}`
      if (data.employment_type) msg += `, ${data.employment_type.replace('_', ' ')}`
      if (data.salary_range) msg += `, salary range: SAR ${data.salary_range}`
      if (data.experience) msg += `, experience: ${data.experience}`
      if (data.description) msg += `. Description: ${data.description}`
      return msg
    }
    default:
      return Object.entries(data).map(([k, v]) => `${k}: ${v}`).join(', ')
  }
}

// ── Field renderers ─────────────────────────────────────────────

function FieldInput({ field, value, onChange }: {
  field: FormField
  value: string
  onChange: (val: string) => void
}) {
  const baseInput = 'w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:outline-none focus:ring-1 focus:ring-ink-dim transition-colors'

  switch (field.type) {
    case 'select':
      return (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`${baseInput} cursor-pointer`}
        >
          <option value="">Select {field.label.toLowerCase()}...</option>
          {field.options?.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      )
    case 'date':
      return (
        <input
          type="date"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={baseInput}
        />
      )
    case 'textarea':
      return (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={3}
          className={`${baseInput} resize-none`}
        />
      )
    default:
      return (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          className={baseInput}
        />
      )
  }
}

// ── Main FormCard component ─────────────────────────────────────

export default function FormCard({ schema, prefilled, agent, onConfirm, onReset }: FormCardProps) {
  const initial: Record<string, string> = {}
  for (const f of schema.fields) {
    initial[f.name] = prefilled?.[f.name] ?? ''
  }
  const [formData, setFormData] = useState(initial)
  const [submitted, setSubmitted] = useState(false)

  const iconBg = AGENT_ICON_BG[agent] ?? AGENT_ICON_BG.deema
  const btnColor = AGENT_BTN[agent] ?? AGENT_BTN.deema

  function handleFieldChange(name: string, value: string) {
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  function handleConfirm() {
    // Check required fields
    for (const f of schema.fields) {
      if (f.required && !formData[f.name]?.trim()) return
    }
    setSubmitted(true)
    onConfirm(formData)
  }

  function handleReset() {
    setFormData(initial)
    onReset()
  }

  // After submission, show a minimal confirmation state
  if (submitted) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[480px] w-full rounded-xl border border-border bg-surface overflow-hidden">
          <div className="px-3.5 py-3 flex items-center gap-2.5 bg-surface-2">
            <div className={`w-7 h-7 rounded-[7px] flex items-center justify-center text-sm ${iconBg}`}>
              {schema.icon}
            </div>
            <div className="flex-1 text-xs font-semibold text-ink">{schema.title}</div>
            <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase bg-emerald-500/15 text-emerald-500">
              Submitted
            </span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[480px] w-full rounded-xl border border-border bg-surface overflow-hidden">
        {/* Header */}
        <div className="px-3.5 py-2.5 flex items-center gap-2.5 border-b border-border bg-surface-2">
          <div className={`w-7 h-7 rounded-[7px] flex items-center justify-center text-sm ${iconBg}`}>
            {schema.icon}
          </div>
          <div className="flex-1 text-xs font-semibold text-ink">{schema.title}</div>
        </div>

        {/* Form fields */}
        <div className="px-3.5 py-3 space-y-3">
          {schema.fields.map((field) => (
            <div key={field.name}>
              <label className="block text-[11px] font-semibold text-ink-dim mb-1">
                {field.label}
                {field.required && <span className="text-rose-400 ml-0.5">*</span>}
              </label>
              <FieldInput
                field={field}
                value={formData[field.name] ?? ''}
                onChange={(val) => handleFieldChange(field.name, val)}
              />
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="px-3.5 pb-3 flex gap-2">
          <button
            type="button"
            onClick={handleConfirm}
            className={`flex-1 px-4 py-2 text-xs font-semibold text-white rounded-lg transition-colors cursor-pointer ${btnColor}`}
          >
            Confirm
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="px-4 py-2 text-xs font-semibold text-ink-dim rounded-lg border border-border hover:bg-surface-3 transition-colors cursor-pointer"
          >
            Reset
          </button>
        </div>
      </div>
    </div>
  )
}
