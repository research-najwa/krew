"""Seed Saudi HR policies into the RAG pipeline for all tenants.

Usage:
    cd backend && python -m scripts.seed_policies

Idempotent — skips if policies already exist for a tenant.
Handles missing OpenAI API key gracefully (stores policies without embeddings).
"""
import asyncio
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text
from app.database import async_session
from app.models.tenant import Tenant
from app.models.policy import Policy, PolicyChunk
from app.config import get_settings

settings = get_settings()

# ─── 12+ Bilingual Saudi HR Policies ───────────────────────────────────────

POLICIES = [
    {
        "title": "Annual Leave Policy",
        "category": "leave",
        "content": """Annual Leave Policy / سياسة الإجازة السنوية

Entitlement:
- Employees are entitled to 21 calendar days of paid annual leave per year for the first 5 years of service.
- After 5 years of continuous service, entitlement increases to 30 calendar days per year.
- Annual leave accrues from the date of joining and is calculated on a pro-rata basis during the first year.

الاستحقاق:
- يستحق الموظف 21 يوم إجازة سنوية مدفوعة الأجر خلال السنوات الخمس الأولى.
- بعد 5 سنوات من الخدمة المستمرة، يزيد الاستحقاق إلى 30 يوم في السنة.
- تُحتسب الإجازة السنوية من تاريخ الالتحاق بالعمل وعلى أساس تناسبي خلال السنة الأولى.

Scheduling:
- Leave must be requested at least 14 days in advance.
- The employer may determine leave timing based on business needs, per Saudi Labor Law Article 109.
- Public holidays (Eid Al-Fitr, Eid Al-Adha, National Day, Founding Day) are NOT deducted from annual leave.
- Friday and Saturday (Saudi weekend) are not counted as leave days.

جدولة الإجازات:
- يجب تقديم طلب الإجازة قبل 14 يوم على الأقل.
- يحق لصاحب العمل تحديد موعد الإجازة وفقاً لمتطلبات العمل، حسب المادة 109 من نظام العمل السعودي.
- لا تُخصم الإجازات الرسمية (عيد الفطر، عيد الأضحى، اليوم الوطني، يوم التأسيس) من رصيد الإجازة السنوية.
- لا يُحتسب يوما الجمعة والسبت (عطلة نهاية الأسبوع) من أيام الإجازة.

Carry-Over:
- Unused leave may be carried forward to the next year, up to a maximum of 10 days.
- Carried-over days must be used within the first quarter (Q1) of the following year.

ترحيل الرصيد:
- يمكن ترحيل الإجازات غير المستخدمة إلى السنة التالية بحد أقصى 10 أيام.
- يجب استخدام الأيام المرحّلة خلال الربع الأول من السنة التالية.

Payout:
- Upon termination, unused accrued leave is paid out based on the employee's last basic salary.
- Per Saudi Labor Law Article 111, the employee is entitled to leave pay for fractions of the year.

الدفع عند انتهاء الخدمة:
- عند انتهاء الخدمة، يُصرف مقابل رصيد الإجازات المستحقة بناءً على آخر راتب أساسي.
- وفقاً للمادة 111 من نظام العمل، يستحق الموظف أجر إجازة عن أجزاء السنة.""",
    },
    {
        "title": "Sick Leave Policy",
        "category": "leave",
        "content": """Sick Leave Policy / سياسة الإجازة المرضية

Entitlement (per Saudi Labor Law Article 117):
- Employees are entitled to sick leave as follows per calendar year:
  * First 30 days: Full pay (100%)
  * Next 60 days: Three-quarters pay (75%)
  * Following 30 days: Unpaid
- Total maximum: 120 days per year.

الاستحقاق (وفقاً للمادة 117 من نظام العمل):
- يستحق الموظف إجازة مرضية على النحو التالي:
  * أول 30 يوم: أجر كامل (100%)
  * الـ 60 يوم التالية: ثلاثة أرباع الأجر (75%)
  * الـ 30 يوم التالية: بدون أجر
- الحد الأقصى: 120 يوم في السنة.

Medical Certificate:
- A medical certificate from an approved healthcare provider is required for sick leave exceeding 2 consecutive days.
- For sick leave of 1-2 days, a self-declaration may be accepted up to 3 times per year.

الشهادة الطبية:
- يُشترط تقديم شهادة طبية من مقدم رعاية صحية معتمد للإجازة المرضية التي تزيد عن يومين متتاليين.
- للإجازة المرضية من 1-2 يوم، يمكن قبول الإقرار الذاتي حتى 3 مرات في السنة.

Notification:
- The employee must notify their direct manager within 2 hours of their shift start time.
- HR must be notified within 24 hours.

الإبلاغ:
- يجب على الموظف إبلاغ مديره المباشر خلال ساعتين من بداية الوردية.
- يجب إبلاغ الموارد البشرية خلال 24 ساعة.""",
    },
    {
        "title": "Maternity Leave Policy",
        "category": "leave",
        "content": """Maternity Leave Policy / سياسة إجازة الأمومة

Entitlement (per Saudi Labor Law Article 151):
- Female employees are entitled to 70 days of maternity leave with full pay.
- Leave may begin up to 4 weeks before the expected delivery date.
- The remaining days are taken after delivery.
- An additional 30 days of unpaid leave may be requested after maternity leave.

الاستحقاق (وفقاً للمادة 151 من نظام العمل):
- تستحق الموظفة 70 يوم إجازة أمومة بأجر كامل.
- يمكن بدء الإجازة قبل 4 أسابيع من تاريخ الولادة المتوقع.
- تؤخذ الأيام المتبقية بعد الولادة.
- يمكن طلب 30 يوم إضافية بدون أجر بعد إجازة الأمومة.

Nursing Breaks:
- Upon return to work, the employee is entitled to one hour of nursing break per day for 24 months from the date of delivery.
- This hour may be split into two 30-minute breaks.

فترات الرضاعة:
- عند العودة للعمل، تستحق الموظفة ساعة رضاعة يومياً لمدة 24 شهر من تاريخ الولادة.
- يمكن تقسيم هذه الساعة إلى فترتين كل منهما 30 دقيقة.

Job Protection:
- The employee's position is protected during maternity leave.
- Termination during maternity leave is prohibited per Saudi Labor Law.""",
    },
    {
        "title": "Paternity Leave Policy",
        "category": "leave",
        "content": """Paternity Leave Policy / سياسة إجازة الأبوة

Entitlement:
- Male employees are entitled to 3 days of paid paternity leave upon the birth of a child.
- Leave must be taken within 7 days of the birth date.

الاستحقاق:
- يستحق الموظف 3 أيام إجازة أبوة مدفوعة الأجر عند ولادة طفل.
- يجب أخذ الإجازة خلال 7 أيام من تاريخ الولادة.

Documentation:
- A birth certificate or hospital notification is required.

المستندات المطلوبة:
- شهادة ميلاد أو إشعار من المستشفى.""",
    },
    {
        "title": "Hajj Leave Policy",
        "category": "leave",
        "content": """Hajj Leave Policy / سياسة إجازة الحج

Entitlement (per Saudi Labor Law Article 114):
- Muslim employees are entitled to 10-15 days of paid Hajj leave (including Eid Al-Adha).
- This is a one-time entitlement during the employee's tenure with the company.
- The employee must have completed at least 2 years of continuous service.

الاستحقاق (وفقاً للمادة 114 من نظام العمل):
- يستحق الموظف المسلم 10-15 يوم إجازة حج مدفوعة الأجر (شاملة عيد الأضحى).
- هذا استحقاق لمرة واحدة خلال فترة خدمة الموظف في الشركة.
- يجب أن يكون الموظف قد أكمل سنتين من الخدمة المستمرة.

Process:
- Request must be submitted at least 30 days before the Hajj season.
- Only a limited number of employees per department may take Hajj leave simultaneously.
- Priority is given to employees who have not performed Hajj before.

الإجراءات:
- يجب تقديم الطلب قبل 30 يوم على الأقل من موسم الحج.
- يُسمح لعدد محدود من الموظفين في كل قسم بأخذ إجازة الحج في نفس الوقت.
- الأولوية لمن لم يؤدِّ فريضة الحج من قبل.""",
    },
    {
        "title": "Bereavement Leave Policy",
        "category": "leave",
        "content": """Bereavement Leave Policy / سياسة إجازة الوفاة

Entitlement:
- Employees are entitled to 5 days of paid bereavement leave upon the death of a spouse, parent, child, sibling, or grandparent.
- 3 days of paid leave for the death of other close relatives (uncle, aunt, in-laws).

الاستحقاق:
- يستحق الموظف 5 أيام إجازة وفاة مدفوعة الأجر عند وفاة الزوج/الزوجة، أحد الوالدين، الأبناء، الإخوة، أو الأجداد.
- 3 أيام إجازة مدفوعة عند وفاة الأقارب الآخرين (العم، العمة، أهل الزوج/الزوجة).

Iddah Leave (for female employees):
- Per Saudi Labor Law Article 160, a Muslim female employee whose husband dies is entitled to a minimum of 4 months and 10 days (Iddah period) with full pay.

إجازة العدة (للموظفات):
- وفقاً للمادة 160 من نظام العمل، تستحق الموظفة المسلمة التي يتوفى زوجها إجازة عدة لا تقل عن 4 أشهر و10 أيام بأجر كامل.

Documentation:
- Death certificate is required.
- For Iddah, marriage certificate and death certificate of spouse.

المستندات:
- يُشترط تقديم شهادة الوفاة.
- لإجازة العدة، شهادة الزواج وشهادة وفاة الزوج.""",
    },
    {
        "title": "Emergency Leave Policy",
        "category": "leave",
        "content": """Emergency Leave Policy / سياسة الإجازة الطارئة

Entitlement:
- Employees are entitled to 5 days of paid emergency leave per year.
- Emergency leave is for unforeseen urgent personal situations.
- If emergency balance is exhausted, days may be deducted from annual leave balance.

الاستحقاق:
- يستحق الموظف 5 أيام إجازة طارئة مدفوعة الأجر في السنة.
- الإجازة الطارئة مخصصة للحالات الشخصية العاجلة غير المتوقعة.
- في حال نفاد رصيد الإجازات الطارئة، قد يُخصم من رصيد الإجازة السنوية.

Approval:
- Must be reported to the direct manager as soon as possible.
- HR approval is required within 48 hours of the emergency.
- Supporting documentation may be requested.

الموافقة:
- يجب إبلاغ المدير المباشر في أقرب وقت ممكن.
- موافقة الموارد البشرية مطلوبة خلال 48 ساعة من الحالة الطارئة.
- قد يُطلب تقديم مستندات داعمة.""",
    },
    {
        "title": "Unpaid Leave Policy",
        "category": "leave",
        "content": """Unpaid Leave Policy / سياسة الإجازة بدون راتب

Eligibility:
- Employees may request unpaid leave after exhausting their annual leave balance.
- Maximum 30 consecutive days per request.
- Total unpaid leave may not exceed 60 days per calendar year.

الأهلية:
- يمكن للموظف طلب إجازة بدون راتب بعد استنفاد رصيد الإجازة السنوية.
- الحد الأقصى 30 يوم متتالية لكل طلب.
- لا يتجاوز إجمالي الإجازة بدون راتب 60 يوم في السنة الميلادية.

Impact:
- No salary or allowances during unpaid leave.
- GOSI contributions are suspended during unpaid leave.
- The period is not counted toward end-of-service benefits calculation.
- Health insurance coverage continues for the first 30 days.

التأثير:
- لا يُصرف راتب أو بدلات خلال الإجازة بدون راتب.
- تُعلق اشتراكات التأمينات الاجتماعية خلال الإجازة.
- لا تُحتسب الفترة ضمن حساب مكافأة نهاية الخدمة.
- يستمر التأمين الصحي خلال أول 30 يوم.

Approval:
- Requires manager approval and HR review.
- Must be requested at least 7 days in advance (except for emergencies).""",
    },
    {
        "title": "Attendance and Working Hours Policy",
        "category": "attendance",
        "content": """Attendance and Working Hours Policy / سياسة الدوام وساعات العمل

Working Hours (per Saudi Labor Law Article 98):
- Standard working hours: 8 hours per day, 48 hours per week.
- During Ramadan, Muslim employees work 6 hours per day, 36 hours per week.
- Working hours are from Sunday to Thursday.
- Friday and Saturday are the official weekend.

ساعات العمل (وفقاً للمادة 98 من نظام العمل):
- ساعات العمل القياسية: 8 ساعات يومياً، 48 ساعة أسبوعياً.
- خلال شهر رمضان، يعمل الموظفون المسلمون 6 ساعات يومياً، 36 ساعة أسبوعياً.
- أيام العمل من الأحد إلى الخميس.
- الجمعة والسبت هي عطلة نهاية الأسبوع الرسمية.

Overtime:
- Overtime must be pre-approved by the direct manager.
- Overtime pay rate: 150% of hourly rate (basic salary / 30 / 8 * 1.5).
- Maximum overtime: 720 hours per year.

العمل الإضافي:
- يجب الحصول على موافقة مسبقة من المدير المباشر.
- معدل أجر العمل الإضافي: 150% من الأجر بالساعة.
- الحد الأقصى للعمل الإضافي: 720 ساعة في السنة.

Tardiness:
- Employees must be at their workstation by the designated start time.
- 3 instances of tardiness (>15 minutes) per month may result in a written warning.
- Habitual tardiness may result in deduction from salary per labor law provisions.""",
    },
    {
        "title": "Code of Conduct Policy",
        "category": "conduct",
        "content": """Code of Conduct / سياسة قواعد السلوك المهني

Professional Behavior:
- All employees must maintain professional conduct in the workplace.
- Harassment, discrimination, and bullying are strictly prohibited and may result in immediate termination.
- The company follows a zero-tolerance policy for workplace violence.

السلوك المهني:
- يجب على جميع الموظفين الحفاظ على السلوك المهني في بيئة العمل.
- التحرش والتمييز والتنمر محظورة تماماً وقد تؤدي إلى الفصل الفوري.
- تتبع الشركة سياسة عدم التسامح المطلق مع العنف في بيئة العمل.

Confidentiality:
- Employees must protect company and client confidential information.
- Sharing proprietary data without authorization is grounds for termination and legal action.
- NDA obligations continue after employment ends.

السرية:
- يجب على الموظفين حماية معلومات الشركة والعملاء السرية.
- مشاركة البيانات الخاصة بدون إذن سبب للفصل واتخاذ إجراءات قانونية.
- تستمر التزامات اتفاقية عدم الإفصاح بعد انتهاء التوظيف.

Dress Code:
- Business professional attire is required in the office.
- Saudi national dress (Thobe/Abaya) is always acceptable.
- Casual dress may be permitted on designated days with manager approval.

قواعد اللباس:
- يُشترط ارتداء الملابس المهنية الرسمية في المكتب.
- الزي الوطني السعودي (الثوب/العباية) مقبول دائماً.
- قد يُسمح باللباس غير الرسمي في أيام محددة بموافقة المدير.""",
    },
    {
        "title": "End of Service Benefits (EOSB) Policy",
        "category": "compensation",
        "content": """End of Service Benefits Policy / سياسة مكافأة نهاية الخدمة

Calculation (per Saudi Labor Law Articles 84-86):
- For the first 5 years: Half month's salary for each year of service.
- After 5 years: One full month's salary for each additional year.
- Fractions of a year are calculated proportionally.
- "Salary" for EOSB purposes includes: basic salary + housing allowance + other fixed allowances.

الحساب (وفقاً للمواد 84-86 من نظام العمل):
- أول 5 سنوات: نصف راتب شهري عن كل سنة خدمة.
- بعد 5 سنوات: راتب شهري كامل عن كل سنة إضافية.
- تُحسب أجزاء السنة بالتناسب.
- "الراتب" لأغراض مكافأة نهاية الخدمة يشمل: الراتب الأساسي + بدل السكن + البدلات الثابتة الأخرى.

Resignation:
- If the employee resigns:
  * Less than 2 years of service: No EOSB.
  * 2-5 years: One-third of the full EOSB.
  * 5-10 years: Two-thirds of the full EOSB.
  * More than 10 years: Full EOSB.

الاستقالة:
- في حال استقالة الموظف:
  * أقل من سنتين: لا يستحق مكافأة.
  * 2-5 سنوات: ثلث المكافأة الكاملة.
  * 5-10 سنوات: ثلثي المكافأة الكاملة.
  * أكثر من 10 سنوات: المكافأة الكاملة.

Termination by Employer:
- Full EOSB is paid if terminated by the employer (unless for cause per Article 80).

إنهاء الخدمة من قبل صاحب العمل:
- تُصرف المكافأة كاملة إذا أنهى صاحب العمل الخدمة (ما لم يكن بسبب حالة منصوص عليها في المادة 80).""",
    },
    {
        "title": "Remote Work (WFH) Policy",
        "category": "general",
        "content": """Remote Work Policy / سياسة العمل عن بُعد

Eligibility:
- Remote work arrangements are available for eligible positions as determined by the department head.
- Employees must have completed their probation period.
- Hybrid employees may work remotely for the number of days specified in their contract.

الأهلية:
- ترتيبات العمل عن بُعد متاحة للوظائف المؤهلة حسب تحديد رئيس القسم.
- يجب أن يكون الموظف قد أكمل فترة التجربة.
- يمكن للموظفين بنظام العمل المختلط العمل عن بُعد بعدد الأيام المحدد في عقدهم.

Requirements:
- Must be reachable during standard working hours.
- Reliable internet connection and appropriate workspace.
- Must attend in-person meetings when required.
- Must use company VPN for accessing internal systems.

المتطلبات:
- يجب أن يكون الموظف متاحاً خلال ساعات العمل القياسية.
- اتصال إنترنت موثوق وبيئة عمل مناسبة.
- يجب حضور الاجتماعات الحضورية عند الطلب.
- يجب استخدام VPN الشركة للوصول إلى الأنظمة الداخلية.

Security:
- Company data must not be accessed on public Wi-Fi without VPN.
- Company devices must be password-protected and encrypted.
- Screen lock must be enabled with a maximum timeout of 5 minutes.

الأمان:
- يُمنع الوصول لبيانات الشركة عبر شبكات Wi-Fi عامة بدون VPN.
- يجب حماية أجهزة الشركة بكلمة مرور وتشفير.
- يجب تفعيل قفل الشاشة بحد أقصى 5 دقائق.""",
    },
    {
        "title": "Probation Period Policy",
        "category": "general",
        "content": """Probation Period Policy / سياسة فترة التجربة

Duration (per Saudi Labor Law Article 53):
- The standard probation period is 90 days from the date of joining.
- Probation may be extended once for an additional 90 days with written agreement from both parties.
- Total probation may not exceed 180 days.

المدة (وفقاً للمادة 53 من نظام العمل):
- فترة التجربة القياسية 90 يوم من تاريخ الالتحاق.
- يمكن تمديد فترة التجربة مرة واحدة لمدة 90 يوم إضافية بموافقة كتابية من الطرفين.
- لا يجوز أن تتجاوز فترة التجربة الإجمالية 180 يوم.

During Probation:
- Either party may terminate the contract without cause or compensation.
- The employee is not entitled to end-of-service benefits.
- Annual leave does not accrue during probation (company policy; more generous than law minimum).
- Sick leave entitlement applies from day one.

خلال فترة التجربة:
- يحق لأي طرف إنهاء العقد بدون سبب أو تعويض.
- لا يستحق الموظف مكافأة نهاية الخدمة.
- لا يتم احتساب الإجازة السنوية خلال فترة التجربة (سياسة الشركة).
- يستحق الموظف الإجازة المرضية من اليوم الأول.

Performance Review:
- A probation performance review is conducted in the last week of probation.
- The manager must recommend: Confirm, Extend, or Terminate.

تقييم الأداء:
- يُجرى تقييم أداء فترة التجربة في الأسبوع الأخير.
- يجب على المدير التوصية بـ: التثبيت، التمديد، أو الإنهاء.""",
    },
    {
        "title": "GOSI (Social Insurance) Policy",
        "category": "benefits",
        "content": """GOSI Social Insurance Policy / سياسة التأمينات الاجتماعية

Registration:
- All employees must be registered with GOSI within the first week of joining.
- The company handles the registration process.
- Employees must provide their national ID or Iqama number.

التسجيل:
- يجب تسجيل جميع الموظفين في التأمينات الاجتماعية خلال الأسبوع الأول من الالتحاق.
- تتولى الشركة عملية التسجيل.
- يجب على الموظفين تقديم رقم الهوية الوطنية أو الإقامة.

Contribution Rates (2024):
- Saudi employees:
  * Employee contribution: 9.75% of salary (pension 9% + unemployment 0.75%)
  * Employer contribution: 11.75% of salary (pension 9% + OHRP 2% + unemployment 0.75%)
- Non-Saudi employees:
  * Employer contribution: 2% of salary (OHRP only)
  * Employee contribution: None

نسب الاشتراك:
- الموظفون السعوديون:
  * حصة الموظف: 9.75% من الراتب (تقاعد 9% + ساند 0.75%)
  * حصة صاحب العمل: 11.75% من الراتب (تقاعد 9% + أخطار مهنية 2% + ساند 0.75%)
- الموظفون غير السعوديين:
  * حصة صاحب العمل: 2% من الراتب (أخطار مهنية فقط)
  * حصة الموظف: لا يوجد""",
    },
    {
        "title": "Workplace Safety Policy",
        "category": "safety",
        "content": """Workplace Safety Policy / سياسة السلامة في بيئة العمل

General Safety:
- All employees must follow workplace safety guidelines and report hazards immediately.
- Fire evacuation drills are conducted quarterly.
- First aid kits are located on every floor and in common areas.
- Emergency exits must remain clear at all times.

السلامة العامة:
- يجب على جميع الموظفين اتباع إرشادات السلامة والإبلاغ عن المخاطر فوراً.
- تُجرى تدريبات إخلاء الحريق كل ربع سنة.
- صناديق الإسعافات الأولية موجودة في كل طابق والمناطق المشتركة.
- يجب أن تبقى مخارج الطوارئ خالية في جميع الأوقات.

Heat Safety (Saudi-specific):
- Outdoor work is prohibited between 12:00 PM and 3:00 PM during summer months (June-September) per Ministry of Human Resources regulations.
- Adequate hydration and shade must be provided for outdoor workers.

السلامة من الحرارة:
- يُحظر العمل في الخارج بين الساعة 12:00 ظهراً و3:00 مساءً خلال أشهر الصيف (يونيو-سبتمبر) وفقاً لأنظمة وزارة الموارد البشرية.
- يجب توفير الترطيب الكافي والظل للعاملين في الخارج.

Reporting:
- Workplace injuries must be reported within 24 hours.
- All incidents are logged and investigated.
- GOSI occupational hazard claims are filed by HR on behalf of the employee.

الإبلاغ:
- يجب الإبلاغ عن إصابات العمل خلال 24 ساعة.
- يتم تسجيل وتحقيق جميع الحوادث.
- تتولى الموارد البشرية تقديم مطالبات الأخطار المهنية للتأمينات نيابة عن الموظف.""",
    },
]


