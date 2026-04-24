/**
 * employee-detail.js — Create/edit employee form.
 */
import { api, hasMinRole } from '../api.js';
import { t } from '../i18n.js';
import { navigate } from '../router.js';
import { showToast } from '../components.js';

export default async function loadEmployeeDetail(params) {
  const isNew = params.id === 'new';
  const app = document.getElementById('app');

  app.innerHTML = `
    <div class="page-header">
      <button class="btn-back" id="backBtn"></button>
      <h2 class="page-title" id="edTitle"></h2>
    </div>
    <div class="card form-card" id="empForm">
      <div class="form-section">
        <h4>${t('empd.first_name')}</h4>
        <div class="form-grid">
          <div class="form-group"><label>${t('empd.first_name')}</label><input id="f_first_name" /></div>
          <div class="form-group"><label>${t('empd.last_name')}</label><input id="f_last_name" /></div>
          <div class="form-group"><label>${t('empd.first_name_ar')}</label><input id="f_first_name_ar" dir="rtl" /></div>
          <div class="form-group"><label>${t('empd.last_name_ar')}</label><input id="f_last_name_ar" dir="rtl" /></div>
        </div>
      </div>
      <div class="form-section">
        <h4>${t('emp.email')} / ${t('empd.phone')}</h4>
        <div class="form-grid">
          <div class="form-group"><label>${t('emp.number')}</label><input id="f_employee_number" /></div>
          <div class="form-group"><label>${t('emp.email')}</label><input id="f_email" type="email" /></div>
          <div class="form-group"><label>${t('empd.phone')}</label><input id="f_phone" /></div>
          <div class="form-group"><label>${t('empd.national_id')}</label><input id="f_national_id" /></div>
          <div class="form-group"><label>${t('empd.whatsapp')}</label><input id="f_whatsapp_number" /></div>
        </div>
      </div>
      <div class="form-section">
        <h4>${t('emp.job_title')}</h4>
        <div class="form-grid">
          <div class="form-group"><label>${t('emp.job_title')}</label><input id="f_job_title" /></div>
          <div class="form-group"><label>${t('emp.department')}</label><select id="f_department_id"><option value="">—</option></select></div>
          <div class="form-group"><label>${t('empd.manager')}</label><select id="f_manager_id"><option value="">—</option></select></div>
          <div class="form-group"><label>${t('empd.hire_date')}</label><input id="f_hire_date" type="date" /></div>
          <div class="form-group"><label>${t('empd.salary')}</label><input id="f_salary_sar" type="number" /></div>
        </div>
      </div>
      <div class="form-section">
        <h4>${t('empd.contract_type')}</h4>
        <div class="form-grid">
          <div class="form-group"><label>${t('empd.gender')}</label>
            <select id="f_gender"><option value="">—</option><option value="male">${t('empd.male')}</option><option value="female">${t('empd.female')}</option></select>
          </div>
          <div class="form-group"><label>${t('empd.contract_type')}</label>
            <select id="f_contract_type"><option value="full_time">Full Time</option><option value="part_time">Part Time</option><option value="contract">Contract</option></select>
          </div>
          <div class="form-group"><label>${t('empd.work_mode')}</label>
            <select id="f_work_mode"><option value="onsite">Onsite</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option></select>
          </div>
          <div class="form-group"><label>${t('empd.is_saudi')}</label>
            <select id="f_is_saudi"><option value="true">${t('common.yes')}</option><option value="false">${t('common.no')}</option></select>
          </div>
          <div class="form-group"><label>${t('empd.language')}</label>
            <select id="f_preferred_language"><option value="ar">Arabic</option><option value="en">English</option></select>
          </div>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn-primary" id="saveBtn">${t('empd.save')}</button>
      </div>
    </div>
  `;

  document.getElementById('edTitle').textContent = isNew ? t('empd.new_title') : t('empd.edit_title');
  document.getElementById('backBtn').textContent = t('empd.back');
  document.getElementById('backBtn').addEventListener('click', () => navigate('#/employees'));

  // Load dropdowns
  const [deptRes, empRes] = await Promise.all([
    api('/admin/departments').catch(() => null),
    api('/admin/employees?per_page=200').catch(() => null),
  ]);

  if (deptRes && deptRes.ok) {
    const depts = await deptRes.json();
    const sel = document.getElementById('f_department_id');
    for (const d of depts) {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = d.name;
      sel.appendChild(opt);
    }
  }

  if (empRes && empRes.ok) {
    const emps = await empRes.json();
    const sel = document.getElementById('f_manager_id');
    for (const e of (emps.items || [])) {
      if (!isNew && e.id === params.id) continue;
      const opt = document.createElement('option');
      opt.value = e.id;
      opt.textContent = e.full_name;
      sel.appendChild(opt);
    }
  }

  // Load existing employee
  if (!isNew) {
    try {
      const res = await api(`/admin/employees/${params.id}`);
      if (!res.ok) throw new Error('Not found');
      const emp = await res.json();
      fillForm(emp);
    } catch (err) {
      showToast(t('common.error'), 'error');
      navigate('#/employees');
      return;
    }
  }

  // Save handler
  document.getElementById('saveBtn').addEventListener('click', async () => {
    const data = readForm();
    const btn = document.getElementById('saveBtn');
    btn.disabled = true;

    try {
      const url = isNew ? '/admin/employees' : `/admin/employees/${params.id}`;
      const method = isNew ? 'POST' : 'PUT';
      const res = await api(url, { method, body: JSON.stringify(data) });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Save failed');
      }
      showToast(t('common.success'), 'success');
      navigate('#/employees');
    } catch (err) {
      showToast(err.message, 'error');
      btn.disabled = false;
    }
  });
}

const FIELDS = [
  'first_name', 'last_name', 'first_name_ar', 'last_name_ar',
  'employee_number', 'email', 'phone', 'national_id', 'whatsapp_number',
  'job_title', 'department_id', 'manager_id', 'hire_date', 'salary_sar',
  'gender', 'contract_type', 'work_mode', 'is_saudi', 'preferred_language',
];

function fillForm(emp) {
  for (const f of FIELDS) {
    const el = document.getElementById(`f_${f}`);
    if (!el) continue;
    let val = emp[f];
    if (val === null || val === undefined) val = '';
    if (f === 'is_saudi') val = String(val);
    el.value = val;
  }
}

function readForm() {
  const data = {};
  for (const f of FIELDS) {
    const el = document.getElementById(`f_${f}`);
    if (!el) continue;
    let val = el.value.trim();
    if (!val && f !== 'is_saudi') continue;
    if (f === 'salary_sar') { data[f] = parseInt(val, 10) || null; continue; }
    if (f === 'is_saudi') { data[f] = val === 'true'; continue; }
    if (f === 'department_id' || f === 'manager_id') {
      if (val) data[f] = val; continue;
    }
    data[f] = val;
  }
  return data;
}
