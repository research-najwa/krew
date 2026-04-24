/**
 * leaves.js — Leave requests list with approve/reject actions.
 */
import { api, hasMinRole } from '../api.js';
import { t } from '../i18n.js';
import { renderTable, badge, showModal, showToast } from '../components.js';

export default async function loadLeaves() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="page-header">
      <h2 class="page-title" id="leaveTitle"></h2>
    </div>
    <div class="filter-bar" id="leaveFilters">
      <select class="filter-select" id="leaveStatus">
        <option value=""></option>
        <option value="pending"></option>
        <option value="approved"></option>
        <option value="rejected"></option>
        <option value="cancelled"></option>
      </select>
      <input type="date" class="filter-input" id="leaveDateFrom" />
      <input type="date" class="filter-input" id="leaveDateTo" />
      <div class="filter-spacer"></div>
      <button class="filter-btn" id="leaveApply"></button>
      <button class="filter-reset" id="leaveReset"></button>
    </div>
    <div id="leaveTable"></div>
  `;

  applyLabels();

  document.getElementById('leaveApply').addEventListener('click', fetchLeaves);
  document.getElementById('leaveReset').addEventListener('click', () => {
    document.getElementById('leaveStatus').value = '';
    document.getElementById('leaveDateFrom').value = '';
    document.getElementById('leaveDateTo').value = '';
    fetchLeaves();
  });

  await fetchLeaves();
}

function applyLabels() {
  document.getElementById('leaveTitle').textContent = t('leave.title');
  const ss = document.getElementById('leaveStatus');
  ss.options[0].textContent = t('leave.all_statuses');
  ss.options[1].textContent = t('leave.pending');
  ss.options[2].textContent = t('leave.approved');
  ss.options[3].textContent = t('leave.rejected');
  ss.options[4].textContent = t('leave.cancelled');
  document.getElementById('leaveApply').textContent = t('common.filter');
  document.getElementById('leaveReset').textContent = t('common.reset');
}

async function fetchLeaves() {
  const params = new URLSearchParams();
  const status = document.getElementById('leaveStatus').value;
  const from = document.getElementById('leaveDateFrom').value;
  const to = document.getElementById('leaveDateTo').value;
  if (status) params.set('status', status);
  if (from) params.set('date_from', from);
  if (to) params.set('date_to', to);

  try {
    const res = await api(`/admin/leave-requests?${params}`);
    if (!res.ok) throw new Error('Failed to load');
    const leaves = await res.json();

    const statusMap = { pending: 'pending', approved: 'approved', rejected: 'rejected', cancelled: 'cancelled' };
    const statusLabel = {
      pending: t('leave.pending'), approved: t('leave.approved'),
      rejected: t('leave.rejected'), cancelled: t('leave.cancelled'),
    };
    const typeNames = {
      annual: 'Annual', sick: 'Sick', emergency: 'Emergency',
      hajj: 'Hajj', maternity: 'Maternity', paternity: 'Paternity',
      bereavement: 'Bereavement', unpaid: 'Unpaid',
    };

    const columns = [
      { key: 'employee_name', label: t('leave.employee'), render: (r) => {
        const div = document.createElement('div');
        const name = document.createElement('div');
        name.className = 'td-name';
        name.textContent = r.employee_name;
        const sub = document.createElement('div');
        sub.className = 'td-sub';
        sub.textContent = r.employee_number || '';
        div.append(name, sub);
        return div;
      }},
      { key: 'department', label: t('emp.department'), render: (r) => r.department || '—' },
      { key: 'leave_type', label: t('leave.type'), render: (r) => {
        const s = document.createElement('span');
        s.className = `type-badge type-${r.leave_type}`;
        s.textContent = typeNames[r.leave_type] || r.leave_type;
        return s;
      }},
      { key: 'start_date', label: t('leave.dates'), render: (r) => {
        const d = document.createElement('div');
        d.textContent = fmtDate(r.start_date);
        const s = document.createElement('div');
        s.className = 'td-sub';
        s.textContent = 'to ' + fmtDate(r.end_date);
        d.appendChild(s);
        return d;
      }},
      { key: 'business_days', label: t('leave.days') },
      { key: 'status', label: t('leave.status'), render: (r) => {
        return badge(statusLabel[r.status] || r.status, statusMap[r.status] || 'default');
      }},
      { key: 'reason', label: t('leave.reason'), render: (r) => {
        const s = document.createElement('span');
        s.textContent = r.reason || '—';
        s.style.maxWidth = '160px';
        s.style.display = 'inline-block';
        s.style.overflow = 'hidden';
        s.style.textOverflow = 'ellipsis';
        s.style.whiteSpace = 'nowrap';
        s.title = r.reason || '';
        return s;
      }},
    ];

    if (hasMinRole('hr_manager')) {
      columns.push({
        key: '_actions', label: t('leave.actions'), width: '160px', render: (r) => {
          if (r.status !== 'pending') return '—';
          const div = document.createElement('div');
          div.style.display = 'flex';
          div.style.gap = '6px';
          const appBtn = document.createElement('button');
          appBtn.className = 'btn-approve';
          appBtn.textContent = t('leave.approve');
          appBtn.addEventListener('click', (e) => { e.stopPropagation(); approveLeave(r.id, appBtn); });
          const rejBtn = document.createElement('button');
          rejBtn.className = 'btn-reject';
          rejBtn.textContent = t('leave.reject');
          rejBtn.addEventListener('click', (e) => { e.stopPropagation(); rejectLeave(r); });
          div.append(appBtn, rejBtn);
          return div;
        }
      });
    }

    renderTable(document.getElementById('leaveTable'), {
      columns,
      rows: leaves,
      page: 1,
      totalPages: 1,
    });
  } catch (err) {
    document.getElementById('leaveTable').innerHTML = `<div class="card" style="padding:40px;text-align:center;color:var(--red)">${t('common.error')}</div>`;
  }
}

async function approveLeave(id, btn) {
  btn.disabled = true;
  btn.textContent = '...';
  try {
    const res = await api(`/admin/leave-requests/${id}/approve`, { method: 'PATCH' });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || 'Failed');
    }
    showToast(t('leave.approved'), 'success');
    fetchLeaves();
  } catch (err) {
    showToast(err.message, 'error');
    btn.disabled = false;
    btn.textContent = t('leave.approve');
  }
}

function rejectLeave(req) {
  const nameHtml = `<p id="rejectEmpName" style="font-size:13px;color:var(--text2);margin-bottom:12px"></p>`;
  const modal = showModal(t('leave.reject_title'), `
    ${nameHtml}
    <textarea id="rejectReason" class="modal-textarea" placeholder="${t('leave.reject_reason')}" rows="3"></textarea>
  `, {
    saveLabel: t('leave.reject'),
    onSave: async (body) => {
      const reason = body.querySelector('#rejectReason').value.trim();
      try {
        const res = await api(`/admin/leave-requests/${req.id}/reject`, {
          method: 'PATCH',
          body: JSON.stringify({ reason: reason || 'Rejected by HR' }),
        });
        if (!res.ok) {
          const d = await res.json().catch(() => ({}));
          throw new Error(d.detail || 'Failed');
        }
        showToast(t('leave.rejected'), 'success');
        fetchLeaves();
      } catch (err) {
        showToast(err.message, 'error');
      }
    }
  });

  // Set employee name safely via textContent (not innerHTML) to prevent XSS
  const empNameEl = modal.body.querySelector('#rejectEmpName');
  if (empNameEl) empNameEl.textContent = req.employee_name;
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
