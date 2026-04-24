/**
 * api.js — Fetch wrapper with JWT auth and session management.
 */

const BASE = '/api/v1';
const ROLE_RANK = {
  hr_specialist: 0,
  hr_manager: 1,
  admin: 2,
  tenant_admin: 2,
  super_admin: 3,
};

/* ── Token helpers ───────────────────────────────────────────────── */

export function setTokens(access, refresh, user) {
  sessionStorage.setItem('krew_access', access);
  sessionStorage.setItem('krew_refresh', refresh);
  sessionStorage.setItem('krew_user', JSON.stringify(user));
}

export function clearTokens() {
  sessionStorage.removeItem('krew_access');
  sessionStorage.removeItem('krew_refresh');
  sessionStorage.removeItem('krew_user');
}

export function getAccessToken() {
  return sessionStorage.getItem('krew_access');
}

export function getRefreshToken() {
  return sessionStorage.getItem('krew_refresh');
}

export function getUser() {
  const raw = sessionStorage.getItem('krew_user');
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export function isLoggedIn() {
  return !!getAccessToken() && !!getUser();
}

export function hasMinRole(role) {
  const user = getUser();
  if (!user) return false;
  const userRank = ROLE_RANK[user.role] ?? -1;
  const requiredRank = ROLE_RANK[role] ?? 99;
  return userRank >= requiredRank;
}

/* ── Fetch wrapper ───────────────────────────────────────────────── */

export async function api(path, options = {}) {
  const token = getAccessToken();
  const headers = { ...(options.headers || {}) };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Only set Content-Type for JSON bodies (not FormData)
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    // Try refresh once
    const refreshed = await tryRefresh();
    if (refreshed) {
      headers['Authorization'] = `Bearer ${getAccessToken()}`;
      const retry = await fetch(`${BASE}${path}`, { ...options, headers });
      if (retry.status === 401) {
        clearTokens();
        window.location.hash = '#/login';
        throw new Error('Session expired');
      }
      return retry;
    }
    clearTokens();
    window.location.hash = '#/login';
    throw new Error('Session expired');
  }

  return res;
}

async function tryRefresh() {
  const refresh = getRefreshToken();
  if (!refresh) return false;

  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    const user = getUser();
    setTokens(data.access_token, data.refresh_token, user);
    return true;
  } catch {
    return false;
  }
}

/* ── Logout ──────────────────────────────────────────────────────── */

export async function logout() {
  const refresh = getRefreshToken();
  try {
    await api('/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refresh || '' }),
    });
  } catch { /* best-effort */ }
  clearTokens();
  window.location.hash = '#/login';
}
