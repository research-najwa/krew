/**
 * app.js — Main SPA entry point.
 * Imports all pages, registers routes, handles auth and shell UI.
 */
import { isLoggedIn, getUser, hasMinRole, logout } from './api.js';
import { t, getCurrentLang, toggleLang, applyLang } from './i18n.js';
import { register, resolve, start, navigate } from './router.js';

// Page loaders
import loadLogin from './pages/login.js';
import loadDashboard from './pages/dashboard.js';
import loadEmployees from './pages/employees.js';
import loadEmployeeDetail from './pages/employee-detail.js';
import loadDepartments from './pages/departments.js';
import loadLeaves from './pages/leaves.js';
import loadReports from './pages/reports.js';
import loadSettings from './pages/settings.js';

/* ── Route Registration ──────────────────────────────────────────── */

register('#/login', loadLogin);
register('#/dashboard', guardAuth(loadDashboard));
register('#/employees', guardAuth(loadEmployees));
register('#/employees/:id', guardAuth(loadEmployeeDetail));
register('#/departments', guardAuth(loadDepartments));
register('#/leaves', guardAuth(loadLeaves));
register('#/reports', guardAuth(loadReports, 'hr_manager'));
register('#/settings', guardAuth(loadSettings, 'admin'));

function guardAuth(loaderFn, minRole = 'hr_specialist') {
  return async (params) => {
    if (!isLoggedIn()) {
      navigate('#/login');
      return;
    }
    if (!hasMinRole(minRole)) {
      navigate('#/dashboard');
      return;
    }
    return loaderFn(params);
  };
}

/* ── Shell UI Updates ────────────────────────────────────────────── */

function updateShellUI() {
  const loggedIn = isLoggedIn();
  const sidebar = document.getElementById('sidebar');
  const topbar = document.getElementById('topbar');

  if (!loggedIn) {
    sidebar.style.display = 'none';
    topbar.style.display = 'none';
    return;
  }

  sidebar.style.display = '';
  topbar.style.display = '';

  // User info in topbar
  const user = getUser();
  const userEl = document.getElementById('topbarUser');
  if (user && userEl) {
    userEl.textContent = user.full_name || user.email || '';
  }

  // Language toggle label
  const lang = getCurrentLang();
  document.getElementById('langToggle').textContent = lang === 'en' ? 'AR' : 'EN';

  // i18n for sidebar nav labels
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });

  // Logout label
  document.getElementById('logoutLabel').textContent = t('common.logout');

  // Settings nav visibility -- only show for admin+
  const settingsNav = document.querySelector('[data-route="#/settings"]');
  if (settingsNav) {
    settingsNav.style.display = hasMinRole('admin') ? '' : 'none';
  }

  // Reports nav visibility -- only show for hr_manager+
  const reportsNav = document.querySelector('[data-route="#/reports"]');
  if (reportsNav) {
    reportsNav.style.display = hasMinRole('hr_manager') ? '' : 'none';
  }

  updateActiveNav();
}

function updateActiveNav() {
  const hash = window.location.hash || '#/dashboard';

  // Highlight sidebar nav items
  document.querySelectorAll('.nav-item[data-route]').forEach(el => {
    const route = el.dataset.route;
    const isActive = hash === route || (route !== '#/dashboard' && hash.startsWith(route));
    el.classList.toggle('active', isActive);
  });

  // Update topbar title
  const titleMap = {
    '#/dashboard': 'nav.dashboard',
    '#/employees': 'nav.employees',
    '#/departments': 'nav.departments',
    '#/leaves': 'nav.leaves',
    '#/reports': 'nav.reports',
    '#/settings': 'nav.settings',
  };

  let titleKey = '';
  for (const [route, key] of Object.entries(titleMap)) {
    if (hash === route || hash.startsWith(route)) {
      titleKey = key;
      break;
    }
  }

  const topbarTitle = document.getElementById('topbarTitle');
  if (topbarTitle) {
    topbarTitle.textContent = titleKey ? t(titleKey) : '';
  }
}

/* ── Hamburger (mobile sidebar toggle) ───────────────────────────── */

const hamburgerBtn = document.getElementById('hamburgerBtn');
const sidebarEl = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');

function closeSidebar() {
  sidebarEl.classList.remove('open');
  sidebarOverlay.classList.remove('visible');
}

hamburgerBtn.addEventListener('click', () => {
  const isOpen = sidebarEl.classList.contains('open');
  if (isOpen) {
    closeSidebar();
  } else {
    sidebarEl.classList.add('open');
    sidebarOverlay.classList.add('visible');
  }
});

sidebarOverlay.addEventListener('click', closeSidebar);

// Close sidebar on navigation (mobile)
window.addEventListener('hashchange', closeSidebar);

/* ── Dark mode toggle ────────────────────────────────────────────── */

const darkToggle = document.getElementById('darkToggle');
const darkIcon = document.getElementById('darkIcon');

function applyDarkMode() {
  const isDark = document.documentElement.classList.contains('dark');
  darkIcon.innerHTML = isDark ? '&#9728;' : '&#127769;';
}

darkToggle.addEventListener('click', () => {
  document.documentElement.classList.toggle('dark');
  const isDark = document.documentElement.classList.contains('dark');
  localStorage.setItem('krew-dark', isDark);
  applyDarkMode();
});

// Restore dark mode from localStorage
if (localStorage.getItem('krew-dark') === 'true') {
  document.documentElement.classList.add('dark');
}
applyDarkMode();

/* ── Language toggle ─────────────────────────────────────────────── */

document.getElementById('langToggle').addEventListener('click', () => {
  toggleLang();
  updateShellUI();
  resolve();
});

/* ── Logout button ───────────────────────────────────────────────── */

document.getElementById('logoutBtn').addEventListener('click', logout);

/* ── Events ──────────────────────────────────────────────────────── */

// Auth change (dispatched from login page after successful login)
window.addEventListener('authchange', () => {
  updateShellUI();
});

// Hash change — update active nav and shell
window.addEventListener('hashchange', () => {
  updateShellUI();
});

/* ── Initialize ──────────────────────────────────────────────────── */

applyLang();
updateShellUI();

// Initial auth check
if (!isLoggedIn() && window.location.hash !== '#/login') {
  window.location.hash = '#/login';
}

// Start the router
start();
resolve();
