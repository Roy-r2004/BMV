/** Host preview helpers — role page map + viewing-as blurb. */

export type PreviewRoute = {
  path: string;
  title?: string;
  role_id?: string;
};

export type PreviewRoleLike = {
  id: string;
  label?: string;
  tagline?: string;
};

const AI_HUB = '/ai-features';

function normalizePath(path: string): string {
  if (!path) return '/';
  const p = path.startsWith('/') ? path : `/${path}`;
  return p.length > 1 && p.endsWith('/') ? p.slice(0, -1) : p;
}

function isAiHub(path: string): boolean {
  const p = normalizePath(path);
  return p === AI_HUB || p.startsWith(`${AI_HUB}?`);
}

/** Title for a route tab when API omits one. */
export function routeTabTitle(path: string, title?: string): string {
  const t = (title || '').trim();
  if (t) return t;
  const p = normalizePath(path);
  if (p === '/') return 'Home';
  const seg = p.split('/').filter(Boolean).pop() || 'Page';
  return seg
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/**
 * Routes for the active role.
 * - Prefer explicit `role_id` matches.
 * - Orphan routes (no role_id) attach to the first role only.
 * - Always exclude the AI hub (separate chip).
 */
export function routesForRole(
  routes: PreviewRoute[] | undefined | null,
  roleId: string,
  firstRoleId: string,
): PreviewRoute[] {
  const list = Array.isArray(routes) ? routes : [];
  const seen = new Set<string>();
  const out: PreviewRoute[] = [];

  for (const rt of list) {
    const path = normalizePath(rt.path || '');
    if (!path || isAiHub(path) || seen.has(path)) continue;
    const rid = String(rt.role_id || '').trim();
    const orphan = !rid;
    const mine = rid === roleId || (orphan && roleId === firstRoleId);
    if (!mine) continue;
    seen.add(path);
    out.push({
      path,
      title: routeTabTitle(path, rt.title),
      role_id: rid || firstRoleId,
    });
  }
  return out;
}

/** One-line blurb under “Viewing as…”. */
export function roleViewingBlurb(role: PreviewRoleLike | undefined | null): string {
  const tag = (role?.tagline || '').trim();
  if (tag) return tag;
  const label = (role?.label || '').trim();
  if (!label) return 'Product view';
  return `${label} view`;
}

/** Whether currentPath matches a tab path (exact or nested under it). */
export function pathMatchesRoute(currentPath: string, routePath: string): boolean {
  const cur = normalizePath(currentPath || '/');
  const target = normalizePath(routePath || '/');
  if (cur === target) return true;
  if (target === '/') return cur === '/';
  return cur.startsWith(`${target}/`);
}

/** Pick the best active tab for the current path (longest matching prefix). */
export function activeRoutePath(
  currentPath: string,
  routes: PreviewRoute[],
): string | null {
  let best: string | null = null;
  let bestLen = -1;
  for (const rt of routes) {
    if (!pathMatchesRoute(currentPath, rt.path)) continue;
    const len = normalizePath(rt.path).length;
    if (len > bestLen) {
      best = normalizePath(rt.path);
      bestLen = len;
    }
  }
  return best;
}
