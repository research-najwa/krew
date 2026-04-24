/**
 * dashboard.js — Overview dashboard with stat cards and chart.
 */
import { api } from '../api.js';
import { t } from '../i18n.js';
import { renderStatCard, showToast } from '../components.js';

export default async function loadDashboard() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="stat-row" id="statRow"></div>
    <div class="card" style="margin-top:24px;padding:24px">
      <h3 class="card-title" id="chartTitle"></h3>
      <canvas id="deptChart" height="260"></canvas>
    </div>
  `;

  document.getElementById('chartTitle').textContent = t('dash.dept_headcount');

  const statRow = document.getElementById('statRow');

  // Fetch stats
  try {
    const [statsRes, nitaqatRes] = await Promise.all([
      api('/dashboard/stats'),
      api('/nitaqat/status').catch(() => null),
    ]);

    const stats = statsRes.ok ? await statsRes.json() : {};
    const nitaqat = nitaqatRes && nitaqatRes.ok ? await nitaqatRes.json() : null;

    const saudPct = stats.saudization_percentage != null
      ? stats.saudization_percentage.toFixed(1) + '%'
      : (nitaqat && nitaqat.current_saudization_pct != null ? nitaqat.current_saudization_pct.toFixed(1) + '%' : '—');

    renderStatCard(statRow, {
      label: t('dash.total_employees'),
      value: stats.total_employees ?? '—',
      sub: t('dash.active'),
      color: 'var(--accent)',
    });
    renderStatCard(statRow, {
      label: t('dash.saudization'),
      value: saudPct,
      sub: t('dash.of_workforce'),
      color: 'var(--green)',
    });
    renderStatCard(statRow, {
      label: t('dash.pending_leaves'),
      value: stats.pending_leave_requests ?? '—',
      sub: t('dash.awaiting_review'),
      color: 'var(--orange)',
    });
    renderStatCard(statRow, {
      label: t('dash.open_tickets'),
      value: stats.open_compliance_alerts ?? '—',
      sub: t('dash.need_attention'),
      color: 'var(--red)',
    });
  } catch (err) {
    statRow.innerHTML = `<div style="color:var(--text3);padding:20px">${t('common.error')}</div>`;
  }

  // Fetch departments for chart
  try {
    const deptRes = await api('/admin/departments');
    if (deptRes.ok) {
      const depts = await deptRes.json();
      if (depts.length > 0 && typeof Chart !== 'undefined') {
        const labels = depts.map(d => d.name);
        const data = depts.map(d => d.active_employee_count);
        const ctx = document.getElementById('deptChart').getContext('2d');
        new Chart(ctx, {
          type: 'bar',
          data: {
            labels,
            datasets: [{
              label: t('dept.employees'),
              data,
              backgroundColor: 'rgba(99, 102, 241, 0.7)',
              borderRadius: 6,
              borderSkipped: false,
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
            },
            scales: {
              y: {
                beginAtZero: true,
                ticks: { stepSize: 1, color: '#9ca3af' },
                grid: { color: 'rgba(0,0,0,0.05)' },
              },
              x: {
                ticks: { color: '#9ca3af' },
                grid: { display: false },
              },
            },
          },
        });
      }
    }
  } catch { /* chart is optional */ }
}
