/**
 * employees.js — Employee list with search, filters, pagination.
 */
import { api, hasMinRole } from '../api.js';
import { t } from '../i18n.js';
import { navigate } from '../router.js';
import { renderTable, badge, showToast, confirmDialog } from '../components.js';

let currentPage = 1;
let departments = [];

export default async function loadEmployees() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="page-header">
      <h2 class="page-title" id="empTitle"></h2>
      <div class="page-actions" id="empActions"></div>
    </div>
    <div class="filter-bar" id="empFilters">
      <input type="text" class="filter-input" id="empSearch" style="min-width:220px" />
      <select class="filter-select" id="empStatus">
        <option value=""></option>
        <option value="active"></option>
        <option value="terminated"></option>
        <option value="on_leave"></option>
        <option value="probation"></option>
      </select>
      <select class="filter-select" id="empDept"><option value=""></option></select>
      <select class="filter-select" id="empNat">
        <option value=""></option>
        <option value="true"></option>
        <option value="false"></option>
      </select>
      <div class="filter-spacer"></div>
      <button class="filter-btn" id="empApply"></button>
      <button class="filter-reset" id="empReset"></button>
    </div>
    <div id="empTable"></div>
  `;

  applyLabels();
  currentPage = 1;

  // Load departments for filter
  try {
    const res = await api('/admin/departments');
    if (res.ok) departments = await res.json();
  } catch { departments = []; }

  const deptSelect = document.getElementById('empDept');
  for (const d of departments) {
    const opt = document.createElement('option');
    opt.value = d.id;
    opt.textContent = d.name;
    deptSelect.appendChild(opt);
  }

  // Actions
  const actions = document.getElementById('empActions');
  if (hasMinRole('hr_manager')) {
    actions.innerHTML = `
      <button class="btn-secondary" id="btnImport">${t('emp.import')}</button>
      <button class="btn-secondary" id="btnExport">${t('emp.export')}</button>
      <button class="btn-primary" id="btnCreate">${t('emp.create')}</button>
    `;
    document.getElementById('btnCreate').addEventListener('click', () => navigate('#/employees/new'));
    document.getElementById('btnExport').addEventListener('click', exportCSV);
    document.getElementById('btnImport').addEventListener('click', importCSV);
  }

  // Events
  document.getElementById('empApply').addEventListener('click', () => { currentPage = 1; fetchEmployees(); });
  document.getElementById('empReset').addEventListener('click', resetFilters);
  document.getElementById('empSearch').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { currentPage = 1; fetchEmployees(); }
  });

  await fetchEmployees();
}

function applyLabels() {
  document.getElementById('empTitle').textContent = t('emp.title');
  document.getElementById('empSearch').placeholder = t('emp.search');
  const statusSel = document.getElementById('empStatus');
  statusSel.options[0].textContent = t('emp.all_statuses');
  statusSel.options[1].textContent = t('common.active');
  statusSel.options[2].textContent = t('common.terminated');
  statusSel.options[3].textContent = t('common.on_leave');
  statusSel.options[4].textContent = t('common.probation');
  document.getElementById('empDept').options[0].textContent = t('emp.all_departments');
  const natSel = document.getElementById('empNat');
  natSel.options[0].textContent = t('emp.all_nationalities');
  natSel.options[1].textContent = t('emp.saudi');
  natSel.options[2].textContent = t('emp.non_saudi');
  document.getElementById('empApply').textContent = t('common.filter');
  document.getElementById('empReset').textContent = t('common.reset');
}

async function fetchEmployees() {
  const params = new URLSearchParams();
  params.set('page', currentPage);
  params.set('per_page', '20');
  const search = document.getElementById('empSearch').value.trim();
  const status = document.getElementById('empStatus').value;
  const dept = document.getElementById('empDept').value;
  const nat = document.getElementById('empNat').value;
  if (search) params.set('search', search);
  if (status) params.set('status', status);
  if (dept) params.set('department_id', dept);
  if (nat) params.set('is_saudi', nat);

  try {
    const res = await api(`/admin/employees?${params}`);
    if (!res.ok) throw new Error('Failed to load');
    const data = await res.json();

    const statusMap = { active: 'approved', terminated: 'rejected', on_leave: 'pending', probation: 'pending' };
    const statusLabel = { active: t('common.active'), terminated: t('common.terminated'), on_leave: t('common.on_leave'), probation: t('common.probation') };

    const columns = [
      { key: 'employee_number', label: t('emp.number'), width: '100px' },
      { key: 'full_name', label: t('emp.name'), render: (r) => {
        const div = document.createElement('div');
        const name = document.createElement('div');
        name.className = 'td-name';
        name.textContent = r.full_name;
        const sub = document.createElement('div');
        sub.className = 'td-sub';
        sub.textContent = r.email;
        div.append(name, sub);
        return div;
      }},
      { key: 'job_title', label: t('emp.job_title') },
      { key: 'department_id', label: t('emp.department'), render: (r) => {
        const dept = departments.find(d => d.id === r.department_id);
        return dept ? dept.name : '—';
      }},
      { key: 'status', label: t('emp.status'), render: (r) => {
        return badge(statusLabel[r.status] || r.status, statusMap[r.status] || 'default');
      }},
      { key: 'is_saudi', label: t('emp.nationality'), render: (r) => r.is_saudi ? t('emp.saudi') : t('emp.non_saudi') },
    ];

    if (hasMinRole('hr_manager')) {
      columns.push({
        key: '_actions', label: '', width: '80px', render: (r) => {
          if (r.status === 'terminated') return '';
          const btn = document.createElement('button');
          btn.className = 'btn-icon btn-danger-subtle';
          btn.title = t('common.delete');
          btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteEmployee(r);
          });
          return btn;
        }
      });
    }

    renderTable(document.getElementById('empTable'), {
      columns,
      rows: data.items,
      page: data.page,
      totalPages: data.pages,
      onPageChange: (p) => { currentPage = p; fetchEmployees(); },
      onRowClick: (r) => navigate(`#/employees/${r.id}`),
    });
  } catch (err) {
    document.getElementById('empTable').innerHTML = `<div class="card" style="padding:40px;text-align:center;color:var(--red)">${t('common.error')}</div>`;
  }
}

function resetFilters() {
  document.getElementById('empSearch').value = '';
  document.getElementById('empStatus').value = '';
  document.getElementById('empDept').value = '';
  document.getElementById('empNat').value = '';
  currentPage = 1;
  fetchEmployees();
}

async function deleteEmployee(emp) {
  confirmDialog(`${t('emp.delete_confirm')}\n\n${emp.full_name}`, {
    onConfirm: async () => {
      try {
        const res = await api(`/admin/employees/${emp.id}`, { method: 'DELETE' });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || 'Failed');
        }
        showToast(t('common.success'), 'success');
        fetchEmployees();
      } catch (err) {
        showToast(err.message, 'error');
      }
    }
  });
}

async function exportCSV() {
  try {
    const res = await api('/admin/employees/export');
    if (!res.ok) throw new Error('Export failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'employees.csv';
    a.click();
    URL.revokeObjectURL(url);
    showToast(t('common.success'), 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function importCSV() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.csv';
  input.addEventListener('change', async () => {
    const file = input.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await api('/admin/employees/import', { method: 'POST', body: formData });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Import failed');
      }
      const data = await res.json();
      showToast(`Imported ${data.created} employees`, 'success');
      fetchEmployees();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
  input.click();
}
