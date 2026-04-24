/**
 * settings.js — Tenant settings form.
 */
import { api } from '../api.js';
import { t } from '../i18n.js';
import { showToast } from '../components.js';

export default async function loadSettings() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="page-header">
      <h2 class="page-title">${t('set.title')}</h2>
    </div>
    <div class="card form-card">
      <div class="form-grid">
        <div class="form-group"><label>${t('set.name')}</label><input id="s_name" /></div>
        <div class="form-group"><label>${t('set.name_ar')}</label><input id="s_name_ar" dir="rtl" /></div>
        <div class="form-group"><label>${t('set.domain')}</label><input id="s_domain" disabled /></div>
        <div class="form-group"><label>${t('set.plan')}</label><input id="s_plan" disabled /></div>
        <div class="form-group"><label>${t('set.cr_number')}</label><input id="s_cr_number" /></div>
        <div class="form-group"><label>${t('set.gosi_number')}</label><input id="s_gosi_number" /></div>
      </div>
      <div class="form-actions">
        <button class="btn-primary" id="saveSettings">${t('set.save')}</button>
      </div>
    </div>
  `;

  // Load tenant data
  try {
    const res = await api('/admin/tenant');
    if (!res.ok) throw new Error('Failed to load');
    const tenant = await res.json();
    document.getElementById('s_name').value = tenant.name || '';
    document.getElementById('s_name_ar').value = tenant.name_ar || '';
    document.getElementById('s_domain').value = tenant.domain || '';
    document.getElementById('s_plan').value = tenant.plan || '';
    document.getElementById('s_cr_number').value = tenant.cr_number || '';
    document.getElementById('s_gosi_number').value = tenant.gosi_number || '';
  } catch (err) {
    showToast(t('common.error'), 'error');
  }

  // Save handler
  document.getElementById('saveSettings').addEventListener('click', async () => {
    const btn = document.getElementById('saveSettings');
    btn.disabled = true;
    const payload = {};
    const name = document.getElementById('s_name').value.trim();
    const name_ar = document.getElementById('s_name_ar').value.trim();
    const cr = document.getElementById('s_cr_number').value.trim();
    const gosi = document.getElementById('s_gosi_number').value.trim();
    if (name) payload.name = name;
    if (name_ar) payload.name_ar = name_ar;
    if (cr) payload.cr_number = cr;
    if (gosi) payload.gosi_number = gosi;

    try {
      const res = await api('/admin/tenant', { method: 'PUT', body: JSON.stringify(payload) });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || 'Save failed');
      }
      showToast(t('common.success'), 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      btn.disabled = false;
    }
  });
}
