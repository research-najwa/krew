/**
 * i18n.js — Arabic/English string map with RTL toggle.
 */

const strings = {
  // Navigation
  'nav.dashboard': { en: 'Dashboard', ar: 'لوحة المعلومات' },
  'nav.employees': { en: 'Employees', ar: 'الموظفون' },
  'nav.departments': { en: 'Departments', ar: 'الأقسام' },
  'nav.leaves': { en: 'Leave Requests', ar: 'طلبات الإجازات' },
  'nav.reports': { en: 'Reports', ar: 'التقارير' },
  'nav.settings': { en: 'Settings', ar: 'الإعدادات' },

  // Login
  'login.title': { en: 'Admin Login', ar: 'تسجيل دخول المشرف' },
  'login.email': { en: 'Email', ar: 'البريد الإلكتروني' },
  'login.password': { en: 'Password', ar: 'كلمة المرور' },
  'login.submit': { en: 'Sign In', ar: 'تسجيل الدخول' },
  'login.error': { en: 'Invalid email or password', ar: 'بريد إلكتروني أو كلمة مرور غير صحيحة' },
  'login.subtitle': { en: 'Krew HR Platform', ar: 'منصة كرو للموارد البشرية' },

  // Dashboard
  'dash.total_employees': { en: 'Total Employees', ar: 'إجمالي الموظفين' },
  'dash.saudization': { en: 'Saudization %', ar: 'نسبة السعودة' },
  'dash.pending_leaves': { en: 'Pending Leaves', ar: 'إجازات معلقة' },
  'dash.open_tickets': { en: 'Open Tickets', ar: 'تذاكر مفتوحة' },
  'dash.active': { en: 'Active', ar: 'نشط' },
  'dash.of_workforce': { en: 'of workforce', ar: 'من القوى العاملة' },
  'dash.awaiting_review': { en: 'Awaiting review', ar: 'بانتظار المراجعة' },
  'dash.need_attention': { en: 'Need attention', ar: 'تحتاج اهتمام' },
  'dash.dept_headcount': { en: 'Department Headcount', ar: 'عدد موظفي الأقسام' },

  // Employees
  'emp.title': { en: 'Employees', ar: 'الموظفون' },
  'emp.search': { en: 'Search by name or ID...', ar: 'بحث بالاسم أو الرقم...' },
  'emp.create': { en: 'New Employee', ar: 'موظف جديد' },
  'emp.import': { en: 'Import CSV', ar: 'استيراد CSV' },
  'emp.export': { en: 'Export CSV', ar: 'تصدير CSV' },
  'emp.name': { en: 'Name', ar: 'الاسم' },
  'emp.number': { en: 'Employee #', ar: 'رقم الموظف' },
  'emp.email': { en: 'Email', ar: 'البريد' },
  'emp.department': { en: 'Department', ar: 'القسم' },
  'emp.job_title': { en: 'Job Title', ar: 'المسمى الوظيفي' },
  'emp.status': { en: 'Status', ar: 'الحالة' },
  'emp.nationality': { en: 'Nationality', ar: 'الجنسية' },
  'emp.saudi': { en: 'Saudi', ar: 'سعودي' },
  'emp.non_saudi': { en: 'Non-Saudi', ar: 'غير سعودي' },
  'emp.all_statuses': { en: 'All Statuses', ar: 'كل الحالات' },
  'emp.all_departments': { en: 'All Departments', ar: 'كل الأقسام' },
  'emp.all_nationalities': { en: 'All Nationalities', ar: 'كل الجنسيات' },
  'emp.delete_confirm': { en: 'Are you sure you want to terminate this employee?', ar: 'هل أنت متأكد من إنهاء خدمة هذا الموظف؟' },

  // Employee Detail
  'empd.new_title': { en: 'New Employee', ar: 'موظف جديد' },
  'empd.edit_title': { en: 'Edit Employee', ar: 'تعديل الموظف' },
  'empd.back': { en: 'Back to Employees', ar: 'العودة للموظفين' },
  'empd.save': { en: 'Save', ar: 'حفظ' },
  'empd.first_name': { en: 'First Name', ar: 'الاسم الأول' },
  'empd.last_name': { en: 'Last Name', ar: 'اسم العائلة' },
  'empd.first_name_ar': { en: 'First Name (Arabic)', ar: 'الاسم الأول (عربي)' },
  'empd.last_name_ar': { en: 'Last Name (Arabic)', ar: 'اسم العائلة (عربي)' },
  'empd.national_id': { en: 'National ID', ar: 'رقم الهوية' },
  'empd.phone': { en: 'Phone', ar: 'الهاتف' },
  'empd.hire_date': { en: 'Hire Date', ar: 'تاريخ التعيين' },
  'empd.salary': { en: 'Salary (SAR)', ar: 'الراتب (ريال)' },
  'empd.gender': { en: 'Gender', ar: 'الجنس' },
  'empd.male': { en: 'Male', ar: 'ذكر' },
  'empd.female': { en: 'Female', ar: 'أنثى' },
  'empd.contract_type': { en: 'Contract Type', ar: 'نوع العقد' },
  'empd.work_mode': { en: 'Work Mode', ar: 'نمط العمل' },
  'empd.manager': { en: 'Manager', ar: 'المدير' },
  'empd.whatsapp': { en: 'WhatsApp', ar: 'واتساب' },
  'empd.language': { en: 'Preferred Language', ar: 'اللغة المفضلة' },
  'empd.is_saudi': { en: 'Saudi National', ar: 'مواطن سعودي' },

  // Departments
  'dept.title': { en: 'Departments', ar: 'الأقسام' },
  'dept.create': { en: 'New Department', ar: 'قسم جديد' },
  'dept.name': { en: 'Name', ar: 'الاسم' },
  'dept.name_ar': { en: 'Name (Arabic)', ar: 'الاسم (عربي)' },
  'dept.employees': { en: 'Employees', ar: 'الموظفون' },
  'dept.budget': { en: 'Headcount Budget', ar: 'ميزانية العدد' },
  'dept.actions': { en: 'Actions', ar: 'الإجراءات' },
  'dept.edit': { en: 'Edit', ar: 'تعديل' },
  'dept.delete': { en: 'Delete', ar: 'حذف' },
  'dept.delete_confirm': { en: 'Delete this department? This cannot be undone.', ar: 'حذف هذا القسم؟ لا يمكن التراجع.' },
  'dept.has_employees': { en: 'Cannot delete department with active employees.', ar: 'لا يمكن حذف قسم يحتوي على موظفين نشطين.' },

  // Leaves
  'leave.title': { en: 'Leave Requests', ar: 'طلبات الإجازات' },
  'leave.employee': { en: 'Employee', ar: 'الموظف' },
  'leave.type': { en: 'Type', ar: 'النوع' },
  'leave.dates': { en: 'Dates', ar: 'التواريخ' },
  'leave.days': { en: 'Days', ar: 'الأيام' },
  'leave.status': { en: 'Status', ar: 'الحالة' },
  'leave.reason': { en: 'Reason', ar: 'السبب' },
  'leave.actions': { en: 'Actions', ar: 'الإجراءات' },
  'leave.approve': { en: 'Approve', ar: 'قبول' },
  'leave.reject': { en: 'Reject', ar: 'رفض' },
  'leave.all_statuses': { en: 'All Statuses', ar: 'كل الحالات' },
  'leave.pending': { en: 'Pending', ar: 'معلق' },
  'leave.approved': { en: 'Approved', ar: 'مقبول' },
  'leave.rejected': { en: 'Rejected', ar: 'مرفوض' },
  'leave.cancelled': { en: 'Cancelled', ar: 'ملغي' },
  'leave.reject_title': { en: 'Reject Leave Request', ar: 'رفض طلب الإجازة' },
  'leave.reject_reason': { en: 'Reason for rejection...', ar: 'سبب الرفض...' },

  // Reports
  'rep.title': { en: 'Reports', ar: 'التقارير' },
  'rep.leave_util': { en: 'Leave Utilization', ar: 'استخدام الإجازات' },
  'rep.headcount': { en: 'Headcount', ar: 'عدد الموظفين' },
  'rep.saudization': { en: 'Saudization', ar: 'السعودة' },
  'rep.agent_perf': { en: 'Agent Performance', ar: 'أداء الوكلاء' },
  'rep.start_date': { en: 'Start Date', ar: 'تاريخ البداية' },
  'rep.end_date': { en: 'End Date', ar: 'تاريخ النهاية' },
  'rep.apply': { en: 'Apply', ar: 'تطبيق' },
  'rep.no_data': { en: 'No data available for the selected filters.', ar: 'لا توجد بيانات للفلاتر المحددة.' },

  // Settings
  'set.title': { en: 'Tenant Settings', ar: 'إعدادات المنشأة' },
  'set.name': { en: 'Company Name', ar: 'اسم الشركة' },
  'set.name_ar': { en: 'Company Name (Arabic)', ar: 'اسم الشركة (عربي)' },
  'set.domain': { en: 'Domain', ar: 'النطاق' },
  'set.cr_number': { en: 'CR Number', ar: 'رقم السجل التجاري' },
  'set.gosi_number': { en: 'GOSI Number', ar: 'رقم التأمينات' },
  'set.plan': { en: 'Plan', ar: 'الخطة' },
  'set.save': { en: 'Save Changes', ar: 'حفظ التغييرات' },

  // Common
  'common.loading': { en: 'Loading...', ar: 'جاري التحميل...' },
  'common.save': { en: 'Save', ar: 'حفظ' },
  'common.cancel': { en: 'Cancel', ar: 'إلغاء' },
  'common.confirm': { en: 'Confirm', ar: 'تأكيد' },
  'common.delete': { en: 'Delete', ar: 'حذف' },
  'common.edit': { en: 'Edit', ar: 'تعديل' },
  'common.create': { en: 'Create', ar: 'إنشاء' },
  'common.search': { en: 'Search', ar: 'بحث' },
  'common.filter': { en: 'Filter', ar: 'تصفية' },
  'common.reset': { en: 'Reset', ar: 'إعادة تعيين' },
  'common.no_data': { en: 'No data found', ar: 'لا توجد بيانات' },
  'common.error': { en: 'An error occurred', ar: 'حدث خطأ' },
  'common.success': { en: 'Success', ar: 'تم بنجاح' },
  'common.logout': { en: 'Logout', ar: 'تسجيل الخروج' },
  'common.active': { en: 'Active', ar: 'نشط' },
  'common.terminated': { en: 'Terminated', ar: 'منتهي' },
  'common.on_leave': { en: 'On Leave', ar: 'في إجازة' },
  'common.probation': { en: 'Probation', ar: 'تحت التجربة' },
  'common.page': { en: 'Page', ar: 'صفحة' },
  'common.of': { en: 'of', ar: 'من' },
  'common.prev': { en: 'Previous', ar: 'السابق' },
  'common.next': { en: 'Next', ar: 'التالي' },
  'common.yes': { en: 'Yes', ar: 'نعم' },
  'common.no': { en: 'No', ar: 'لا' },
};

let currentLang = localStorage.getItem('krew_lang') || 'en';

export function t(key) {
  const entry = strings[key];
  if (!entry) return key;
  return entry[currentLang] || entry.en || key;
}

export function getCurrentLang() {
  return currentLang;
}

export function toggleLang() {
  currentLang = currentLang === 'en' ? 'ar' : 'en';
  localStorage.setItem('krew_lang', currentLang);
  document.documentElement.dir = currentLang === 'ar' ? 'rtl' : 'ltr';
  document.documentElement.lang = currentLang;
  // Dispatch custom event so pages can re-render
  window.dispatchEvent(new CustomEvent('langchange'));
}

export function applyLang() {
  document.documentElement.dir = currentLang === 'ar' ? 'rtl' : 'ltr';
  document.documentElement.lang = currentLang;
}
