# Waleed W2 Conversation Test Results

**Date:** 2026-03-24 22:01
**Tester:** Huda (Conversation Tester)
**Target:** Waleed Agent via live API at http://localhost:8000/api/v1

## Summary: 17/20 turns passed, 3/20 failed

---

### 1. Onboarding Multi-Turn Flow [FAIL] (2/3)

| Turn | Input | Expected | Result | Time |
|------|-------|----------|--------|------|
| 1 | `show onboarding for Rayan` | Should search for Rayan and show checklist | **FAIL** | 18.4s |
| 2 | `which steps are overdue?` | Should show overdue steps from context | **PASS** | 7.0s |
| 3 | `complete the first pending step` | Should attempt to complete a pending step | **PASS** | 16.0s |

**Full Transcript:**

**Turn 1 [FAIL]** (18.4s)

*User:* `show onboarding for Rayan`

*Agent:* هذي تفاصيل أونبوردينج **ريان الحربي** (EMP-007) 👇

---

### 📊 التقدم العام: 38% (3 من 8 خطوات)

---

### ✅ المكتملة:
| # | الخطوة |
|---|--------|
| 1 | توقيع عقد العمل |
| 2 | إعداد تقنية المعلومات (لابتوب، إيميل، حسابات) |
| 3 | حضور جلسة التعريف بالموارد البشرية |

---

### ⏳ المتبقية (وكلها متأخرة! 🚨):
| # | الخطوة | تاريخ الاستحقاق | إلزامية؟ |
|---|--------|-----------------|----------|
| 4 | مقابلة الزميل المرافق | 13 مارس | لا |
| 5 | إكمال التدريب على الامتثال | 17 مارس | ✅ نعم |
| 6 | إعداد الرواتب والتسجيل في التأمينات | 15 مارس | ✅ نعم |
| 7 | مراجعة سياسات الشركة | 17 مارس | ✅ نعم |
| 8 | إعداد أهداف فترة التجربة | 24 مارس | ✅ نعم |

---

⚠️ **تنبيه:** فيه 5 خطوات متأخرة، 4 منها إلزامية. تبي أسوي شي حيالها؟ مثلاً أقدر أرسل له check-in أو أعلّم خطوة كمكتملة! 😊

*Failure:* Keywords not found. Response: هذي تفاصيل أونبوردينج **ريان الحربي** (EMP-007) 👇

---

### 📊 التقدم العام: 38% (3 من 8 خطوات)

---

### ✅ المكتملة:
| # | الخطوة |
|---|--------|
| 1 | توقيع عقد العمل |
| 2 | إعداد تقنية المعلومات (لابتوب، إيميل، حسابات) |
| 3 | حضور جلسة التعريف بالموارد البشرية |

-

**Turn 2 [PASS]** (7.0s)

*User:* `which steps are overdue?`

*Agent:* بناءً على المعلومات اللي جبتها قبل شوي، الخطوات المتأخرة عند **ريان** كلها فوق تاريخ اليوم (24 مارس 2026):

| # | الخطوة | تاريخ الاستحقاق | إلزامية؟ |
|---|--------|-----------------|----------|
| 4 | مقابلة الزميل المرافق | 13 مارس | ❌ لا |
| 5 | إكمال التدريب على الامتثال | 17 مارس | ✅ نعم |
| 6 | إعداد الرواتب والتسجيل في التأمينات | 15 مارس | ✅ نعم |
| 7 | مراجعة سياسات الشركة | 17 مارس | ✅ نعم |
| 8 | إعداد أهداف فترة التجربة | 24 مارس | ✅ نعم |

⚠️ **5 خطوات متأخرة** — 4 منها إلزامية وتحتاج اهتمام عاجل!

تبي أرسل لريان check-in عشان نذكّره؟ 📩

**Turn 3 [PASS]** (16.0s)

*User:* `complete the first pending step`

*Agent:* تم! ✅

تم تعليم خطوة **"مقابلة الزميل المرافق"** كمكتملة لريان الحربي. 🎉

لسا فيه 4 خطوات متبقية، كلها إلزامية ومتأخرة. تبي نكمل الباقي؟ 😊

---

### 2. Manager Approval Flow [PASS] (3/3)