async def seed_policies():
    """Seed policies for all existing tenants."""
    async with async_session() as db:
        # Get all tenants
        result = await db.execute(select(Tenant))
        tenants = result.scalars().all()

        if not tenants:
            print("No tenants found. Run the main seed script first.")
            print("  python -m scripts.seed")
            return

        for tenant in tenants:
            print(f"\nProcessing tenant: {tenant.name} ({tenant.id})")

            # Get existing policy titles to avoid duplicates
            existing_result = await db.execute(
                select(Policy.title).where(Policy.tenant_id == tenant.id)
            )
            existing_titles = {row[0] for row in existing_result.fetchall()}

            policies_added = 0
            for policy_data in POLICIES:
                if policy_data["title"] in existing_titles:
                    continue

                # Create the Policy record
                policy = Policy(
                    tenant_id=tenant.id,
                    title=policy_data["title"],
                    category=policy_data["category"],
                    source_filename="seed_policies.py",
                    is_active=True,
                )
                db.add(policy)
                await db.flush()

                # Split content into chunks
                content = policy_data["content"]
                chunks = _split_into_chunks(content)

                # Try to generate embeddings
                embeddings = None
                if settings.openai_api_key:
                    try:
                        embeddings = await _get_embeddings_batch(chunks)
                    except Exception as e:
                        print(f"  Warning: Could not generate embeddings for '{policy_data['title']}': {e}")
                        print("  Storing chunks without embeddings. RAG search will not work until embeddings are generated.")
                        embeddings = None

                for idx, chunk_text in enumerate(chunks):
                    embedding = embeddings[idx] if embeddings and idx < len(embeddings) else None
                    chunk = PolicyChunk(
                        policy_id=policy.id,
                        chunk_index=idx,
                        content=chunk_text,
                        content_normalized=_strip_arabic_diacritics(chunk_text),
                        embedding=embedding,
                        token_count=max(1, len(chunk_text) // 4),
                    )
                    db.add(chunk)

                policies_added += 1
                print(f"  Added: {policy_data['title']} ({len(chunks)} chunks)")

            await db.commit()
            print(f"  Done. Added {policies_added} new policies for {tenant.name}.")

    print("\nPolicy seeding complete.")


def _strip_arabic_diacritics(s: str) -> str:
    import re
    return re.sub(r'[\u0610-\u061A\u064B-\u065F\u0670]', '', s)


def _split_into_chunks(content: str, target_chars: int = 2000) -> list[str]:
    """Split content into chunks by paragraph boundaries."""
    import re
    paragraphs = re.split(r"\n\s*\n", content.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len + 2 > target_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks


async def _get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embeddings from OpenAI API."""
    import httpx
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.embedding_model,
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()
        sorted_embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_embeddings]


if __name__ == "__main__":
    asyncio.run(seed_policies())
