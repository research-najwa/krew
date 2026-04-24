/**
 * login.js — Login page.
 */
import { api, setTokens, isLoggedIn } from '../api.js';
import { t } from '../i18n.js';
import { navigate } from '../router.js';
import { showToast } from '../components.js';

export default async function loadLogin() {
  if (isLoggedIn()) {
    navigate('#/dashboard');
    return;
  }

  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="login-page">
      <div class="login-card">
        <div class="login-logo">Krew</div>
        <p class="login-sub" id="loginSub"></p>
        <form id="loginForm" autocomplete="on">
          <div class="form-group">
            <label id="lbl-email"></label>
            <input type="email" id="loginEmail" required autocomplete="email" />
          </div>
          <div class="form-group">
            <label id="lbl-pass"></label>
            <input type="password" id="loginPassword" required autocomplete="current-password" />
          </div>
          <div id="loginError" class="login-error" style="display:none"></div>
          <button type="submit" class="btn-primary btn-block" id="loginBtn"></button>
        </form>
      </div>
    </div>
  `;

  // Apply i18n
  document.getElementById('lbl-email').textContent = t('login.email');
  document.getElementById('lbl-pass').textContent = t('login.password');
  document.getElementById('loginBtn').textContent = t('login.submit');
  document.getElementById('loginSub').textContent = t('login.subtitle');

  // Hide sidebar/topbar for login and reset content margin
  const sidebar = document.getElementById('sidebar');
  const topbar = document.getElementById('topbar');
  const mainContent = app.closest('.main-content');
  if (sidebar) sidebar.style.display = 'none';
  if (topbar) topbar.style.display = 'none';
  if (mainContent) {
    mainContent.style.marginInlineStart = '0';
    mainContent.style.marginBlockStart = '0';
  }

  const form = document.getElementById('loginForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('loginEmail').value.trim();
    const password = document.getElementById('loginPassword').value;
    const btn = document.getElementById('loginBtn');
    const errDiv = document.getElementById('loginError');
    errDiv.style.display = 'none';

    btn.disabled = true;
    btn.textContent = '...';

    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || t('login.error'));
      }

      const data = await res.json();
      setTokens(data.access_token, data.refresh_token, data.user);

      // Show sidebar/topbar and restore layout
      if (sidebar) sidebar.style.display = '';
      if (topbar) topbar.style.display = '';
      if (mainContent) {
        mainContent.style.marginInlineStart = '';
        mainContent.style.marginBlockStart = '';
      }
      window.dispatchEvent(new CustomEvent('authchange'));
      navigate('#/dashboard');
    } catch (err) {
      errDiv.textContent = err.message;
      errDiv.style.display = 'block';
      btn.disabled = false;
      btn.textContent = t('login.submit');
    }
  });

  // Cleanup: restore sidebar/topbar visibility and content margin
  return () => {
    if (sidebar) sidebar.style.display = '';
    if (topbar) topbar.style.display = '';
    if (mainContent) {
      mainContent.style.marginInlineStart = '';
      mainContent.style.marginBlockStart = '';
    }
  };
}