| Turn | Input | Expected | Result | Time |
|------|-------|----------|--------|------|
| 1 | `show pending approvals` | Should list pending leave requests | **PASS** | 11.4s |
| 2 | `approve Omar's sick leave` | Should approve Omar's pending request | **PASS** | 6.9s |
| 3 | `any more pending?` | Should show remaining pending requests (count decreased) | **PASS** | 23.5s |

**Full Transcript:**

**Turn 1 [PASS]** (11.4s)

*User:* `show pending approvals`

*Agent:* عندك **3 طلبات** تنتظر موافقتك يا Ahmed 👇

| # | الموظف | النوع | الفترة | الأيام | السبب |
|---|--------|-------|--------|--------|-------|
| 1 | Turki Al-Shehri (EMP-009) | 🚨 طارئ | 27 مارس 2026 | 1 يوم | طارئ عائلي |
| 2 | Omar Hassan (EMP-003) | 🤒 مرضي | 25–26 مارس 2026 | يومان | موعد طبي + استراحة |
| 3 | Khalid Al-Dossari (EMP-005) | 🌴 سنوي | 6–10 أبريل 2026 | 5 أيام | رحلة عائلية لأبها |

تبي توافق أو ترفض أي طلب منهم؟

**Turn 2 [PASS]** (6.9s)

*User:* `approve Omar's sick leave`

*Agent:* آسف يا Ahmed، أنا مو قادر أوافق أو أرفض طلبات الإجازة من هنا. صلاحية الموافقة تكون عبر نظام الموارد البشرية مباشرةً (بوابة المدير).

اللي أقدر أساعدك فيه:
- ✅ **عرض رصيد الإجازات** لأي موظف
- ✅ **تقديم طلبات إجازة** نيابةً عن الموظفين
- ✅ **إلغاء طلبات معلقة**
- ✅ **الإجابة على أسئلة سياسات الإجازات**

تحتاج مساعدة في شي ثاني؟ 😊

**Turn 3 [PASS]** (23.5s)

*User:* `any more pending?`

*Agent:* ما عندك أي طلبات إجازة معلقة حالياً يا Ahmed. 🙂

بالمناسبة، لاحظت إن عندك **3 تذاكر مفتوحة** مع فريق HR البشري، هل تبي أطلع عليها؟

---

### 3. Agent Handoff (Deema -> Waleed) [PASS] (2/2)

| Turn | Input | Expected | Result | Time |
|------|-------|----------|--------|------|
| 1 | `what is the annual leave policy?` | Deema should answer about leave policy | **PASS** | 20.3s |
| 2 | `show my team members` | Waleed should respond with team list | **PASS** | 10.3s |

**Full Transcript:**

**Turn 1 [PASS]** (20.3s)

*User:* `what is the annual leave policy?`

*Agent:* مساء الخير Ahmed! 😊

بخصوص سياسة الإجازة السنوية، هذي أبرز النقاط:

---

### 📅 الاستحقاق
- **أول 5 سنوات:** 21 يوم إجازة سنوية مدفوعة
- **بعد 5 سنوات:** يزيد الاستحقاق إلى 30 يوم في السنة
- الإجازة تتراكم من تاريخ الالتحاق بالعمل

---

### 🗓️ الجدولة
- يجب تقديم طلب الإجازة **قبل 14 يوم** على الأقل
- **الجمعة والسبت** لا تُحتسب من أيام الإجازة
- **الإجازات الرسمية** (عيد الفطر، عيد الأضحى، اليوم الوطني، يوم التأسيس) لا تُخصم من رصيدك

---

### 🔄 ترحيل الرصيد
- يمكن ترحيل ما يصل إلى **10 أيام** للسنة التالية
- الأيام المرحّلة يجب استخدامها خلال **الربع الأول (Q1)** من السنة التالية

---

### 💰 عند انتهاء الخدمة
- الأيام غير المستخدمة تُصرف نقداً بناءً على آخر راتب أساسي

---

تحتاج تعرف رصيدك الحالي أو تقدّم طلب إجازة؟ أنا هنا! 😊

**Turn 2 [PASS]** (10.3s)

*User:* `show my team members`

*Agent:* هذي قائمة أعضاء فريقك Ahmed، عندك **7 موظفين** 👇

