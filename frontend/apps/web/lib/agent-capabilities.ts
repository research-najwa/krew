/**
 * Per-agent tool capabilities — used to show grouped action buttons
 * in the right-side tools panel and after the agent's first greeting.
 *
 * Each entry maps a user-friendly label (EN + AR) to a sample prompt
 * that gets sent to the agent when clicked.  Grouped by category.
 */

export interface ToolAction {
  label: string
  labelAr: string
  prompt: string
  promptAr: string
  icon: string
}

export interface ToolCategory {
  name: string
  nameAr: string
  icon: string
  actions: ToolAction[]
}

export const AGENT_CAPABILITIES: Record<string, ToolCategory[]> = {
  deema: [
    {
      name: 'Leave',
      nameAr: 'الإجازات',
      icon: '\uD83C\uDFD6\uFE0F',
      actions: [
        { label: 'Leave balance', labelAr: 'رصيد الإجازات', prompt: 'What is my leave balance?', promptAr: 'ما هو رصيد إجازاتي؟', icon: '\uD83D\uDCCA' },
        { label: 'Apply for leave', labelAr: 'تقديم إجازة', prompt: 'Apply for leave', promptAr: 'تقديم طلب إجازة', icon: '\uD83D\uDCDD' },
        { label: 'My leave requests', labelAr: 'طلبات إجازاتي', prompt: 'Show my leave requests', promptAr: 'اعرض طلبات إجازاتي', icon: '\uD83D\uDCCB' },
        { label: 'Team calendar', labelAr: 'تقويم الفريق', prompt: 'Who is on leave this week?', promptAr: 'من في إجازة هذا الأسبوع؟', icon: '\uD83D\uDCC5' },
      ],
    },
    {
      name: 'Profile & Pay',
      nameAr: 'الملف الشخصي والراتب',
      icon: '\uD83D\uDC64',
      actions: [
        { label: 'My profile', labelAr: 'ملفي الشخصي', prompt: 'Show my profile', promptAr: 'اعرض ملفي الشخصي', icon: '\uD83E\uDEAA' },
        { label: 'Salary info', labelAr: 'معلومات الراتب', prompt: "What's my salary breakdown?", promptAr: 'ما هو تفصيل راتبي؟', icon: '\uD83D\uDCB0' },
        { label: 'My payslip', labelAr: 'كشف الراتب', prompt: 'Show my latest payslip', promptAr: 'اعرض آخر كشف راتب', icon: '\uD83E\uDDFE' },
        { label: 'Contract info', labelAr: 'معلومات العقد', prompt: 'Show my contract details', promptAr: 'اعرض تفاصيل عقدي', icon: '\uD83D\uDCC4' },
      ],
    },
    {
      name: 'Documents',
      nameAr: 'المستندات',
      icon: '\uD83D\uDCC1',
      actions: [
        { label: 'My documents', labelAr: 'مستنداتي', prompt: 'List my documents', promptAr: 'اعرض مستنداتي', icon: '\uD83D\uDCC2' },
        { label: 'Expiring docs', labelAr: 'مستندات منتهية', prompt: 'Do I have any expiring documents?', promptAr: 'هل لدي مستندات تنتهي صلاحيتها؟', icon: '\u23F0' },
      ],
    },
    {
      name: 'Onboarding',
      nameAr: 'التهيئة',
      icon: '\uD83D\uDE80',
      actions: [
        { label: 'My onboarding', labelAr: 'تهيئتي', prompt: 'Show my onboarding checklist', promptAr: 'اعرض قائمة تهيئتي', icon: '\u2705' },
        { label: 'Onboarding dashboard', labelAr: 'لوحة التهيئة', prompt: 'Show onboarding dashboard', promptAr: 'اعرض لوحة التهيئة', icon: '\uD83D\uDCCA' },
        { label: 'Overdue steps', labelAr: 'خطوات متأخرة', prompt: 'Show overdue onboarding steps', promptAr: 'اعرض خطوات التهيئة المتأخرة', icon: '\u26A0\uFE0F' },
      ],
    },
    {
      name: 'Policies & Support',
      nameAr: 'السياسات والدعم',
      icon: '\uD83D\uDCD6',
      actions: [
        { label: 'Search policies', labelAr: 'بحث السياسات', prompt: 'What is the remote work policy?', promptAr: 'ما هي سياسة العمل عن بعد؟', icon: '\uD83D\uDD0D' },
        { label: 'My tickets', labelAr: 'تذاكري', prompt: 'Show my support tickets', promptAr: 'اعرض تذاكر الدعم', icon: '\uD83C\uDFAB' },
        { label: 'Escalate to HR', labelAr: 'تصعيد للموارد البشرية', prompt: 'Escalate to HR', promptAr: 'تصعيد للموارد البشرية', icon: '\uD83C\uDD98' },
      ],
    },
  ],

  mohammad: [
    {
      name: 'Job Postings',
      nameAr: 'الإعلانات الوظيفية',
      icon: '\uD83D\uDCBC',
      actions: [
        { label: 'Open positions', labelAr: 'الوظائف المفتوحة', prompt: 'Show all open job postings', promptAr: 'اعرض جميع الوظائف المفتوحة', icon: '\uD83D\uDCCB' },
        { label: 'Create posting', labelAr: 'إنشاء إعلان', prompt: 'Create a new job posting', promptAr: 'أنشئ إعلان وظيفي جديد', icon: '\u2795' },
        { label: 'Generate JD', labelAr: 'إنشاء وصف وظيفي', prompt: 'Generate a job description for Senior Engineer', promptAr: 'أنشئ وصف وظيفي لمهندس أول', icon: '\uD83D\uDCDD' },
      ],
    },
    {
      name: 'Candidates',
      nameAr: 'المرشحين',
      icon: '\uD83D\uDC65',
      actions: [
        { label: 'View candidates', labelAr: 'عرض المرشحين', prompt: 'Show all candidates', promptAr: 'اعرض جميع المرشحين', icon: '\uD83D\uDC64' },
        { label: 'Search candidates', labelAr: 'بحث المرشحين', prompt: 'Search for backend developer candidates', promptAr: 'ابحث عن مرشحين لمطور خلفي', icon: '\uD83D\uDD0D' },
        { label: 'Compare candidates', labelAr: 'مقارنة المرشحين', prompt: 'Compare top candidates', promptAr: 'قارن أفضل المرشحين', icon: '\u2696\uFE0F' },
      ],
    },
    {
      name: 'Pipeline',
      nameAr: 'خط التوظيف',
      icon: '\uD83D\uDCCA',
      actions: [
        { label: 'Pipeline summary', labelAr: 'ملخص خط التوظيف', prompt: 'Show the recruitment pipeline', promptAr: 'اعرض خط التوظيف', icon: '\uD83D\uDCC8' },
        { label: 'Schedule interview', labelAr: 'جدولة مقابلة', prompt: 'Schedule an interview', promptAr: 'جدول مقابلة', icon: '\uD83D\uDCC5' },
        { label: 'Offer recommendation', labelAr: 'توصية العرض', prompt: 'Generate offer recommendation', promptAr: 'أنشئ توصية عرض وظيفي', icon: '\uD83D\uDCA1' },
      ],
    },
  ],

  waleed: [
    {
      name: 'Team Overview',
      nameAr: 'نظرة عامة على الفريق',
      icon: '\uD83D\uDCCA',
      actions: [
        { label: 'Team dashboard', labelAr: 'لوحة الفريق', prompt: 'Show my team dashboard', promptAr: 'اعرض لوحة فريقي', icon: '\uD83C\uDFE0' },
        { label: 'My team', labelAr: 'فريقي', prompt: 'Show my team members', promptAr: 'اعرض أعضاء فريقي', icon: '\uD83D\uDC65' },
        { label: 'Team headcount', labelAr: 'عدد الفريق', prompt: 'What is my team headcount?', promptAr: 'كم عدد أعضاء فريقي؟', icon: '\uD83D\uDCC8' },
        { label: 'Action items', labelAr: 'المهام المطلوبة', prompt: 'Show my action items', promptAr: 'اعرض المهام المطلوبة مني', icon: '\uD83D\uDD14' },
      ],
    },
    {
      name: 'Leave & Calendar',
      nameAr: 'الإجازات والتقويم',
      icon: '\uD83D\uDCC5',
      actions: [
        { label: 'Pending approvals', labelAr: 'الموافقات المعلقة', prompt: 'Show pending leave approvals', promptAr: 'اعرض طلبات الإجازة المعلقة', icon: '\u23F3' },
        { label: 'Team leave calendar', labelAr: 'تقويم إجازات الفريق', prompt: 'Show team leave calendar', promptAr: 'اعرض تقويم إجازات الفريق', icon: '\uD83D\uDCC5' },
      ],
    },
    {
      name: 'People Insights',
      nameAr: 'رؤى الموظفين',
      icon: '\uD83E\uDDE0',
      actions: [
        { label: 'Flight risk', labelAr: 'مخاطر الاستقالة', prompt: 'Show flight risk analysis', promptAr: 'اعرض تحليل مخاطر الاستقالة', icon: '\u26A0\uFE0F' },
        { label: 'Probation tracker', labelAr: 'متابعة فترة التجربة', prompt: 'Show probation tracker', promptAr: 'اعرض متابعة فترة التجربة', icon: '\u23F1\uFE0F' },
        { label: 'Compensation overview', labelAr: 'نظرة على التعويضات', prompt: 'Show compensation overview', promptAr: 'اعرض نظرة عامة على التعويضات', icon: '\uD83D\uDCB0' },
        { label: 'Team compliance', labelAr: 'امتثال الفريق', prompt: 'Show team compliance status', promptAr: 'اعرض حالة امتثال الفريق', icon: '\u2705' },
        { label: 'Team attendance', labelAr: 'حضور الفريق', prompt: 'Show team attendance', promptAr: 'اعرض سجل حضور الفريق', icon: '\uD83D\uDCCB' },
      ],
    },
    {
      name: 'Manager Actions',
      nameAr: 'إجراءات المدير',
      icon: '\u26A1',
      actions: [
        { label: 'Prepare 1:1', labelAr: 'تحضير اجتماع فردي', prompt: 'Prepare a one-on-one meeting', promptAr: 'حضر اجتماع فردي', icon: '\uD83E\uDD1D' },
        { label: 'Request headcount', labelAr: 'طلب موظف جديد', prompt: 'Request a new headcount', promptAr: 'اطلب موظف جديد', icon: '\u2795' },
        { label: 'Generate PIP', labelAr: 'إنشاء خطة تحسين أداء', prompt: 'Generate a performance improvement plan', promptAr: 'أنشئ خطة تحسين أداء', icon: '\uD83D\uDCDD' },
      ],
    },
  ],

  yara: [
    {
      name: 'Workforce Planning',
      nameAr: 'تخطيط القوى العاملة',
      icon: '\uD83D\uDCD0',
      actions: [
        { label: 'Department overview', labelAr: 'نظرة عامة على القسم', prompt: 'Show department overview', promptAr: 'اعرض نظرة عامة على القسم', icon: '\uD83C\uDFE2' },
        { label: 'Analyze department', labelAr: 'تحليل القسم', prompt: 'Analyze the Engineering department', promptAr: 'حلل قسم الهندسة', icon: '\uD83D\uDD2C' },
        { label: 'Workforce mix', labelAr: 'مزيج القوى العاملة', prompt: 'Recommend workforce mix', promptAr: 'اقترح مزيج القوى العاملة', icon: '\u2696\uFE0F' },
        { label: 'Simulate scenario', labelAr: 'محاكاة سيناريو', prompt: 'Simulate adding 2 AI agents', promptAr: 'حاكي إضافة وكيلين ذكاء اصطناعي', icon: '\uD83E\uDDEA' },
        { label: 'Agent ROI', labelAr: 'عائد الاستثمار', prompt: 'Estimate ROI for an invoice processor agent', promptAr: 'قدّر عائد الاستثمار لوكيل معالجة الفواتير', icon: '\uD83D\uDCB0' },
      ],
    },
    {
      name: 'Agent Factory',
      nameAr: 'مصنع الوكلاء',
      icon: '\uD83C\uDFED',
      actions: [
        { label: 'Design agent', labelAr: 'تصميم وكيل', prompt: 'Design an AI agent for Finance', promptAr: 'صمم وكيل ذكاء اصطناعي للمالية', icon: '\u270F\uFE0F' },
        { label: 'Create agent', labelAr: 'إنشاء وكيل', prompt: 'Create the designed agent', promptAr: 'أنشئ الوكيل المصمم', icon: '\u2795' },
        { label: 'Activate agent', labelAr: 'تفعيل وكيل', prompt: 'Activate the new agent', promptAr: 'فعّل الوكيل الجديد', icon: '\u25B6\uFE0F' },
        { label: 'Configure tools', labelAr: 'إعداد الأدوات', prompt: 'Configure agent tools', promptAr: 'أعد إعداد أدوات الوكيل', icon: '\uD83D\uDD27' },
      ],
    },
    {
      name: 'Governance',
      nameAr: 'الحوكمة',
      icon: '\uD83D\uDEE1\uFE0F',
      actions: [
        { label: 'Deployed agents', labelAr: 'الوكلاء المنشورين', prompt: 'List all deployed agents', promptAr: 'اعرض جميع الوكلاء المنشورين', icon: '\uD83E\uDD16' },
        { label: 'Agent performance', labelAr: 'أداء الوكلاء', prompt: 'Show agent performance', promptAr: 'اعرض أداء الوكلاء', icon: '\uD83D\uDCC8' },
        { label: 'Detect drift', labelAr: 'كشف الانحراف', prompt: 'Check for agent drift', promptAr: 'تحقق من انحراف الوكلاء', icon: '\uD83D\uDD0D' },
        { label: 'Governance report', labelAr: 'تقرير الحوكمة', prompt: 'Generate governance report', promptAr: 'أنشئ تقرير حوكمة', icon: '\uD83D\uDCCB' },
      ],
    },
  ],

  ahmad: [
    {
      name: 'Analytics',
      nameAr: 'التحليلات',
      icon: '\uD83D\uDCCA',
      actions: [
        { label: 'Headcount', labelAr: 'عدد الموظفين', prompt: 'Show headcount summary', promptAr: 'اعرض ملخص عدد الموظفين', icon: '\uD83D\uDC65' },
        { label: 'Turnover', labelAr: 'معدل الدوران', prompt: 'Show turnover metrics', promptAr: 'اعرض مقاييس الدوران الوظيفي', icon: '\uD83D\uDD04' },
        { label: 'Salary distribution', labelAr: 'توزيع الرواتب', prompt: 'Show salary distribution', promptAr: 'اعرض توزيع الرواتب', icon: '\uD83D\uDCB0' },
        { label: 'Workforce overview', labelAr: 'نظرة عامة على القوى العاملة', prompt: 'Give me a workforce overview', promptAr: 'أعطني نظرة عامة على القوى العاملة', icon: '\uD83C\uDFE2' },
        { label: 'Department budget', labelAr: 'ميزانية القسم', prompt: 'Show department budget', promptAr: 'اعرض ميزانية القسم', icon: '\uD83D\uDCB5' },
      ],
    },
    {
      name: 'Compliance',
      nameAr: 'الامتثال',
      icon: '\u2705',
      actions: [
        { label: 'Saudization', labelAr: 'السعودة', prompt: 'Show Saudization status', promptAr: 'اعرض حالة السعودة', icon: '\uD83C\uDDF8\uD83C\uDDE6' },
        { label: 'Compliance status', labelAr: 'حالة الامتثال', prompt: 'Show compliance status', promptAr: 'اعرض حالة الامتثال', icon: '\uD83D\uDCCB' },
        { label: 'GOSI audit', labelAr: 'تدقيق التأمينات', prompt: 'Audit GOSI compliance', promptAr: 'دقق امتثال التأمينات الاجتماعية', icon: '\uD83D\uDD0D' },
        { label: 'Policy acknowledgments', labelAr: 'إقرارات السياسات', prompt: 'Show policy acknowledgments', promptAr: 'اعرض إقرارات السياسات', icon: '\uD83D\uDCD6' },
      ],
    },
    {
      name: 'Operations',
      nameAr: 'العمليات',
      icon: '\u2699\uFE0F',
      actions: [
        { label: 'Leave analytics', labelAr: 'تحليلات الإجازات', prompt: 'Show leave analytics', promptAr: 'اعرض تحليلات الإجازات', icon: '\uD83C\uDFD6\uFE0F' },
        { label: 'Payroll summary', labelAr: 'ملخص الرواتب', prompt: 'Show payroll summary', promptAr: 'اعرض ملخص الرواتب', icon: '\uD83E\uDDFE' },
        { label: 'Recruitment analytics', labelAr: 'تحليلات التوظيف', prompt: 'Show recruitment analytics', promptAr: 'اعرض تحليلات التوظيف', icon: '\uD83D\uDCC8' },
      ],
    },
    {
      name: 'Intelligence',
      nameAr: 'الذكاء',
      icon: '\uD83E\uDDE0',
      actions: [
        { label: 'Attrition risk', labelAr: 'مخاطر التسرب', prompt: 'Predict attrition risk', promptAr: 'توقع مخاطر تسرب الموظفين', icon: '\u26A0\uFE0F' },
        { label: 'Budget forecast', labelAr: 'توقعات الميزانية', prompt: 'Forecast next quarter budget', promptAr: 'توقع ميزانية الربع القادم', icon: '\uD83D\uDD2E' },
        { label: 'Custom report', labelAr: 'تقرير مخصص', prompt: 'Generate a custom HR report', promptAr: 'أنشئ تقرير موارد بشرية مخصص', icon: '\uD83D\uDCDD' },
      ],
    },
  ],
}
