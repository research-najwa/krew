/**
 * router.js — Hash-based SPA router with path params.
 */

const routes = [];
let currentCleanup = null;

/**
 * Register a route.
 * @param {string} hash - e.g. '#/dashboard' or '#/employees/:id'
 * @param {Function} loaderFn - async (params) => void, renders into #app
 * @param {Object} [options] - { minRole: 'hr_specialist' }
 */
export function register(hash, loaderFn, options = {}) {
  // Convert :param to regex groups
  const paramNames = [];
  const pattern = hash.replace(/:([^/]+)/g, (_, name) => {
    paramNames.push(name);
    return '([^/]+)';
  });
  const regex = new RegExp('^' + pattern + '$');
  routes.push({ regex, paramNames, loaderFn, options });
}

/**
 * Navigate to a hash route.
 */
export function navigate(hash) {
  window.location.hash = hash;
}

/**
 * Resolve current hash and render the matching page.
 */
export async function resolve() {
  const hash = window.location.hash || '#/dashboard';
  const app = document.getElementById('app');

  // Run cleanup from previous page
  if (currentCleanup && typeof currentCleanup === 'function') {
    currentCleanup();
    currentCleanup = null;
  }

  for (const route of routes) {
    const match = hash.match(route.regex);
    if (match) {
      const params = {};
      route.paramNames.forEach((name, i) => {
        params[name] = decodeURIComponent(match[i + 1]);
      });

      app.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;padding:80px 0;color:var(--text3)"><div class="spinner"></div></div>';

      try {
        const cleanup = await route.loaderFn(params);
        if (typeof cleanup === 'function') {
          currentCleanup = cleanup;
        }
      } catch (err) {
        console.error('Route error:', err);
        app.innerHTML = `<div style="padding:40px;text-align:center;color:var(--red)">Error loading page</div>`;
      }
      return;
    }
  }

  // No match — redirect to dashboard
  window.location.hash = '#/dashboard';
}

/**
 * Start listening for hash changes.
 */
export function start() {
  window.addEventListener('hashchange', resolve);
}
