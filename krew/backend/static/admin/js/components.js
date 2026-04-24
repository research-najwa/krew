/**
 * components.js — Reusable UI components.
 */
import { t } from './i18n.js';

/* ── Paginated Table ─────────────────────────────────────────────── */

/**
 * Render a paginated data table.
 * @param {HTMLElement} container
 * @param {Object} opts - { columns, rows, page, totalPages, onPageChange, onRowClick }
 *   columns: [{key, label, render?}]
 *   rows: array of objects
 */
export function renderTable(container, { columns, rows, page = 1, totalPages = 1, onPageChange, onRowClick }) {
  container.innerHTML = '';

  const wrap = document.createElement('div');
  wrap.className = 'table-wrap';

  const table = document.createElement('table');
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  for (const col of columns) {
    const th = document.createElement('th');
    th.textContent = col.label;
    if (col.width) th.style.width = col.width;
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  if (rows.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = columns.length;
    td.innerHTML = `<div class="empty-table">${t('common.no_data')}</div>`;
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    for (const row of rows) {
      const tr = document.createElement('tr');
      if (onRowClick) {
        tr.style.cursor = 'pointer';
        tr.addEventListener('click', (e) => {
          // Don't trigger row click if user clicked a button
          if (e.target.closest('button')) return;
          onRowClick(row);
        });
      }
      for (const col of columns) {
        const td = document.createElement('td');
        if (col.render) {
          const content = col.render(row);
          if (content instanceof HTMLElement) {
            td.appendChild(content);
          } else {
            td.textContent = content;
          }
        } else {
          td.textContent = row[col.key] ?? '—';
        }
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);

  // Pagination
  if (totalPages > 1) {
    const pager = document.createElement('div');
    pager.className = 'pagination';
    pager.innerHTML = `
      <button class="pager-btn" id="pg-prev" ${page <= 1 ? 'disabled' : ''}>${t('common.prev')}</button>
      <span class="pager-info">${t('common.page')} ${page} ${t('common.of')} ${totalPages}</span>
      <button class="pager-btn" id="pg-next" ${page >= totalPages ? 'disabled' : ''}>${t('common.next')}</button>
    `;
    container.appendChild(pager);
    pager.querySelector('#pg-prev').addEventListener('click', () => onPageChange && onPageChange(page - 1));
    pager.querySelector('#pg-next').addEventListener('click', () => onPageChange && onPageChange(page + 1));
  }
}

/* ── Modal ────────────────────────────────────────────────────────── */

export function showModal(title, contentHTML, { onSave, saveLabel, showFooter = true } = {}) {
  // Remove existing modal
  const existing = document.getElementById('krew-modal');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'krew-modal';
  overlay.className = 'modal-overlay open';

  const modal = document.createElement('div');
  modal.className = 'modal';

  const header = document.createElement('div');
  header.className = 'modal-header';
  const h3 = document.createElement('h3');
  h3.textContent = title;
  header.appendChild(h3);

  const body = document.createElement('div');
  body.className = 'modal-body';
  body.innerHTML = contentHTML;

  modal.appendChild(header);
  modal.appendChild(body);

  if (showFooter) {
    const footer = document.createElement('div');
    footer.className = 'modal-footer';
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'modal-btn modal-btn-cancel';
    cancelBtn.textContent = t('common.cancel');
    cancelBtn.addEventListener('click', () => overlay.remove());
    footer.appendChild(cancelBtn);

    if (onSave) {
      const saveBtn = document.createElement('button');
      saveBtn.className = 'modal-btn modal-btn-save';
      saveBtn.textContent = saveLabel || t('common.save');
      saveBtn.addEventListener('click', () => {
        onSave(body);
        overlay.remove();
      });
      footer.appendChild(saveBtn);
    }
    modal.appendChild(footer);
  }

  overlay.appendChild(modal);
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });
  document.body.appendChild(overlay);

  // Focus first input
  const firstInput = body.querySelector('input, select, textarea');
  if (firstInput) firstInput.focus();

  return { overlay, body, close: () => overlay.remove() };
}

/* ── Toast ────────────────────────────────────────────────────────── */

let toastTimer = null;

export function showToast(message, type = 'info') {
  let toast = document.getElementById('krew-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'krew-toast';
    toast.className = 'toast';
    document.body.appendChild(toast);
  }

  toast.textContent = message;
  toast.className = 'toast';
  if (type === 'error') toast.classList.add('toast-error');
  if (type === 'success') toast.classList.add('toast-success');

  clearTimeout(toastTimer);
  requestAnimationFrame(() => toast.classList.add('visible'));
  toastTimer = setTimeout(() => toast.classList.remove('visible'), 3500);
}

/* ── Confirm Dialog ──────────────────────────────────────────────── */

export function confirmDialog(message, { onConfirm }) {
  const { body, close } = showModal(t('common.confirm'), `<p style="font-size:14px;color:var(--text);line-height:1.6">${escapeHtml(message)}</p>`, {
    onSave: () => {
      close();
      onConfirm();
    },
    saveLabel: t('common.confirm'),
  });
}

/* ── Stat Card ───────────────────────────────────────────────────── */

export function renderStatCard(container, { label, value, sub, color }) {
  const card = document.createElement('div');
  card.className = 'stat-card';
  const lbl = document.createElement('div');
  lbl.className = 'sc-label';
  lbl.textContent = label;
  const val = document.createElement('div');
  val.className = 'sc-value';
  val.style.color = color || 'var(--text)';
  val.textContent = value;
  const s = document.createElement('div');
  s.className = 'sc-sub';
  s.textContent = sub || '';
  card.append(lbl, val, s);
  container.appendChild(card);
  return card;
}

/* ── Badge ────────────────────────────────────────────────────────── */

export function badge(text, variant = 'default') {
  const span = document.createElement('span');
  span.className = `badge badge-${variant}`;
  const dot = document.createElement('span');
  dot.className = 'badge-dot';
  span.appendChild(dot);
  const txt = document.createTextNode(text);
  span.appendChild(txt);
  return span;
}

/* ── Utility ──────────────────────────────────────────────────────── */

export function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text || '';
  return d.innerHTML;
}