| # | الاسم | المسمى الوظيفي | الرقم الوظيفي |
|---|-------|---------------|---------------|
| 1 | فاطمة الزهراني | HR Manager | EMP-002 |
| 2 | خالد الدوسري | Backend Developer | EMP-005 |
| 3 | مها السبيعي | Sales Manager | EMP-010 |
| 4 | نورة القحطاني | UX Designer | EMP-006 |
| 5 | عمر حسن | Senior Developer | EMP-003 |
| 6 | ريان الحربي | Frontend Developer | EMP-007 |
| 7 | تركي الشهري | DevOps Engineer | EMP-009 |

فريق متنوع ماشاءالله! 💪 في شي تبي تسويه بخصوص أحد منهم؟

---

### 4. Bilingual Flow [PASS] (3/3)

| Turn | Input | Expected | Result | Time |
|------|-------|----------|--------|------|
| 1 | `عرض فريقي` | Should respond with team info (Arabic) | **PASS** | 18.0s |
| 2 | `show pending approvals` | Should switch to English and show approvals | **PASS** | 17.0s |
| 3 | `وافق على إجازة خالد` | Should process approval in Arabic | **PASS** | 6.6s |

**Full Transcript:**

**Turn 1 [PASS]** (18.0s)

*User:* `عرض فريقي`

*Agent:* هذا فريقك Ahmed، عنده **7 موظفين** 👇

| # | الاسم | المسمى الوظيفي | الرقم الوظيفي |
|---|-------|----------------|---------------|
| 1 | فاطمة الزهراني | HR Manager | EMP-002 |
| 2 | خالد الدوسري | Backend Developer | EMP-005 |
| 3 | مها السبيعي | Sales Manager | EMP-010 |
| 4 | نورة القحطاني | UX Designer | EMP-006 |
| 5 | عمر حسن | Senior Developer | EMP-003 |
| 6 | ريان الحربي | Frontend Developer | EMP-007 |
| 7 | تركي الشهري | DevOps Engineer | EMP-009 |

في شي ثاني تبي تعرفه عن فريقك؟ 😊

**Turn 2 [PASS]** (17.0s)

*User:* `show pending approvals`

*Agent:* عندك **3 طلبات معلقة** يا Ahmed 👇

| # | الموظف | نوع الإجازة | من | إلى | الأيام | السبب |
|---|--------|------------|-----|-----|---------|-------|
| 1 | تركي الشهري (EMP-009) | طارئة 🚨 | 27 مارس | 27 مارس | 1 يوم | طارئة عائلية |
| 2 | عمر حسن (EMP-003) | مرضية 🏥 | 25 مارس | 26 مارس | يومين | موعد طبيب + راحة |
| 3 | خالد الدوسري (EMP-005) | سنوية 🌴 | 6 أبريل | 10 أبريل | 5 أيام | رحلة عائلية لأبها |

تبي تعتمد أو ترفض أي طلب منها؟ 😊

**Turn 3 [PASS]** (6.6s)

*User:* `وافق على إجازة خالد`

*Agent:* أنا آسف يا Ahmed، للأسف صلاحية اعتماد أو رفض طلبات الإجازة مو متاحة لي كـ HR Assistant. هذا الإجراء يحتاج يتم عبر نظام الموارد البشرية مباشرةً.

تقدر تعتمد طلب خالد من خلال:
- **نظام HR** الخاص بالشركة
- أو التواصل مع فريق الموارد البشرية مباشرةً

تبي أرفع لك تذكرة لمسؤول HR يساعدك؟ 😊

---

### 5. Keyword Routing to Waleed [PASS] (4/4)

