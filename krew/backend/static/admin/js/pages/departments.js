/**
 * departments.js — Department CRUD with modal forms.
 */
import { api, hasMinRole } from '../api.js';
import { t } from '../i18n.js';
import { renderTable, showModal, showToast, confirmDialog } from '../components.js';

export default async function loadDepartments() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="page-header">
      <h2 class="page-title" id="deptTitle"></h2>
      <div class="page-actions" id="deptActions"></div>
    </div>
    <div id="deptTable"></div>
  `;

  document.getElementById('deptTitle').textContent = t('dept.title');

  if (hasMinRole('hr_manager')) {
    const actions = document.getElementById('deptActions');
    const btn = document.createElement('button');
    btn.className = 'btn-primary';
    btn.textContent = t('dept.create');
    btn.addEventListener('click', () => openDeptModal());
    actions.appendChild(btn);
  }

  await fetchDepartments();
}

async function fetchDepartments() {
  try {
    const res = await api('/admin/departments');
    if (!res.ok) throw new Error('Failed to load');
    const depts = await res.json();

    const columns = [
      { key: 'name', label: t('dept.name') },
      { key: 'name_ar', label: t('dept.name_ar'), render: (r) => r.name_ar || '—' },
      { key: 'active_employee_count', label: t('dept.employees') },
      { key: 'headcount_budget', label: t('dept.budget'), render: (r) => r.headcount_budget ?? '—' },
    ];

    if (hasMinRole('hr_manager')) {
      columns.push({
        key: '_actions', label: t('dept.actions'), width: '150px', render: (r) => {
          const div = document.createElement('div');
          div.style.display = 'flex';
          div.style.gap = '8px';
          const editBtn = document.createElement('button');
          editBtn.className = 'btn-icon';
          editBtn.textContent = t('dept.edit');
          editBtn.addEventListener('click', (e) => { e.stopPropagation(); openDeptModal(r); });
          const delBtn = document.createElement('button');
          delBtn.className = 'btn-icon btn-danger-subtle';
          delBtn.textContent = t('dept.delete');
          delBtn.addEventListener('click', (e) => { e.stopPropagation(); deleteDept(r); });
          div.append(editBtn, delBtn);
          return div;
        }
      });
    }

    renderTable(document.getElementById('deptTable'), {
      columns,
      rows: depts,
      page: 1,
      totalPages: 1,
    });
  } catch (err) {
    document.getElementById('deptTable').innerHTML = `<div class="card" style="padding:40px;text-align:center;color:var(--red)">${t('common.error')}</div>`;
  }
}

function openDeptModal(dept = null) {
  const isEdit = !!dept;
  const html = `
    <div class="form-group"><label>${t('dept.name')}</label><input id="md_name" /></div>
    <div class="form-group"><label>${t('dept.name_ar')}</label><input id="md_name_ar" dir="rtl" /></div>
    <div class="form-group"><label>${t('dept.budget')}</label><input id="md_budget" type="number" /></div>
  `;

  // Set values safely via DOM after modal is rendered (avoid XSS via value interpolation)
  const _origOnSave = null;

  const modal = showModal(isEdit ? t('dept.edit') : t('dept.create'), html, {
    onSave: async (body) => {
      const name = body.querySelector('#md_name').value.trim();
      const name_ar = body.querySelector('#md_name_ar').value.trim();
      const budget = body.querySelector('#md_budget').value.trim();
      if (!name) { showToast(t('common.error'), 'error'); return; }

      const payload = { name };
      if (name_ar) payload.name_ar = name_ar;
      if (budget) payload.headcount_budget = parseInt(budget, 10);

      try {
        const url = isEdit ? `/admin/departments/${dept.id}` : '/admin/departments';
        const method = isEdit ? 'PUT' : 'POST';
        const res = await api(url, { method, body: JSON.stringify(payload) });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || 'Failed');
        }
        showToast(t('common.success'), 'success');
        fetchDepartments();
      } catch (err) {
        showToast(err.message, 'error');
      }
    },
  });

  // Set input values safely via DOM (not string interpolation) to prevent XSS
  if (dept) {
    modal.body.querySelector('#md_name').value = dept.name || '';
    modal.body.querySelector('#md_name_ar').value = dept.name_ar || '';
    modal.body.querySelector('#md_budget').value = dept.headcount_budget || '';
  }
}

function deleteDept(dept) {
  if (dept.active_employee_count > 0) {
    showToast(t('dept.has_employees'), 'error');
    return;
  }
  confirmDialog(`${t('dept.delete_confirm')}\n\n${dept.name}`, {
    onConfirm: async () => {
      try {
        const res = await api(`/admin/departments/${dept.id}`, { method: 'DELETE' });
        if (res.status === 409) {
          showToast(t('dept.has_employees'), 'error');
          return;
        }
        if (!res.ok && res.status !== 204) throw new Error('Failed');
        showToast(t('common.success'), 'success');
        fetchDepartments();
      } catch (err) {
        showToast(err.message, 'error');
      }
    }
  });
}
