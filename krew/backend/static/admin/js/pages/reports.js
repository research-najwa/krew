/**
 * reports.js — Report tabs with Chart.js visualizations.
 */
import { api } from '../api.js';
import { t } from '../i18n.js';
import { showToast } from '../components.js';

const TABS = ['leave_util', 'headcount', 'saudization', 'agent_perf'];
let activeTab = 'leave_util';
let chartInstance = null;

export default async function loadReports() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="page-header">
      <h2 class="page-title">${t('rep.title')}</h2>
    </div>
    <div class="tabs" id="repTabs"></div>
    <div class="filter-bar" id="repFilters">
      <label>${t('rep.start_date')}</label>
      <input type="date" class="filter-input" id="repStart" />
      <label>${t('rep.end_date')}</label>
      <input type="date" class="filter-input" id="repEnd" />
      <div class="filter-spacer"></div>
      <button class="filter-btn" id="repApply">${t('rep.apply')}</button>
    </div>
    <div class="card" style="padding:24px;margin-top:16px">
      <div id="repContent">
        <canvas id="repChart" height="300"></canvas>
        <div id="repMeta" style="margin-top:16px"></div>
      </div>
      <div id="repEmpty" style="display:none;text-align:center;padding:40px;color:var(--text3)">${t('rep.no_data')}</div>
    </div>
  `;

  // Build tabs
  const tabsEl = document.getElementById('repTabs');
  for (const tab of TABS) {
    const btn = document.createElement('button');
    btn.className = 'tab' + (tab === activeTab ? ' active' : '');
    btn.dataset.tab = tab;
    btn.textContent = t(`rep.${tab}`);
    btn.addEventListener('click', () => {
      activeTab = tab;
      tabsEl.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadReport();
    });
    tabsEl.appendChild(btn);
  }

  document.getElementById('repApply').addEventListener('click', loadReport);
  await loadReport();
}

async function loadReport() {
  const startDate = document.getElementById('repStart').value;
  const endDate = document.getElementById('repEnd').value;
  const content = document.getElementById('repContent');
  const empty = document.getElementById('repEmpty');
  content.style.display = '';
  empty.style.display = 'none';

  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }

  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);

  const endpoints = {
    leave_util: '/reports/leave-utilization',
    headcount: '/reports/headcount',
    saudization: '/nitaqat/status',
    agent_perf: '/reports/agent-performance',
  };

  try {
    const res = await api(`${endpoints[activeTab]}?${params}`);
    if (!res.ok) throw new Error('Failed to load report');
    const data = await res.json();

    if (activeTab === 'leave_util') renderLeaveUtil(data);
    else if (activeTab === 'headcount') renderHeadcount(data);
    else if (activeTab === 'saudization') renderSaudization(data);
    else if (activeTab === 'agent_perf') renderAgentPerf(data);
  } catch (err) {
    content.style.display = 'none';
    empty.style.display = '';
  }
}

function getCtx() {
  return document.getElementById('repChart').getContext('2d');
}

function renderLeaveUtil(data) {
  const meta = document.getElementById('repMeta');
  meta.innerHTML = '';

  const byType = data.by_type || data.leave_by_type || [];
  if (byType.length === 0 && typeof Chart !== 'undefined') {
    document.getElementById('repContent').style.display = 'none';
    document.getElementById('repEmpty').style.display = '';
    return;
  }

  if (typeof Chart !== 'undefined') {
    chartInstance = new Chart(getCtx(), {
      type: 'doughnut',
      data: {
        labels: byType.map(d => d.leave_type || d.type || 'Unknown'),
        datasets: [{
          data: byType.map(d => d.total_days || d.count || 0),
          backgroundColor: ['#6366f1', '#f59e0b', '#ef4444', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#6b7280'],
        }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
    });
  }

  if (data.summary) {
    const s = data.summary;
    meta.innerHTML = `
      <div class="stat-row" style="margin-top:16px">
        <div class="stat-card"><div class="sc-label">Total Days Used</div><div class="sc-value" style="color:var(--accent)">${s.total_days_used || 0}</div></div>
        <div class="stat-card"><div class="sc-label">Avg Days/Employee</div><div class="sc-value" style="color:var(--green)">${(s.avg_days_per_employee || 0).toFixed(1)}</div></div>
      </div>
    `;
  }
}

function renderHeadcount(data) {
  const meta = document.getElementById('repMeta');
  meta.innerHTML = '';

  const byDept = data.by_department || [];
  if (typeof Chart !== 'undefined' && byDept.length > 0) {
    chartInstance = new Chart(getCtx(), {
      type: 'bar',
      data: {
        labels: byDept.map(d => d.department || d.name || 'Unknown'),
        datasets: [{
          label: 'Headcount',
          data: byDept.map(d => d.count || d.active || 0),
          backgroundColor: 'rgba(99, 102, 241, 0.7)',
          borderRadius: 6,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { stepSize: 1, color: '#9ca3af' }, grid: { color: 'rgba(0,0,0,0.05)' } }, x: { ticks: { color: '#9ca3af' }, grid: { display: false } } },
      },
    });
  }

  if (data.totals || data.summary) {
    const s = data.totals || data.summary || {};
    meta.innerHTML = `
      <div class="stat-row" style="margin-top:16px">
        <div class="stat-card"><div class="sc-label">Total Active</div><div class="sc-value" style="color:var(--accent)">${s.active || s.total_active || 0}</div></div>
        <div class="stat-card"><div class="sc-label">Saudi</div><div class="sc-value" style="color:var(--green)">${s.saudi || 0}</div></div>
        <div class="stat-card"><div class="sc-label">Non-Saudi</div><div class="sc-value" style="color:var(--orange)">${s.non_saudi || 0}</div></div>
      </div>
    `;
  }
}

function renderSaudization(data) {
  const meta = document.getElementById('repMeta');
  meta.innerHTML = '';

  const pct = data.current_saudization_pct ?? data.saudization_percentage ?? 0;
  const band = data.current_band || data.band || '—';

  if (typeof Chart !== 'undefined') {
    chartInstance = new Chart(getCtx(), {
      type: 'doughnut',
      data: {
        labels: ['Saudi', 'Non-Saudi'],
        datasets: [{
          data: [data.saudi_count || 0, data.non_saudi_count || 0],
          backgroundColor: ['#10b981', '#f59e0b'],
        }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
    });
  }

  meta.innerHTML = `
    <div class="stat-row" style="margin-top:16px">
      <div class="stat-card"><div class="sc-label">Saudization %</div><div class="sc-value" style="color:var(--green)">${pct.toFixed(1)}%</div></div>
      <div class="stat-card"><div class="sc-label">Nitaqat Band</div><div class="sc-value" style="color:var(--accent)">${band}</div></div>
      <div class="stat-card"><div class="sc-label">Total Employees</div><div class="sc-value">${data.total_employees || (data.saudi_count || 0) + (data.non_saudi_count || 0)}</div></div>
    </div>
  `;
}

function renderAgentPerf(data) {
  const meta = document.getElementById('repMeta');
  meta.innerHTML = '';

  const agents = data.agents || data.by_agent || [];
  if (typeof Chart !== 'undefined' && agents.length > 0) {
    chartInstance = new Chart(getCtx(), {
      type: 'bar',
      data: {
        labels: agents.map(a => a.agent || a.name || 'Unknown'),
        datasets: [
          { label: 'Messages', data: agents.map(a => a.messages || a.message_count || 0), backgroundColor: 'rgba(99, 102, 241, 0.7)', borderRadius: 6 },
          { label: 'Resolutions', data: agents.map(a => a.resolutions || a.resolved_count || 0), backgroundColor: 'rgba(16, 185, 129, 0.7)', borderRadius: 6 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' } },
        scales: { y: { beginAtZero: true, ticks: { color: '#9ca3af' }, grid: { color: 'rgba(0,0,0,0.05)' } }, x: { ticks: { color: '#9ca3af' }, grid: { display: false } } },
      },
    });
  }

  if (data.summary || data.totals) {
    const s = data.summary || data.totals || {};
    meta.innerHTML = `
      <div class="stat-row" style="margin-top:16px">
        <div class="stat-card"><div class="sc-label">Total Messages</div><div class="sc-value" style="color:var(--accent)">${s.total_messages || 0}</div></div>
        <div class="stat-card"><div class="sc-label">Resolution Rate</div><div class="sc-value" style="color:var(--green)">${(s.resolution_rate || 0).toFixed(0)}%</div></div>
        <div class="stat-card"><div class="sc-label">Escalation Rate</div><div class="sc-value" style="color:var(--orange)">${(s.escalation_rate || 0).toFixed(0)}%</div></div>
      </div>
    `;
  }
}