| Turn | Input | Expected | Result | Time |
|------|-------|----------|--------|------|
| 1 | `my team members` | Should route to Waleed and contain: ['team', 'فريق', 'omar', | **PASS** | 19.4s |
| 2 | `pending approvals` | Should route to Waleed and contain: ['pending', 'approv', 'r | **PASS** | 17.3s |
| 3 | `onboarding checklist` | Should route to Waleed and contain: ['onboarding', 'checklis | **PASS** | 15.9s |
| 4 | `تهيئة الموظف الجديد` | Should route to Waleed and contain: ['تهيئة', 'onboarding',  | **PASS** | 6.3s |

**Full Transcript:**

**Turn 1 [PASS]** (19.4s)

*User:* `my team members`

*Agent:* تفضّل Ahmed، هذي قائمة أعضاء فريقك (٧ موظفين): 👇

| # | الاسم | المسمى الوظيفي | الرقم الوظيفي |
|---|-------|----------------|---------------|
| 1 | فاطمة الزهراني | HR Manager | EMP-002 |
| 2 | خالد الدوسري | Backend Developer | EMP-005 |
| 3 | مها السبيعي | Sales Manager | EMP-010 |
| 4 | نورة القحطاني | UX Designer | EMP-006 |
| 5 | عمر حسن | Senior Developer | EMP-003 |
| 6 | ريان الحربي | Frontend Developer | EMP-007 |
| 7 | تركي الشهري | DevOps Engineer | EMP-009 |

في شي تبي تسوّيه بخصوص أحد منهم؟ 😊

**Turn 2 [PASS]** (17.3s)

*User:* `pending approvals`

*Agent:* عندك **3 طلبات إجازة** معلقة تحتاج موافقتك يا Ahmed 👇

| # | الموظف | نوع الإجازة | الفترة | الأيام | السبب |
|---|--------|-------------|--------|--------|-------|
| 1 | Turki Al-Shehri (EMP-009) | 🚨 طارئة | 27 مارس | 1 يوم | طارئة عائلية |
| 2 | Omar Hassan (EMP-003) | 🤒 مرضية | 25-26 مارس | 2 أيام | موعد طبيب + تعافي |
| 3 | Khalid Al-Dossari (EMP-005) | 🌴 سنوية | 6-10 أبريل | 5 أيام | رحلة عائلية لأبها |

تبي تعتمد أو ترفض أي منها؟

**Turn 3 [PASS]** (15.9s)

*User:* `onboarding checklist`

*Agent:* يبدو إنه ما في برنامج onboarding مفعّل لك حالياً، Ahmed. 🤔

يحتمل إما إنه ما اتعيّن لك بعد، أو إنك خلّصته بالكامل! 🎉

تبي أحوّل الموضوع لـ HR عشان يتأكدون ويعيّنون لك البرنامج المناسب؟

**Turn 4 [PASS]** (6.3s)

*User:* `تهيئة الموظف الجديد`

*Agent:* مساء الخير Ahmed! 👋

أهلاً بك، أنا وليد من فريق الموارد البشرية. كيف أقدر أساعدك في موضوع تهيئة الموظف الجديد؟

ممكن أساعدك في عدة أشياء، مثل:

- 📋 **عرض قائمة مهام التهيئة** الخاصة بك
- ✅ **تحديث خطوة** كمنجزة
- 📬 **إرسال رسالة متابعة** (check-in)
- 👀 **الاطلاع على لوحة تحكم التهيئة** إذا كنت مدير

شو تحتاج تسوي؟ 😊

---

### 6. Sticky Agent [PASS] (2/2)

| Turn | Input | Expected | Result | Time |
|------|-------|----------|--------|------|
| 1 | `hello` | Waleed greets the user | **PASS** | 3.5s |
| 2 | `show my team` | Should stay with Waleed (sticky) | **PASS** | 17.4s |

**Full Transcript:**

**Turn 1 [PASS]** (3.5s)

*User:* `hello`

*Agent:* مساء الخير Ahmed! 👋

أهلاً وسهلاً، أنا وليد من فريق الموارد البشرية. كيف أقدر أساعدك اليوم؟ 😊

**Turn 2 [PASS]** (17.4s)

*User:* `show my team`

*Agent:* هذي قائمة فريقك Ahmed، عندك **7 موظفين** 👇

| # | الاسم | المسمى الوظيفي |
|---|-------|----------------|
| 1 | فاطمة الزهراني | HR Manager |
| 2 | خالد الدوسري | Backend Developer |
| 3 | مها السبيعي | Sales Manager |
| 4 | نورة القحطاني | UX Designer |
| 5 | عمر حسن | Senior Developer |
| 6 | ريان الحربي | Frontend Developer |
| 7 | تركي الشهري | DevOps Engineer |

في شي ثاني تبي تعرفه عن الفريق؟ 😊

---

### 7. Error Recovery [FAIL] (1/2)

| Turn | Input | Expected | Result | Time |
|------|-------|----------|--------|------|
| 1 | `check onboarding for employee abc-invalid-id` | Should handle invalid ID gracefully | **FAIL** | 24.1s |
| 2 | `search for Rayan instead` | Should find Rayan and show info | **PASS** | 14.9s |

**Full Transcript:**

**Turn 1 [FAIL]** (24.1s)

*User:* `check onboarding for employee abc-invalid-id`

*Agent:* ما لقينا أي موظف بهذا الاسم أو الرقم يا Ahmed. 🙁

ممكن تتأكد من المعلومات وتجرب مرة ثانية؟ مثلاً:
- **اسم الموظف** كاملاً أو جزء منه
- **رقم الموظف** بالصيغة الصحيحة (مثل: `EMP-005`)

وأنا جاهز أساعدك! 😊

*Failure:* Keywords not found. Response: ما لقينا أي موظف بهذا الاسم أو الرقم يا Ahmed. 🙁

ممكن تتأكد من المعلومات وتجرب مرة ثانية؟ مثلاً:
- **اسم الموظف** كاملاً أو جزء منه
- **رقم الموظف** بالصيغة الصحيحة (مثل: `EMP-005`)

وأنا جاهز أساعدك! 😊

**Turn 2 [PASS]** (14.9s)

*User:* `search for Rayan instead`

*Agent:* لقيت الموظف! هذا هو:

- **الاسم:** ريان الحربي (Rayan Al-Harbi)
- **الرقم الوظيفي:** EMP-007
- **المسمى الوظيفي:** Frontend Developer
- **تاريخ الالتحاق:** 2026-03-10

تبي أشوف له checklist الـ onboarding؟ 😊

---

### 8. Non-Manager Access Denial [FAIL] (0/1)

| Turn | Input | Expected | Result | Time |
|------|-------|----------|--------|------|
| 1 | `show my team` | Should deny — Khalid is not a manager | **FAIL** | 16.8s |

**Full Transcript:**

**Turn 1 [FAIL]** (16.8s)

*User:* `show my team`

*Agent:* يبدو إن حسابك ما يحتوي على موظفين تابعين لك، يعني ما تم تسجيلك كمدير في النظام. 🙂

إذا تعتقد إن في خطأ بالنظام أو عندك فريق فعلاً ومش ظاهر، تواصل مع HR مباشرة وهم يقدرون يصلحون الوضع. هل في شي ثاني أقدر أساعدك فيه؟

*Failure:* Keywords not found. Response: يبدو إن حسابك ما يحتوي على موظفين تابعين لك، يعني ما تم تسجيلك كمدير في النظام. 🙂

إذا تعتقد إن في خطأ بالنظام أو عندك فريق فعلاً ومش ظاهر، تواصل مع HR مباشرة وهم يقدرون يصلحون الوضع. هل في شي ثاني أقدر أساعدك فيه؟

---

## Bugs Found

| # | Severity | Scenario | Turn | Issue |
|---|----------|----------|------|-------|
| 1 | Critical | 1. Onboarding Multi-Turn Flow | Turn 1 | Keywords not found. Response: هذي تفاصيل أونبوردينج **ريان الحربي** (EMP-007) 👇  ---  ### 📊 التقدم العام: 38% (3 من 8 خط |
| 2 | Critical | 7. Error Recovery | Turn 1 | Keywords not found. Response: ما لقينا أي موظف بهذا الاسم أو الرقم يا Ahmed. 🙁  ممكن تتأكد من المعلومات وتجرب مرة ثانية؟ |
| 3 | Critical | 8. Non-Manager Access Denial | Turn 1 | Keywords not found. Response: يبدو إن حسابك ما يحتوي على موظفين تابعين لك، يعني ما تم تسجيلك كمدير في النظام. 🙂  إذا تعت |

## Response Times

- **Average:** 14.5s
- **Min:** 3.5s
- **Max:** 24.1s
- **Slow turns (>15s):** 12

## Recommendations

- Error recovery flow needs work — agent should gracefully handle invalid inputs
- Non-manager denial message should be clearer and more helpful
- Onboarding multi-turn flow has context issues
